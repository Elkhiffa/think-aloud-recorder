"""Local recording engine. Every session is durable before the first OBS request."""
from pathlib import Path
from datetime import datetime
import json, os, re, shutil, subprocess, time, uuid, zipfile, hashlib, math
import av
from media_runtime import resolve_ffmpeg
import obsws_python as obs
from obsws_python.error import OBSSDKRequestError
import functools,msvcrt,threading
from contextlib import contextmanager
import psutil

ROOT=Path(__file__).resolve().parent
FFMPEG=resolve_ffmpeg(ROOT)
HIDDEN=0x08000000 if os.name=='nt' else 0
PRESETS={'均衡 1080p30':(1920,1080,30),'流畅 1080p60':(1920,1080,60),'省空间 720p30':(1280,720,30)}
SESSION_SETTING_KEYS=('game','language','preset','source','window','monitor','mic',
    'model','device','compute_type','transcription_provider','hotwords','qwen_region','qwen_model','record_inputs')
_obs_process_lock=threading.RLock()
_owned_obs={}
_obs_closed_roots=set()
_OBS_RECEIPT='state/owned-obs.json'


class _RecoveredObsProcess:
    """The exact child from a previous app run, identified by its birth time."""
    def __init__(self, process):
        self._process=process
        self.pid=process.pid

    def poll(self):
        try:return None if self._process.is_running() else 0
        except psutil.NoSuchProcess:return 0

    def wait(self, timeout):
        try:return self._process.wait(timeout=timeout)
        except psutil.TimeoutExpired as error:
            raise subprocess.TimeoutExpired('owned OBS',timeout) from error

    def terminate(self):
        self._process.terminate()


def _obs_receipt(root, owned=None, status='running'):
    path=root/_OBS_RECEIPT
    if owned is None:
        if not path.is_file():return None
        try:return read(path)
        except (OSError,ValueError,TypeError):return None
    write(path,dict(schema=1,status=status,root=str(root),exe=str(owned['exe']),
                    pid=owned['process'].pid,created=owned['created'],
                    parent_pid=owned['parent_pid']))


def _recover_owned_obs(root, cfg):
    """Reattach only a previous run's exact child from this installation.

    The receipt has no credentials and grants no right to stop an output. The
    ordinary live socket, idle-output, profile and window checks still apply.
    """
    if root in _owned_obs:return _owned_obs[root]
    receipt=_obs_receipt(root)
    if not isinstance(receipt,dict) or receipt.get('schema')!=1 or receipt.get('status')!='running':
        return None
    exe=(root/'tools/obs/bin/64bit/obs64.exe').resolve()
    try:
        if Path(receipt['root']).resolve()!=root or Path(receipt['exe']).resolve()!=exe:
            return None
        pid=receipt['pid']; parent_pid=receipt['parent_pid']; created=receipt['created']
        if type(pid) is not int or type(parent_pid) is not int or type(created) not in (int,float):
            return None
        child=psutil.Process(pid)
        if (not child.is_running() or child.ppid()!=parent_pid
                or Path(child.exe()).resolve()!=exe or abs(child.create_time()-created)>.01):
            return None
    except (KeyError,ValueError,TypeError,OSError,psutil.Error):
        return None
    owned=dict(process=_RecoveredObsProcess(child),exe=exe,port=cfg['port'],
               password=cfg['password'],created=created,parent_pid=parent_pid)
    _owned_obs[root]=owned
    return owned

def session_settings(cfg):
    """Session exports contain their own recording choices, not other presets."""
    return {key:cfg[key] for key in SESSION_SETTING_KEYS if key in cfg}
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,data):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.'+uuid.uuid4().hex+'.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(40):
        try:os.replace(tmp,p);return
        except PermissionError:
            if attempt==39:raise
            time.sleep(.05)
def config():
    from portable_config import load_settings
    return load_settings(ROOT)

def save_config(cfg):
    from portable_config import stored_settings
    write(ROOT/'config.json',stored_settings(ROOT,cfg))
def open_review(session, progress=lambda s: None):
    """Portable browser entry; the desktop service owns native review windows."""
    from review_runtime import session_review_payload, render_player
    (session.path / '独立回看.html').write_text(render_player(ROOT, session_review_payload(session.path)), encoding='utf-8')
    os.startfile(session.path / '独立回看.html')
    progress('已请求打开独立回看网页。')
    return 'browser-requested'
def stamp(t):
    ms=round(t*1000);s,ms=divmod(ms,1000);m,s=divmod(s,60);h,m=divmod(m,60)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'
def run(args,log):
    with open(log,'ab') as out:
        p=subprocess.run([FFMPEG,'-nostdin','-hide_banner','-y',*map(str,args)],stdout=out,stderr=out,creationflags=HIDDEN)
    if p.returncode: raise RuntimeError(f'音视频处理失败，见 {Path(log).name}')
def probe(path):
    with av.open(str(path)) as f:
        return {'duration':float(f.duration or 0)/av.time_base,'video':len(f.streams.video),'audio':len(f.streams.audio),'codecs':[s.codec_context.name for s in f.streams]}

def video_clock_endpoint(path):
    """Use the published video track, not longer AAC/container duration."""
    with av.open(str(path)) as media:
        if len(media.streams.video)!=1:raise ValueError('ambiguous video stream')
        video=media.streams.video[0]
        if video.duration is None or video.start_time is None or not video.average_rate:
            raise ValueError('video presentation clock unavailable')
        start=float(video.start_time*video.time_base)
        end=float((video.start_time+video.duration)*video.time_base)
        rate=float(video.average_rate)
        if not (10<=rate<=240 and 0<=start<=.25 and end>start):
            raise ValueError('unsupported video presentation clock')
        return end,1/rate

def microphone_is_silent(path):
    """Only digital zero counts as silence; quiet speech must still be transcribed."""
    samples=0
    with av.open(str(path)) as audio:
        for frame in audio.decode(audio=0):
            samples+=frame.samples
            if frame.to_ndarray().any():return False
    if not samples:raise RuntimeError('独立口述音轨没有有效采样，原始录像已保留。')
    return True
def wait_obs_ready(r,timeout=45,progress=lambda s:None):
    """A websocket handshake can finish before OBS loads its scene collection."""
    deadline=time.monotonic()+timeout
    notified=False
    while True:
        try:
            recording=r.get_record_status()
            streaming=r.get_stream_status()
            return recording,streaming
        except OBSSDKRequestError as error:
            if error.code!=207:raise
            if not notified:
                progress('录制引擎正在加载配置，请稍候…');notified=True
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise RuntimeError('录制引擎尚未完成初始化。请稍后重试；如果持续出现，请检查专用 OBS 是否有等待处理的提示窗口。') from error
            time.sleep(min(.2,remaining))

def client(launch=True,progress=lambda s:None):
    # Keep the original process handle, and serialize launch/close so reconnects
    # cannot create duplicate children or race an accepted application close.
    with _obs_process_lock:
        if ROOT.resolve() in _obs_closed_roots:
            raise RuntimeError('记录器正在关闭，录制引擎不再接受新连接。')
        return _connect_obs(launch,progress)

@contextmanager
def obs_connection(*args,**kwargs):
    """Release each operation's socket explicitly, including failed requests.

    ReqClient owns dynamically bound methods; relying on local-variable cleanup
    can leave its socket alive until cyclic GC, delaying OBS's normal shutdown.
    """
    connection=client(*args,**kwargs)
    try:yield connection
    finally:
        try:connection.disconnect()
        except Exception:pass

def _connect_obs(launch,progress):
    c=config()
    root=ROOT.resolve()
    owned=_recover_owned_obs(root,c)
    try:r=obs.ReqClient(host='127.0.0.1',port=c['port'],password=c['password'],timeout=8)
    except Exception:
        if not launch:raise
        if owned is not None and owned['process'].poll() is None:
            progress('正在重新连接录制引擎，请稍候…')
        else:
            progress('正在启动录制引擎，请稍候…')
            exe=ROOT/'tools/obs/bin/64bit/obs64.exe'
            process=subprocess.Popen([str(exe),'--portable','--multi','--profile','Experience','--collection','Experience','--minimize-to-tray','--disable-shutdown-check'],cwd=exe.parent,creationflags=HIDDEN)
            try:
                owned=dict(process=process,exe=exe.resolve(),port=c['port'],password=c['password'],
                           created=psutil.Process(process.pid).create_time(),parent_pid=os.getpid())
                _obs_receipt(root,owned)
            except Exception as error:
                # A child without durable ownership could survive every later
                # application run. It has not yet been used for recording.
                process.terminate()
                process.wait(timeout=5)
                raise RuntimeError('无法保存录制引擎的进程归属，已取消启动。') from error
            _owned_obs[root]=owned
        for _ in range(45):
            time.sleep(1)
            try:r=obs.ReqClient(host='127.0.0.1',port=c['port'],password=c['password'],timeout=2);break
            except Exception:pass
        else:
            if owned is not None and owned['process'].poll() is None:
                raise RuntimeError('上次启动的录制引擎仍在运行，但无法连接。请先确认它已退出。')
            raise RuntimeError('专用 OBS 未能连接。请查看 tools/obs/config/obs-studio/logs。')
    # Readiness failures must never launch another OBS instance.
    try:
        wait_obs_ready(r,progress=progress)
        # Retry handshakes stay short, but a ready connection must use the same
        # request deadline as a connection to an already-running OBS. Scene and
        # device initialization can legitimately exceed the 2s handshake bound.
        r.base_client.ws.settimeout(8)
        r.base_client.timeout=8
    except Exception:
        try:r.disconnect()
        except Exception:pass
        raise
    return r

def _owned_obs_identity(owned,connection=None):
    """A live original child handle plus image, parent and exact TCP peer proof."""
    process=owned['process']
    if process.poll() is not None:return False
    child=psutil.Process(process.pid)
    if (child.ppid()!=owned.get('parent_pid',os.getpid())
            or Path(child.exe()).resolve()!=owned['exe']):return False
    if 'created' in owned and abs(child.create_time()-owned['created'])>.01:return False
    if connection is not None:
        sock=connection.base_client.ws.sock
        local,peer=sock.getsockname(),sock.getpeername()
        if not any(tuple(item.laddr)==tuple(peer) and tuple(item.raddr)==tuple(local)
                   and item.status==psutil.CONN_ESTABLISHED
                   for item in child.net_connections(kind='tcp')):
            return False
    return process.poll() is None

def _request_obs_window_close(process):
    """Send normal WM_CLOSE only to this live child's OBS main window; never kill."""
    if os.name!='nt' or process.poll() is not None:return False
    import ctypes
    from ctypes import wintypes
    user32=ctypes.WinDLL('user32',use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user32.EnumWindows.argtypes=(callback_type,wintypes.LPARAM)
    user32.EnumWindows.restype=wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes=(wintypes.HWND,ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowTextW.argtypes=(wintypes.HWND,wintypes.LPWSTR,ctypes.c_int)
    user32.PostMessageW.argtypes=(wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM)
    user32.PostMessageW.restype=wintypes.BOOL
    windows=[]
    def visit(hwnd,_):
        pid=wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==process.pid:
            title=ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd,title,len(title))
            if title.value.startswith('OBS '):windows.append(hwnd)
        return True
    user32.EnumWindows(callback_type(visit),0)
    if len(windows)!=1 or process.poll() is not None:return False
    # Recheck the HWND owner immediately before posting, after enumeration.
    pid=wintypes.DWORD()
    user32.GetWindowThreadProcessId(windows[0],ctypes.byref(pid))
    return pid.value==process.pid and bool(user32.PostMessageW(windows[0],0x0010,0,0))

def _stock_obs_environment(root, owned):
    """Bound the stock-output status APIs to the shipped, unscripted OBS.

    GetOutputList can crash OBS after SetVideoSettings (upstream #1344). The
    four frontend status APIs cannot attest to arbitrary plugin outputs, so an
    unknown module, scripting history, hardware output module or unverifiable
    startup log must preserve the process. This is an operational customization
    check, not a security boundary against a locally tampered executable/log.
    """
    try:
        child=psutil.Process(owned['process'].pid)
        environment=child.environ()
        if any(environment.get(name) for name in ('OBS_PLUGINS_PATH','OBS_PLUGINS_DATA_PATH')):return False
        plugins=root/'tools/obs/obs-plugins/64bit'
        rows=read(root/'scripts/runtime-seed.json')['files']
        expected={Path(row['path']).name.casefold():row for row in rows
            if row['path'].startswith('tools/obs/obs-plugins/64bit/') and row['path'].endswith('.dll')}
        actual={path.name.casefold():path for path in plugins.glob('*.dll')}
        if not expected or set(expected)!=set(actual):return False
        # Portable OBS skips machine-wide module paths. The recorded command
        # line and environment must prove that this process used that mode.
        if '--portable' not in child.cmdline():return False
        settings=root/'tools/obs/config/obs-studio'
        logs=[path for path in (settings/'logs').glob('*.txt')
            if owned['created']-1<=path.stat().st_ctime<=owned['created']+60]
        if len(logs)!=1 or logs[0].stat().st_size>20*1024*1024:return False
        log=logs[0].read_text(encoding='utf-8-sig')
        if '==== Startup complete' not in log:return False
        if re.search(r'\[obs-scripting\]|\[(?:Lua|Python):',log,re.I):return False
        section=re.search(r'Loaded Modules:\r?\n(.*?)(?:\r?\n[^\n]*-{8,})',log,re.S)
        if section is None:return False
        modules=re.findall(r'^\d\d:\d\d:\d\d\.\d+:\s+([^\s]+\.dll)\s*$',section[1],re.M)
        if not modules or any(name.casefold() not in expected for name in modules):return False
        if any(name.casefold() in ('aja.dll','decklink.dll') for name in modules):return False
        loaded={str(Path(item.path).resolve()).casefold() for item in child.memory_maps() if item.path}
        for name in modules:
            path=actual[name.casefold()]
            if (not path.resolve().is_relative_to(plugins.resolve())
                    or str(path.resolve()).casefold() not in loaded
                    or sha256(path)!=expected[name.casefold()]['sha256']):return False
        # Configurations of stock hardware-output tools are also outside the
        # app's four standard output kinds. Cache-only stock files are harmless.
        allowed={'obs-websocket/config.json','rtmp-services/meta.json','rtmp-services/package.json',
            'rtmp-services/services.json','win-capture/meta.json','win-capture/package.json','win-capture/compatibility.json'}
        directory=settings/'plugin_config'
        for path in directory.rglob('*'):
            if path.is_file() and path.relative_to(directory).as_posix() not in allowed:return False
        for path in (settings/'basic/scenes').glob('*.json'):
            if path.stat().st_size>4*1024*1024 or read(path).get('modules',{}).get('scripts-tool',[]):return False
        return True
    except (OSError,ValueError,TypeError,KeyError,AttributeError,psutil.Error):
        return False


def shutdown_owned_obs(root):
    """After accepted app close, exit only our verified idle child.

    A durable receipt recognizes our exact child after a recorder restart. If
    normal close stalls, terminate that already-verified idle child by its
    original handle; never stop outputs or target an unverified process.
    Returned reasons are fixed codes and never include connection credentials.
    """
    root=Path(root).resolve()
    with _obs_process_lock:
        _obs_closed_roots.add(root)
        owned=_owned_obs.get(root)
        if owned is None:
            try:owned=_recover_owned_obs(root,config())
            except Exception:return {'status':'unverified'}
        if owned is None:return {'status':'not_owned'}
        process=owned['process']
        if process.poll() is not None:
            _owned_obs.pop(root,None)
            try:_obs_receipt(root,owned,'exited')
            except OSError:pass
            return {'status':'already_exited'}
        connection=None
        try:
            if not _owned_obs_identity(owned):return {'status':'identity_unverified'}
            connection=obs.ReqClient(host='127.0.0.1',port=owned['port'],password=owned['password'],timeout=2)
            if not _owned_obs_identity(owned,connection):return {'status':'endpoint_unverified'}
            # An OBS started by us may subsequently be used from its own UI.
            # Missing fields, disconnection and active auxiliary outputs are unsafe.
            for request in ('get_record_status','get_stream_status','get_replay_buffer_status','get_virtual_cam_status'):
                try:status=getattr(connection,request)()
                except OBSSDKRequestError as error:
                    # Only an explicitly unavailable replay buffer is known
                    # absent. Other failures, including virtualcam, stay unknown.
                    if request=='get_replay_buffer_status' and error.code==604:continue
                    raise
                if getattr(status,'output_active',None) is not False:return {'status':'output_active_or_unknown'}
            if (connection.get_profile_list().current_profile_name!='Experience'
                    or connection.get_scene_collection_list().current_scene_collection_name!='Experience'):
                return {'status':'configuration_changed'}
            if not _stock_obs_environment(root,owned):return {'status':'custom_outputs_unverified'}
            if not _owned_obs_identity(owned,connection):return {'status':'identity_unverified'}
            # Release our WebSocket before asking OBS to stop its server.
            # Holding it open can delay the child's otherwise normal exit.
            connection.disconnect()
            connection=None
            if not _request_obs_window_close(process):return {'status':'close_not_requested'}
            try:
                process.wait(timeout=8)
                result='closed'
            except subprocess.TimeoutExpired:
                # OBS has begun a normal exit and its outputs were verified
                # idle immediately before WM_CLOSE. A stalled child otherwise
                # keeps its executable and DLLs locked indefinitely.
                if not _owned_obs_identity(owned):return {'status':'close_unconfirmed'}
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:return {'status':'close_unconfirmed'}
                result='terminated_after_close_timeout'
            _owned_obs.pop(root,None)
            try:_obs_receipt(root,owned,'exited')
            except OSError:pass
            return {'status':result}
        except Exception:
            return {'status':'unverified'}
        finally:
            if connection is not None:
                try:connection.disconnect()
                except Exception:pass
def ensure_idle(r):
    recording,streaming=wait_obs_ready(r)
    if recording.output_active: raise RuntimeError('OBS 已在录制，未覆盖或停止它。请先处理当前场次。')
    if streaming.output_active: raise RuntimeError('专用 OBS 正在推流，请先停止推流。')
    if r.get_profile_list().current_profile_name!='Experience':
        r.set_current_profile('Experience');wait_obs_ready(r)
    if r.get_scene_collection_list().current_scene_collection_name!='Experience':
        r.set_current_scene_collection('Experience');wait_obs_ready(r)
def add(r,name,kind,settings,enabled=True):
    existing={i['inputName'] for i in r.get_input_list().inputs}
    if name in existing: r.set_input_settings(name,settings,True)
    else:r.create_input('Experience',name,kind,settings,enabled)
def tracks(r,name,nums):r.set_input_audio_tracks(name,{str(i):i in nums for i in range(1,7)})
def primary_monitor_ids():
    """Read Windows' primary monitor identity; callers must match actual OBS items.

    OBS monitor properties use the display-interface ID on current releases and
    the display name on some older ones. Neither list order nor OBS' placeholder
    default (for example ``DUMMY``) identifies the primary display.
    """
    if os.name != 'nt':
        return ()
    try:
        import ctypes
        from ctypes import wintypes

        class MonitorInfo(ctypes.Structure):
            _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                        ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD),
                        ('szDevice', wintypes.WCHAR * 32)]

        class DisplayDevice(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('DeviceName', wintypes.WCHAR * 32),
                        ('DeviceString', wintypes.WCHAR * 128), ('StateFlags', wintypes.DWORD),
                        ('DeviceID', wintypes.WCHAR * 128), ('DeviceKey', wintypes.WCHAR * 128)]

        user32 = ctypes.WinDLL('user32', use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                          ctypes.POINTER(wintypes.RECT), ctypes.c_ssize_t)
        user32.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                               callback_type, ctypes.c_ssize_t]
        user32.EnumDisplayMonitors.restype = wintypes.BOOL
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.EnumDisplayDevicesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
                                               ctypes.POINTER(DisplayDevice), wintypes.DWORD]
        user32.EnumDisplayDevicesW.restype = wintypes.BOOL
        primary = []

        @callback_type
        def visit(monitor, _dc, _rect, _data):
            info = MonitorInfo()
            info.cbSize = ctypes.sizeof(info)
            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)) and info.dwFlags & 1:
                primary.append(info.szDevice)
            return True

        if not user32.EnumDisplayMonitors(None, None, visit, 0) or len(primary) != 1 or not primary[0]:
            return ()
        display = DisplayDevice()
        display.cb = ctypes.sizeof(display)
        # EDD_GET_DEVICE_INTERFACE_NAME, read-only; never change display settings.
        if user32.EnumDisplayDevicesW(primary[0], 0, ctypes.byref(display), 1) and display.DeviceID:
            return (display.DeviceID, primary[0])
        return (primary[0],)
    except Exception:
        # Optional default suggestions must not prevent device enumeration.
        return ()

def devices(progress=lambda s:None):
    with obs_connection(progress=progress) as r:
        ensure_idle(r)
        add(r,'设置：麦克风','wasapi_input_capture',{'device_id':'default'},False)
        add(r,'设置：窗口','window_capture',{},False)
        add(r,'设置：显示器','monitor_capture',{},False)
        result={}
        for key,name,prop in [('mic','设置：麦克风','device_id'),('window','设置：窗口','window'),('monitor','设置：显示器','monitor_id')]:
            result[key]=r.get_input_properties_list_property_items(name,prop).property_items
            result[key]=[x for x in result[key] if x.get('itemEnabled') and x.get('itemValue')]
        for n in ['设置：麦克风','设置：窗口','设置：显示器']:r.remove_input(n)
        return result
def configure_scene(r,c,test_file=None):
    ensure_idle(r)
    if r.get_profile_parameter('Output','Mode').parameter_value!='Advanced' or r.get_profile_parameter('AdvOut','RecTracks').parameter_value!='3':
        raise RuntimeError('OBS 专用配置必须录制第 1、2 两条音轨，当前配置已改变。请恢复 Experience 配置后重试。')
    for i in r.get_input_list().inputs:r.remove_input(i['inputName'])
    for _ in range(100):
        if not r.get_input_list().inputs:break
        time.sleep(0.1)
    else:raise RuntimeError('OBS 旧录制源尚未释放，稍后重试。')
    w,h,fps=PRESETS[c['preset']]
    r.send('SetVideoSettings',{'baseWidth':w,'baseHeight':h,'outputWidth':w,'outputHeight':h,'fpsNumerator':fps,'fpsDenominator':1})
    if test_file:
        add(r,'测试素材','ffmpeg_source',{'local_file':str(test_file),'is_local_file':True,'looping':True,'restart_on_activate':True})
        tracks(r,'测试素材',[1,2])
        tone=Path(test_file).parent/'测试游戏声.wav'
        if tone.exists():
            add(r,'测试游戏声','ffmpeg_source',{'local_file':str(tone),'is_local_file':True,'looping':True,'restart_on_activate':True});tracks(r,'测试游戏声',[1])
    else:
        if c['source']=='游戏窗口':
            if not c.get('window'):raise RuntimeError('请先在设置中选择已打开的游戏窗口。')
            add(r,'游戏画面','window_capture',{'window':c['window'],'method':2,'cursor':True,'client_area':True})
        else:
            if not c.get('monitor'):raise RuntimeError('请先在设置中选择显示器。')
            add(r,'游戏画面','monitor_capture',{'monitor_id':c['monitor'],'capture_cursor':True})
        add(r,'游戏声音','wasapi_output_capture',{'device_id':'default'});tracks(r,'游戏声音',[1])
        add(r,'口述','wasapi_input_capture',{'device_id':c['mic']});tracks(r,'口述',[1,2])
        r.set_input_mute('口述',False)
        for name,prop,value in [('口述','device_id',c['mic']),('游戏画面','window' if c['source']=='游戏窗口' else 'monitor_id',c['window'] if c['source']=='游戏窗口' else c['monitor'])]:
            options=r.get_input_properties_list_property_items(name,prop).property_items
            if not any(item.get('itemEnabled') and item['itemValue']==value for item in options):raise RuntimeError(f'{name} 已不可用，请打开游戏或重新连接设备，然后在首次设置中重新选择。')
    for item in r.get_scene_item_list('Experience').scene_items:
        r.set_scene_item_transform('Experience',item['sceneItemId'],{'boundsType':'OBS_BOUNDS_SCALE_INNER','boundsWidth':w,'boundsHeight':h,'positionX':0,'positionY':0})
    r.set_current_program_scene('Experience')
    time.sleep(0.5)
    expected={'测试素材'} if test_file else {'游戏画面','游戏声音','口述'}
    actual={i['inputName'] for i in r.get_input_list().inputs}
    if not expected.issubset(actual):raise RuntimeError('OBS 录制源未能就绪，已取消开始。')
    microphone='测试素材' if test_file else '口述'
    for item in r.get_input_list().inputs:
        name=item['inputName']
        if name=='游戏画面':continue
        track_state=r.get_input_audio_tracks(name).input_audio_tracks
        if bool(track_state.get('2'))!=(name==microphone):raise RuntimeError('音轨隔离检查失败：第 2 轨只能包含选定麦克风。')

def session_lock(fn):
    @functools.wraps(fn)
    def wrapper(self,*args,**kwargs):
        with open(self.path/'.processing.lock','a+b') as lock:
            lock.seek(0)
            try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('此场次正在由另一个操作处理，请等待完成后再试。')
            try:return fn(self,*args,**kwargs)
            finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)
    return wrapper

class _InputClockEvents:
    """Optional output-only observer; no capture data or credentials persisted.

    The STOPPING notification bounds when OBS takes its stop timestamp. A stop
    response alone is insufficient: its UI action may still be queued. Keeping
    this connection from before StartRecord also detects pauses between polls.
    """
    def __init__(self, request):
        base=request.base_client
        if not (base.host in ('127.0.0.1','localhost') and type(base.port) is int):
            raise ValueError('local OBS endpoint required')
        self.started=False
        self.invalid=False
        self.stopping=None
        self._lock=threading.Lock()
        self._client=obs.EventClient(host=base.host,port=base.port,password=base.password,timeout=2,subs=64)
        self._client.callback.register(self.on_record_state_changed)

    def on_record_state_changed(self, event):
        with self._lock:
            state=getattr(event,'output_state','')
            if state=='OBS_WEBSOCKET_OUTPUT_STARTED':
                if self.started:self.invalid=True
                self.started=True
            elif state in ('OBS_WEBSOCKET_OUTPUT_PAUSED','OBS_WEBSOCKET_OUTPUT_RESUMED'):
                self.invalid=True
            elif state=='OBS_WEBSOCKET_OUTPUT_STOPPING':
                if self.stopping is not None:self.invalid=True
                self.stopping=time.perf_counter()
            elif state=='OBS_WEBSOCKET_OUTPUT_STOPPED' and self.stopping is None:
                self.invalid=True

    def boundary(self, before):
        with self._lock:
            if (not self.started or self.invalid or not self._client.worker.is_alive()
                    or self.stopping is None or not before<=self.stopping<=before+.2):
                return None
            return (before,self.stopping)

    def close(self):
        self._client.disconnect()


class Session:
    def __init__(self,path):
        self.path=Path(path);self.meta=read(self.path/'session.json')
        self._input_capture=None
        self._video_seconds=0.0
        self._input_clock_anchor=None
        self._input_clock_trusted=None
        self._input_clock_events=None
        self._input_stop_boundary=None
        self._input_clock_continuous=False
    def update(self,**kw):
        from session_metadata import update_metadata
        self.meta=update_metadata(self.path,kw)
    @staticmethod
    def output_seconds(status):
        value=getattr(status,'output_duration',None)
        if type(value) in (int,float) and math.isfinite(value) and value>=0:return value/1000.0
        code=getattr(status,'output_timecode','')
        if isinstance(code,str):
            try:
                hours,minutes,seconds=code.split(':')
                value=int(hours)*3600+int(minutes)*60+float(seconds)
                if math.isfinite(value) and value>=0:return value
            except (ValueError,TypeError):pass
        raise RuntimeError('OBS 尚未返回录像时间，无法同步操作记录。')
    def await_input_clock(self,client,status,before,after):
        """Confirm an advancing output clock before creating any input listener.

        OBS acknowledges output_active before its encoder emits frames. A zero
        duration at that point cannot anchor wall time to video time. Require
        three positive samples, two increments and a short stable span instead;
        the collector will mark all video before listener readiness as a gap.
        This bounded startup check never weakens ongoing pause/drift detection.
        """
        deadline=after+5
        candidate=previous=None
        increments=0
        for _ in range(51):
            if not getattr(status,'output_active',False):
                raise RuntimeError('OBS 已停止输出，未启动操作采集。')
            if getattr(status,'output_paused',False) is True:
                raise RuntimeError('OBS 启动时已暂停，未启动操作采集。')
            try:seconds=self.output_seconds(status)
            except RuntimeError:seconds=None
            midpoint=(before+after)/2
            uncertainty=max(0,(after-before)/2)
            if seconds is not None:self._video_seconds=seconds
            if seconds is None or seconds<=0 or uncertainty>.1:
                candidate=previous=None
                increments=0
            else:
                sample=(midpoint,seconds,uncertainty)
                if candidate is not None:
                    elapsed=midpoint-candidate[0]
                    progressed=seconds-candidate[1]
                    if seconds>previous[1] and abs(progressed-elapsed)<=.1+candidate[2]+uncertainty:
                        increments+=1
                        if increments>=2 and elapsed>=.15:return status,before,after
                    else:
                        candidate=None
                if candidate is None:
                    candidate=sample
                    increments=0
                previous=sample
            if after>=deadline:break
            time.sleep(.1)
            before=time.perf_counter()
            status=client.get_record_status()
            after=time.perf_counter()
        raise RuntimeError('OBS 录像时间尚未稳定递增，未启动操作采集；录像仍会保留。')
    def observe_input_clock(self,status,before,after):
        """Fail closed on a paused/discontinuous OBS clock; never retime facts.

        Request midpoint estimates carry half-roundtrip uncertainty. Every sample
        is compared to the initial anchor, so small persistent drift cannot hide
        by being accepted one short interval at a time.
        """
        if self._input_capture is None:return False
        midpoint=(before+after)/2
        uncertainty=max(0,(after-before)/2)
        try:seconds=self.output_seconds(status)
        except RuntimeError:
            cutoff=(self._input_clock_trusted or (0,0,0))[1]
            self.finish_inputs(cutoff,interrupted=True,trim_to=cutoff,error='录像时钟暂不可确认，操作采集已停止。')
            return False
        self._video_seconds=seconds
        if getattr(status,'output_paused',False) is True:
            self.finish_inputs(seconds,interrupted=True,trim_to=seconds,error='OBS 已暂停录像，操作采集已停止；恢复录像后不补写未知操作。')
            self.update(warning='OBS 暂停导致操作采集中断，后续录像区间将标记为缺口。')
            return False
        sample=(midpoint,seconds,uncertainty)
        anchor=self._input_clock_anchor
        if anchor is None:
            self._input_clock_anchor=self._input_clock_trusted=sample
            self._input_clock_continuous=True
            return True
        expected=anchor[1]+midpoint-anchor[0]
        tolerance=.25+anchor[2]+uncertainty
        if abs(seconds-expected)>tolerance:
            cutoff=self._input_clock_trusted[1]
            self.finish_inputs(max(cutoff,seconds),interrupted=True,trim_to=cutoff,error='录像时钟与操作时钟不连续，已保留上次可信校准前的操作；后续区间不能恢复。')
            self.update(warning='检测到暂停或录像时钟变化，操作采集已停止并标记数据缺口。')
            return False
        # Slow replies may confirm continuity but are not better trim points.
        if uncertainty<=.5:
            self._input_clock_trusted=sample
            self.update(input_clock={**self.meta.get('input_clock',{}),'last_verified_seconds':seconds})
        return True
    def finish_inputs(self,duration=None,*,interrupted=False,error=None,trim_to=None):
        if interrupted or error or trim_to is not None:
            self._input_clock_continuous=False
            self.close_input_clock_events()
        capture=self._input_capture
        self._input_capture=None
        if capture is not None:
            try:
                if interrupted and trim_to is None and self._input_clock_trusted is not None:
                    trim_to=self._input_clock_trusted[1]
                options={'duration':duration,'interrupted':interrupted,'error':error}
                if trim_to is not None:options['trim_to']=trim_to
                result=capture.stop(**options)
                if result.get('version')==1 and trim_to is not None:
                    endpoint=max(float(result.get('duration',0)),float(duration or 0))
                    if endpoint>result['duration']:
                        result.setdefault('gaps',[]).append(dict(start=result['duration'],end=endpoint,type='capture',reason=error or '操作时钟无法继续确认'))
                        result['duration']=endpoint
                        write(self.path/'input-events.json',result)
                self.update(input_state=result.get('state','failed'))
            except Exception:
                self.update(input_state='failed',input_error='操作记录未能完整保存，原始录像不受影响。')
        elif self.meta.get('settings',{}).get('record_inputs'):
            # A recovered recording has no listener owned by this process. Never
            # resume global capture silently or claim that the gap had no input.
            path=self.path/'input-events.json'
            try:
                data=read(path) if path.is_file() else {'state':'recording'}
                was_recording=self.meta.get('state') in ('录制中','启动中','保存中') or self.meta.get('recording_uncertain')
                if data.get('state') in ('recording','prepared') or (interrupted and was_recording and data.get('state') == 'complete'):
                    verified=self.meta.get('input_clock',{}).get('last_verified_seconds')
                    if trim_to is None and type(verified) in (int,float) and math.isfinite(verified) and verified>=0:
                        trim_to=verified
                    from input_capture import recover_capture
                    recover_capture(self.path,duration,error=error or '操作采集已中断；未记录的区间不能恢复。',trim_to=trim_to)
                    self.update(input_state='interrupted')
            except Exception:
                self.update(input_state='failed',input_error='操作记录文件无法恢复，原始录像不受影响。')
    def close_input_clock_events(self):
        events=self._input_clock_events
        self._input_clock_events=None
        if events is not None:
            try:events.close()
            except Exception:pass

    def calibrate_input_clock(self, video):
        """Estimate a constant presentation offset only for a verified live run.

        GetRecordStatus counts packets already emitted by the encoder; it can
        lag the captured image by a stable encoder buffer. Final video end and
        the actual StopRecord boundary share the capture clock instead. Keep
        their derived correction separate from the immutable input intervals.
        """
        boundary=self._input_stop_boundary
        anchor=self._input_clock_anchor
        if (boundary is None or anchor is None or not self._input_clock_continuous
                or self.meta.get('input_state')!='complete'
                or self.meta.get('input_alignment')):return
        try:
            data=read(self.path/'input-events.json')
            if data.get('state')!='complete' or (self.path/'input-events.revocation.json').exists():return
            endpoint,frame=video_clock_endpoint(video)
            before,after=boundary
            # Include the event delivery window, clock-query midpoint error,
            # video frame quantization and encoder presentation reordering.
            uncertainty=(after-before)/2+anchor[2]+3*frame
            offset=endpoint-(anchor[1]+(before+after)/2-anchor[0])
            if uncertainty>.25 or not math.isfinite(offset) or abs(offset)>30:return
            self.update(input_alignment=dict(method='final_video_stop_boundary_v1',
                offset_seconds=round(offset,6),uncertainty_seconds=round(uncertainty,6),
                video_endpoint_seconds=round(endpoint,6),
                stop_request_raw_seconds=round(anchor[1]+before-anchor[0],6),
                stopping_event_delay_seconds=round(after-before,6)))
        except (OSError,ValueError,TypeError,KeyError,OverflowError):
            # Uncertain calibration never blocks video publication or invents
            # precision. Review retains explicit manual per-session alignment.
            return
    @classmethod
    def start(cls,c,test_file=None):
        with obs_connection() as r:
            ensure_idle(r)
            vault=Path(c['vault']);vault.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(vault).free<5*1024**3:raise RuntimeError('保存盘可用空间不足 5 GB。请清理或更换保存位置。')
            configure_scene(r,c,test_file)
            ident=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
            game=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',c['game']).strip(' .')[:60] or '自由探索'
            folder=vault/'场次'/f'{ident} {game}';folder.mkdir(parents=True)
            write(folder/'session.json',dict(id=ident,game=c['game'],created=datetime.now().astimezone().isoformat(),state='待开始',settings=session_settings(c),test=bool(test_file),audio_layout={'track1':'游戏与口述混音，仅回放','track2':'独立口述，唯一转写输入','ffmpeg_map':'0:a:1'}))
            s=cls(folder);s.update(state='启动中')
            try:
                from input_capture import prepare_capture
                s._input_capture=prepare_capture(c,folder,root=ROOT)
                if s._input_capture is not None:
                    try:s._input_clock_events=_InputClockEvents(r)
                    except Exception:pass
                r.send('SetRecordDirectory',{'recordDirectory':str(folder)})
                s.update(state='录制中',started=time.time())
                r.start_record()
                for _ in range(100):
                    before=time.perf_counter()
                    state=r.get_record_status()
                    after=time.perf_counter()
                    if state.output_active:break
                    time.sleep(0.1)
                else:raise RuntimeError('OBS 尚未确认录制状态，请在场次列表恢复后检查。')
                if s._input_capture is not None:
                    try:
                        state,before,after=s.await_input_clock(r,state,before,after)
                        s._video_seconds=s.output_seconds(state)
                        if not s.observe_input_clock(state,before,after):
                            return s
                        s._input_capture.start(origin=(before+after)/2,video_offset=s._video_seconds)
                        s.update(input_state='recording',input_clock={'basis':'OBS output_duration','initial_seconds':s._video_seconds,'last_verified_seconds':s._video_seconds,'uncertainty_seconds':(after-before)/2})
                    except Exception:
                        s.finish_inputs(s._video_seconds,error='操作采集启动失败或无法取得录像时钟；录像仍在继续。')
                        s.update(warning='操作采集未能启动，录像仍在继续。')
            except Exception as e:
                s.finish_inputs(s._video_seconds,interrupted=True,error='录制启动未确认，操作采集已停止。')
                s.update(state='失败',error=str(e));raise
            return s
    def stop(self):
        with obs_connection(False) as r:
            directory=Path(r.send('GetRecordDirectory').record_directory)
            if directory.resolve()!=self.path.resolve():raise RuntimeError('OBS 录制目录不属于本场次，已拒绝停止其他录制。')
            before=time.perf_counter()
            status=r.get_record_status()
            after=time.perf_counter()
            self.observe_input_clock(status,before,after)
            try:self._video_seconds=self.output_seconds(status)
            except RuntimeError:pass
            # Stop listeners before a stop request can block or lose acknowledgement.
            self.finish_inputs(self._video_seconds)
            if status.output_active:
                self.update(state='保存中')
                # Native listener shutdown and sidecar flush may take seconds.
                # Take this boundary immediately before the actual request.
                stop_before=time.perf_counter()
                try:
                    output=Path(r.stop_record().output_path)
                    self.update(recording_file=output.name)
                    for _ in range(120):
                        if not r.get_record_status().output_active:break
                        time.sleep(0.5)
                    else:raise RuntimeError('OBS 尚未完成停止，请稍后重试。')
                    if self._input_clock_events is not None:
                        self._input_stop_boundary=self._input_clock_events.boundary(stop_before)
                finally:self.close_input_clock_events()
            else:self.close_input_clock_events()
            self.adopt_recording()
            # Release capture devices after recording; a later session rebuilds them.
            for item in r.get_input_list().inputs:r.remove_input(item['inputName'])
            self.prepare_video()
    def adopt_recording(self):
        raw=self.path/'原始录像.mkv'
        if not raw.exists():
            files=sorted(self.path.glob('*.mkv'),key=lambda p:p.stat().st_mtime)
            if not files:raise RuntimeError('尚未找到录像；如果 OBS 仍在录制，请先结束。')
            src=files[-1]
            # The stop response completes finalization; additionally require stable size.
            size=-1
            for _ in range(30):
                new=src.stat().st_size
                if new==size and new>0:break
                size=new;time.sleep(1)
            else:raise RuntimeError('录像仍在写入，稍后重试。')
            for _ in range(60):
                try:src.rename(raw);break
                except PermissionError:time.sleep(0.5)
            else:raise RuntimeError('录像文件仍被占用，请稍后恢复整理。')
        data=probe(raw)
        source=raw
        if data['duration']<=0 and data['audio']>=2 and data['video']==1:
            # Interrupted MKV may lack final duration metadata. Never rewrite the source.
            recovered=self.path/'恢复录像.mkv'
            run(['-i',raw,'-map','0','-c','copy',recovered],self.path/'处理日志.txt')
            data=probe(recovered);source=recovered
        if data['audio']<2 or data['video']!=1 or data['duration']<=0:raise RuntimeError('录像缺少画面或独立口述音轨，已保留原文件。')
        self.update(state='待整理',media=data,processing_source=source.name)
    def prepare_video(self,progress=lambda text:None):
        p=self.path;duration=self.meta['media']['duration'];video=p/'录像.mp4'
        # Published playback media is immutable during retranscription, including
        # while a native viewer holds it open. Only the first remux publishes it.
        if video.is_file():
            info=probe(video)
        else:
            progress('生成可回看的 MP4，保留原始 MKV…')
            self.update(step='生成回看录像')
            source=p/self.meta.get('processing_source','原始录像.mkv')
            run(['-i',source,'-map','0:v:0','-map','0:a:0','-c','copy','-movflags','+faststart',p/'录像.pending.mp4'],p/'处理日志.txt')
            info=probe(p/'录像.pending.mp4')
            if abs(info['duration']-duration)>0.5:raise RuntimeError('回看录像与原始录像时长不一致。')
            os.replace(p/'录像.pending.mp4',video)
        if abs(info['duration']-duration)>0.5:raise RuntimeError('回看录像与原始录像时长不一致。')
        self.calibrate_input_clock(video)
        # Listeners stop before OBS finalization. Explicitly show the short tail
        # rather than representing unobserved final frames as "no input".
        inputs=p/'input-events.json'
        if inputs.is_file() and self._input_capture is None:
            try:
                data=read(inputs)
                observed=float(data.get('duration',0))
                measured=self.meta.get('input_alignment') or {}
                offset=measured.get('offset_seconds',0) if measured.get('method')=='final_video_stop_boundary_v1' else 0
                raw_end=max(0,duration-offset)
                if data.get('state') in ('complete','failed','interrupted') and raw_end>observed+.001:
                    reason='操作采集已结束，录像正在完成保存' if data.get('state')=='complete' else '操作采集中断，此区间没有可靠操作数据'
                    data.setdefault('gaps',[]).append(dict(start=observed,end=raw_end,type='capture',reason=reason))
                    data['duration']=raw_end
                    write(inputs,data)
            except (OSError,ValueError,TypeError):pass
        self.update(video_ready=True)
        if not (p/'复盘.md').exists():(p/'复盘.md').write_text('# 复盘\n\n## 回看记录\n\n## Insight\n\n## 待验证\n\n',encoding='utf-8')
        try:
            transcript=read(p/'录像.whisper.json')['segments'] if (p/'录像.whisper.json').is_file() else []
            if not isinstance(transcript,list):raise ValueError('逐字稿条目无效')
            valid_segments(transcript,duration)
        except (OSError,ValueError,TypeError,KeyError,RuntimeError):
            # The old bytes were archived by process() before retranscription.
            # A corrupt old transcript must not prevent generating a successor.
            transcript=[]
        make_player(p,self.meta,transcript)
    @session_lock
    def process(self,progress=lambda text:None,transcription_settings=None):
        try:
            selected=transcription_settings if transcription_settings is not None else self.meta['settings']
            if selected.get('transcription_provider')=='later':
                raise RuntimeError('当前为仅录制模式。请选择本地或云端转写方式后再整理。')
            if transcription_settings is not None:
                previous=dict(self.meta)
                if (self.path/'录像.whisper.json').exists():
                    version=self.path/'转写版本'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
                    version.mkdir(parents=True)
                    for name in ['session.json','录像.whisper.json','录像.srt','逐字稿.md','独立回看.html','场次说明.md']:
                        src=self.path/name
                        if src.exists():shutil.copy2(src,version/name)
                    write(version/'版本说明.json',{'model':previous.get('transcription',{}).get('model',previous['settings'].get('model')),'provider':previous['settings'].get('transcription_provider','local'),'cache':previous.get('transcription_cache','转写原始'),'reason':'重新转写前保留的版本'})
                    (version/'旧版打开说明.md').write_text('# 旧版逐字稿\n\n此目录保留重新转写前的文字与设置。[原场次录像](../../录像.mp4)和[复盘](../../复盘.md)仍在场次目录。\n\n[查看旧版逐字稿](逐字稿.md)。原始分段结果的位置记录在“版本说明.json”中。\n',encoding='utf-8')
                    progress('旧版逐字稿已保留，开始重新转写…')
                self.update(settings=session_settings(transcription_settings))
            self.update(step='检查原始录像');self.adopt_recording();self.update(state='转写中',transcription_state='pending',error=None)
            p=self.path;log=p/'处理日志.txt';duration=self.meta['media']['duration']
            source=p/self.meta.get('processing_source','原始录像.mkv')
            self.prepare_video(progress)
            progress('提取独立口述音轨（保留静音与时间位置）…')
            self.update(step='提取口述音轨')
            run(['-i',source,'-map','0:a:1','-af','aresample=16000:async=1:first_pts=0','-ac','1','-c:a','flac',p/'口述.flac'],log)
            from transcription_runtime import profile,prepare_gpu_runtime
            options=profile(self.meta['settings'])
            identity={'options':options,'audio_sha256':sha256(p/'口述.flac')}
            fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
            chunks=p/'转写原始'/fingerprint;chunks.mkdir(parents=True,exist_ok=True);all_segments=[]
            write(chunks/'配置.json',identity)
            self.update(transcription=options,transcription_cache=chunks.relative_to(p).as_posix())
            silent_microphone=microphone_is_silent(p/'口述.flac')
            warning='麦克风音轨全程静音，录像可以回看，但没有口述文字。请检查麦克风静音键，并在首次设置中选择正确的麦克风。' if silent_microphone else ''
            audio_check={'digital_silence':silent_microphone,'transcription_skipped':silent_microphone}
            write(chunks/'口述音轨检查.json',audio_check)
            self.update(audio_check=audio_check)
            if silent_microphone:
                progress(warning)
            elif options.get('provider')=='qwen':
                from qwen_transcription import transcribe
                from secret_store import load_key
                self.update(step='Qwen 录音转写')
                all_segments=transcribe(p/'口述.flac',chunks,options,duration,progress,load_key(options['region']))
            else:
                from model_manager import ModelManager
                model_path=ModelManager(ROOT).resolve_model()
                if not model_path:raise RuntimeError('本地模型尚未就绪。请在“转写与模型”下载模型，或导入已有 large-v3 文件夹并完成校验。')
                if options['device']=='cuda':prepare_gpu_runtime()
                from faster_whisper import WhisperModel
                self.update(step='加载离线转写模型')
                progress('加载离线转写模型：'+options['model']+'…')
                model=WhisperModel(str(model_path),device=options['device'],compute_type=options['compute_type'],cpu_threads=8,local_files_only=True)
                # Bounded ten-minute chunks prevent multi-hour audio from loading into RAM.
                for index,offset in enumerate(range(0,int(duration)+1,600)):
                    if duration-offset<0.02:break
                    result=chunks/f'{index:04}.json'
                    if result.exists():segments=read(result)['segments']
                    else:
                        self.update(step=f'转写第 {index+1} 段')
                        progress(f'转写 {stamp(offset)} / {stamp(duration)}（离线）…')
                        wav=chunks/'当前片段.wav'
                        run(['-ss',str(offset),'-i',p/'口述.flac','-t','600','-ar','16000','-ac','1',wav],log)
                        import wave,numpy as np
                        with wave.open(str(wav),'rb') as audio:
                            silent=np.max(np.abs(np.frombuffer(audio.readframes(audio.getnframes()),dtype=np.int16).astype(np.int32)),initial=0)<8
                        if silent:
                            segments=[];write(result,{'offset':offset,'segments':segments,'silence':True});wav.unlink(missing_ok=True);continue
                        generated,inf=model.transcribe(str(wav),language=options['language'] or None,task='transcribe',beam_size=options['beam_size'],vad_filter=options['vad_filter'],condition_on_previous_text=options['condition_on_previous_text'],word_timestamps=True,hotwords=options['hotwords'] or None,no_speech_threshold=options['no_speech_threshold'])
                        segments=[]
                        for seg in generated:
                            # The engine jointly checks silence and text confidence; do not
                            # discard recognized speech using silence probability alone.
                            segments.append({'start':round(seg.start+offset,3),'end':round(min(seg.end+offset,duration),3),'text':seg.text,'no_speech_prob':seg.no_speech_prob,'words':[{'start':w.start+offset,'end':w.end+offset,'word':w.word,'probability':w.probability} for w in seg.words or []]})
                        write(result,{'offset':offset,'segments':segments,'model':self.meta['settings']['model'],'language':inf.language})
                        wav.unlink(missing_ok=True)
                    all_segments.extend(segments)
            valid_segments(all_segments,duration)
            write(p/'录像.whisper.json',{'segments':all_segments,'transcription':options})
            (p/'录像.srt').write_text('\n\n'.join(f'{i+1}\n{stamp(s["start"])} --> {stamp(s["end"])}\n{s["text"].strip()}' for i,s in enumerate(all_segments))+'\n',encoding='utf-8')
            (p/'逐字稿.md').write_text('# 口述逐字稿\n\n机器转写未经校对；原话、改口与疑问不转成设计结论。音频是最终依据。\n\n'+(warning+'\n\n' if warning else '')+ '\n\n'.join(f'[{stamp(s["start"])}](录像.mp4#t={s["start"]}) {s["text"]}' for s in all_segments),encoding='utf-8')
            (p/'场次说明.md').write_text(f'# {self.meta["game"]}\n\n场次 ID：`{self.meta["id"]}`\n\n开始：{self.meta["created"]}\n\n录像时长：{stamp(duration)}\n\n[同步回看](录像.mp4) · [[逐字稿]] · [[复盘]]\n\n引用格式：`{self.meta["id"]} @ 00:12:03.200–00:12:18.500`\n\n原始录像.mkv：音轨1 游戏与口述混音；音轨2 独立口述。\n\n口述.flac 保留录制时间位置；录像.mp4 保留画面与混音，无重编码。\n\n自动逐字稿可能漏字、误识别和不精确分句，请结合原声校对。\n',encoding='utf-8')
            if not (p/'复盘.md').exists():(p/'复盘.md').write_text('# 复盘\n\n## 回看记录\n\n## Insight\n\n## 待验证\n\n',encoding='utf-8')
            warning=warning or ('未识别出语音，请检查原声。' if not all_segments else '')
            self.update(state='可回看',transcription_state='ready',segments=len(all_segments),completed=datetime.now().astimezone().isoformat(),warning=warning)
            make_player(p,self.meta,all_segments)
            progress(warning or '可回看')
        except Exception as e:
            error=f'{self.meta.get("step","整理")}：{e}'
            history=self.meta.get('error_history',[]);history.append({'time':datetime.now().astimezone().isoformat(),'error':error})
            self.update(state='失败',transcription_state='failed',error=error,error_history=history)
            if (self.path/'录像.mp4').is_file():
                try:make_player(self.path,self.meta,[])
                except Exception:pass
            raise RuntimeError(error) from e
    @session_lock
    def package(self):
        from session_metadata import metadata_lock
        with metadata_lock(self.path):
            metadata_bytes=(self.path/'session.json').read_bytes()
            metadata=json.loads(metadata_bytes)
        if metadata['state']!='可回看':raise RuntimeError('整理完成后才能打包。')
        folder=self.path;vault=folder.parent.parent;dest=vault/'打包';dest.mkdir(exist_ok=True)
        from review_runtime import render_player,review_payload,input_payload
        transcript=folder/'录像.whisper.json'
        payload=review_payload(folder,metadata,read(transcript)['segments']) if transcript.is_file() else None
        public_inputs=payload['inputs'] if payload is not None else input_payload(folder,metadata)
        input_bytes=json.dumps(public_inputs,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
        target=dest/(metadata['id']+'-'+datetime.now().strftime('%H%M%S')+'.zip');tmp=target.with_suffix('.partial')
        hashes={}
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for src in folder.rglob('*'):
                if src.is_file() and not src.name.endswith(('.tmp','.pending.mp4','.lock')):
                    if src.parent==folder and src.name.startswith('input-events.') and src.name!='input-events.json':
                        # Recovery journals and revocation fences are local-only.
                        continue
                    rel=Path('场次')/folder.name/src.relative_to(folder)
                    if src.name == '独立回看.html' and src.parent == folder:
                        continue
                    if src.name == 'session.json' and src.parent == folder:
                        # Renaming may continue while large media files are being
                        # copied. Metadata, title, and digest share one snapshot.
                        z.writestr(rel.as_posix(),metadata_bytes)
                        hashes[rel.as_posix()]=hashlib.sha256(metadata_bytes).hexdigest()
                    elif src.name=='input-events.json' and src.parent==folder:
                        z.writestr(rel.as_posix(),input_bytes)
                        hashes[rel.as_posix()]=hashlib.sha256(input_bytes).hexdigest()
                    else:
                        digest=hashlib.sha256()
                        with src.open('rb') as source,z.open(rel.as_posix(),'w',force_zip64=True) as output:
                            for block in iter(lambda:source.read(8*1024*1024),b''):
                                output.write(block)
                                digest.update(block)
                        if src.suffix not in ['.md','.txt','.html']:hashes[rel.as_posix()]=digest.hexdigest()
            if payload is not None:
                page = render_player(ROOT,payload)
                z.writestr((Path('场次') / folder.name / '独立回看.html').as_posix(), page)
            z.writestr('校验清单.json',json.dumps(hashes,ensure_ascii=False,indent=2))
            z.writestr('办公室打开说明.md',OFFICE)
        with zipfile.ZipFile(tmp) as z:
            if z.testzip():raise RuntimeError('打包校验失败。')
        os.replace(tmp,target);return target
def sha256(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()
def valid_segments(segments,duration):
    last=-1
    for s in segments:
        if not (0<=s['start']<=s['end']<=duration+0.05 and s['start']>=last):raise RuntimeError('字幕时间轴校验失败。')
        last=s['start']
OFFICE = """# 办公室回看

完整解压 ZIP，在记录器中选择资料库并打开场次回看，也可以双击场次内的“独立回看.html”。网页内已包含播放器资源，无需联网或安装录制、转写引擎。

回看窗口支持多开、点击逐字稿定位录像、空格播放/暂停、方向键前后 15 秒。视频下方可打开资料文件夹并复制路径。直接用浏览器打开网页时，“打开所在文件夹”会复制路径，可粘贴到文件资源管理器。

在“复盘.md”记录自己的复盘与 insight。引用场次 ID + 起止时间。保留原录像、原始转写与手写笔记；没有自动联网或云同步。

迁移时复制完整资料库，再在记录器设置中选择新目录。可将场次文件夹路径交给 agent 分析录像、逐字稿与复盘。
"""

def make_player(p, meta, segments):
    from review_runtime import render_player, review_payload
    temporary=p/('独立回看.html.'+uuid.uuid4().hex+'.tmp')
    temporary.write_text(render_player(ROOT, review_payload(p, meta, segments)), encoding='utf-8')
    os.replace(temporary,p/'独立回看.html')
