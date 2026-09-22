"""Local recording engine. Every session is durable before the first OBS request."""
from pathlib import Path
from datetime import datetime
import json, os, re, shutil, subprocess, time, uuid, zipfile, hashlib
import av
import imageio_ffmpeg
import obsws_python as obs
from obsws_python.error import OBSSDKRequestError
import functools,msvcrt

ROOT=Path(__file__).resolve().parent
FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()
HIDDEN=0x08000000 if os.name=='nt' else 0
PRESETS={'均衡 1080p30':(1920,1080,30),'流畅 1080p60':(1920,1080,60),'省空间 720p30':(1280,720,30)}
SESSION_SETTING_KEYS=('game','language','preset','source','window','monitor','mic',
    'model','device','compute_type','transcription_provider','hotwords','qwen_region','qwen_model')

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
    data = read(session.path / '录像.whisper.json')
    make_player(session.path, session.meta, data['segments'])
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
    c=config()
    try:r=obs.ReqClient(host='127.0.0.1',port=c['port'],password=c['password'],timeout=8)
    except Exception:
        if not launch:raise
        progress('正在启动录制引擎，请稍候…')
        exe=ROOT/'tools/obs/bin/64bit/obs64.exe'
        subprocess.Popen([str(exe),'--portable','--multi','--profile','Experience','--collection','Experience','--minimize-to-tray','--disable-shutdown-check'],cwd=exe.parent,creationflags=HIDDEN)
        for _ in range(45):
            time.sleep(1)
            try:r=obs.ReqClient(host='127.0.0.1',port=c['port'],password=c['password'],timeout=2);break
            except Exception:pass
        else:raise RuntimeError('专用 OBS 未能连接。请查看 tools/obs/config/obs-studio/logs。')
    # Readiness failures must never launch another OBS instance.
    try:wait_obs_ready(r,progress=progress)
    except Exception:
        try:r.disconnect()
        except Exception:pass
        raise
    return r
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
    r=client(progress=progress);ensure_idle(r)
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

class Session:
    def __init__(self,path):self.path=Path(path);self.meta=read(self.path/'session.json')
    def update(self,**kw):self.meta.update(kw);write(self.path/'session.json',self.meta)
    @classmethod
    def start(cls,c,test_file=None):
        r=client();ensure_idle(r)
        vault=Path(c['vault']);vault.mkdir(parents=True,exist_ok=True)
        if shutil.disk_usage(vault).free<5*1024**3:raise RuntimeError('保存盘可用空间不足 5 GB。请清理或更换保存位置。')
        configure_scene(r,c,test_file)
        ident=datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
        game=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',c['game']).strip(' .')[:60] or '自由探索'
        folder=vault/'场次'/f'{ident} {game}';folder.mkdir(parents=True)
        write(folder/'session.json',dict(id=ident,game=c['game'],created=datetime.now().astimezone().isoformat(),state='待开始',settings=session_settings(c),test=bool(test_file),audio_layout={'track1':'游戏与口述混音，仅回放','track2':'独立口述，唯一转写输入','ffmpeg_map':'0:a:1'}))
        s=cls(folder);s.update(state='启动中')
        try:
            r.send('SetRecordDirectory',{'recordDirectory':str(folder)})
            s.update(state='录制中',started=time.time())
            r.start_record()
            for _ in range(100):
                if r.get_record_status().output_active:break
                time.sleep(0.1)
            else:raise RuntimeError('OBS 尚未确认录制状态，请在场次列表恢复后检查。')
        except Exception as e:s.update(state='失败',error=str(e));raise
        return s
    def stop(self):
        r=client(False)
        directory=Path(r.send('GetRecordDirectory').record_directory)
        if directory.resolve()!=self.path.resolve():raise RuntimeError('OBS 录制目录不属于本场次，已拒绝停止其他录制。')
        if r.get_record_status().output_active:
            self.update(state='保存中')
            output=Path(r.stop_record().output_path)
            self.update(recording_file=output.name)
            for _ in range(120):
                if not r.get_record_status().output_active:break
                time.sleep(0.5)
            else:raise RuntimeError('OBS 尚未完成停止，请稍后重试。')
        self.adopt_recording()
        # Release capture devices after recording; a later session rebuilds them.
        for item in r.get_input_list().inputs:r.remove_input(item['inputName'])
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
            self.update(step='检查原始录像');self.adopt_recording();self.update(state='转写中',error=None)
            p=self.path;log=p/'处理日志.txt';duration=self.meta['media']['duration']
            source=p/self.meta.get('processing_source','原始录像.mkv')
            progress('生成可回看的 MP4，保留原始 MKV…')
            self.update(step='生成回看录像')
            run(['-i',source,'-map','0:v:0','-map','0:a:0','-c','copy','-movflags','+faststart',p/'录像.pending.mp4'],log)
            info=probe(p/'录像.pending.mp4')
            if abs(info['duration']-duration)>0.5:raise RuntimeError('回看录像与原始录像时长不一致。')
            os.replace(p/'录像.pending.mp4',p/'录像.mp4')
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
            make_player(p,self.meta,all_segments)
            warning=warning or ('未识别出语音，请检查原声。' if not all_segments else '')
            self.update(state='可回看',segments=len(all_segments),completed=datetime.now().astimezone().isoformat(),warning=warning)
            progress(warning or '可回看')
        except Exception as e:
            error=f'{self.meta.get("step","整理")}：{e}'
            history=self.meta.get('error_history',[]);history.append({'time':datetime.now().astimezone().isoformat(),'error':error})
            self.update(state='失败',error=error,error_history=history);raise RuntimeError(error) from e
    @session_lock
    def package(self):
        if self.meta['state']!='可回看':raise RuntimeError('整理完成后才能打包。')
        folder=self.path;vault=folder.parent.parent;dest=vault/'打包';dest.mkdir(exist_ok=True)
        target=dest/(self.meta['id']+'-'+datetime.now().strftime('%H%M%S')+'.zip');tmp=target.with_suffix('.partial')
        hashes={}
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for src in folder.rglob('*'):
                if src.is_file() and not src.name.endswith(('.tmp','.pending.mp4','.lock')):
                    rel=Path('场次')/folder.name/src.relative_to(folder)
                    if src.name == '独立回看.html' and src.parent == folder:
                        continue
                    z.write(src,str(rel))
                    if src.suffix not in ['.md','.txt','.html']:hashes[rel.as_posix()]=sha256(src)
            transcript = folder / '录像.whisper.json'
            if transcript.is_file():
                from review_runtime import render_player, review_payload
                page = render_player(ROOT, review_payload(folder, self.meta, read(transcript)['segments']))
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
    (p / '独立回看.html').write_text(render_player(ROOT, review_payload(p, meta, segments)), encoding='utf-8')
