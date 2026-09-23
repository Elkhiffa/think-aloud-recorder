"""Offline portable-update verifier and external, recoverable installer.

The helper executes from the validated staged runtime, never the runtime it
replaces. It retains backups and its transaction journal; it never kills apps.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import unicodedata
import uuid
import zipfile

MAX_ARCHIVE = 2 * 1024**3
MAX_EXPANDED = 8 * 1024**3
MAX_FILE = 1024**3
MAX_ENTRIES = 30000
MAX_MANIFEST = 16 * 1024**2
MAX_PORTABLE_METADATA = 256 * 1024
REQUIRED = {'portable.json', 'ExperienceRecorder.exe', 'portable_entry.py', 'app.py',
            'runtime/python.exe', 'runtime/pythonw.exe', 'ui/index.html'}
HIDDEN = 0x08000000 if os.name == 'nt' else 0
RECOVERY_ENTRY = '恢复更新前版本.cmd'


class UpdateError(RuntimeError):
    pass


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024**2), b''): digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, allow_nan=False)
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_json(path, limit=MAX_MANIFEST):
    if Path(path).stat().st_size > limit: raise UpdateError('更新元数据过大。')
    try:
        with Path(path).open(encoding='utf-8') as source: return json.load(source)
    except (ValueError, UnicodeError): raise UpdateError('更新元数据格式无效。') from None


def safe_name(name):
    if (not isinstance(name, str) or not name or len(name) > 240 or '\\' in name
            or name.startswith('/') or any(ord(c) < 32 for c in name)):
        raise UpdateError('更新包包含不安全的路径。')
    for part in name.split('/'):
        if (part in ('', '.', '..') or part.endswith((' ', '.')) or any(c in part for c in ':<>"|?*')
                or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part)):
            raise UpdateError('更新包包含不安全的 Windows 路径。')
    if unicodedata.normalize('NFC', name) != name: raise UpdateError('更新包路径编码不规范。')
    return name


def managed_path(name):
    safe_name(name)
    lower = name.casefold()
    if lower.startswith(('state/', 'models/', 'staging/', 'tools/obs/config/')): return False
    if lower.startswith('vocabularies/'): return lower == 'vocabularies/uiux-terms.txt'
    if '/' not in name:
        return lower.endswith('.py') or lower in {'experiencerecorder.exe', 'portable.json',
            'package-manifest.json', 'dependency-source-manifest.json', 'model-manifest.json',
            'requirements-lock.txt', 'license', 'third_party_notices.md', 'readme.md', 'player.html'}
    return lower.startswith(('runtime/', 'ui/', 'licenses/', 'docs/', 'scripts/', 'tools/input/',
                             'tools/obs/bin/', 'tools/obs/data/', 'tools/obs/obs-plugins/')) or lower == 'tools/obs/portable_mode.txt'


def reject_reparse(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if item.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise UpdateError('更新路径包含链接或重解析点，已保留原文件。')


def child(root, relative):
    path = Path(root) / safe_name(relative)
    reject_reparse(path)
    if not path.resolve().is_relative_to(Path(root).resolve()): raise UpdateError('更新路径超出安装目录。')
    return path


def inventory(value):
    if not isinstance(value, dict) or value.get('schema') != 1 or not isinstance(value.get('files'), list):
        raise UpdateError('软件包清单版本不受支持。')
    if not 1 <= len(value['files']) <= MAX_ENTRIES: raise UpdateError('软件包清单数量无效。')
    result, aliases = {}, set()
    for record in value['files']:
        if not isinstance(record, dict): raise UpdateError('软件包清单条目无效。')
        name = safe_name(record.get('path'))
        size, digest = record.get('bytes'), record.get('sha256')
        if (name.casefold() in aliases or not managed_path(name) or name == 'package-manifest.json'
                or type(size) is not int or not 0 <= size <= MAX_FILE
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise UpdateError('软件包清单含重复、受保护或无效文件。')
        aliases.add(name.casefold()); result[name] = {'path': name, 'bytes': size, 'sha256': digest}
    if sum(r['bytes'] for r in result.values()) > MAX_EXPANDED or not REQUIRED <= result.keys():
        raise UpdateError('软件包不完整或展开后过大。')
    return result


def validate_metadata(metadata, manifest, expected_version=None, allow_candidate=False):
    if not isinstance(metadata, dict) or metadata.get('platform') != 'windows-x64':
        raise UpdateError('更新包不是 Windows x64 版本。')
    if not isinstance(metadata.get('version'), str) or (expected_version is not None and metadata['version'] != expected_version):
        raise UpdateError('发布版本与软件包版本不一致。')
    if metadata.get('update_protocol',1) != 1:
        raise UpdateError('该软件包需要更新版本的安装协议，请手动保留配置后安装。')
    if not allow_candidate and (metadata.get('release_status') != 'public' or manifest.get('dependency_source_status') is not True):
        raise UpdateError('该软件包尚未通过公开分发检查，不能作为在线更新安装。')


def extract_package(archive_path, destination, *, expected_version=None, allow_candidate=False, cancelled=lambda: False):
    archive_path, destination = Path(archive_path), Path(destination)
    reject_reparse(archive_path); reject_reparse(destination)
    if archive_path.stat().st_size > MAX_ARCHIVE: raise UpdateError('更新包过大。')
    if destination.exists(): raise UpdateError('更新暂存目录已存在，请重新下载。')
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist(); names, aliases = {}, set()
            if len(infos) > MAX_ENTRIES + 1: raise UpdateError('更新包文件数量过多。')
            for item in infos:
                name = safe_name(item.filename)
                mode = item.external_attr >> 16
                if (item.is_dir() or item.flag_bits & 1 or stat.S_ISLNK(mode)
                        or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                        or (item.external_attr & 0x400) or name.casefold() in aliases
                        or item.file_size > MAX_FILE or not managed_path(name)):
                    raise UpdateError('更新包含重复、链接、加密或受保护条目。')
                aliases.add(name.casefold()); names[name] = item
            if 'package-manifest.json' not in names or names['package-manifest.json'].file_size > MAX_MANIFEST:
                raise UpdateError('更新包缺少有效清单。')
            manifest = json.loads(archive.read('package-manifest.json'))
            records = inventory(manifest)
            if names.keys() != records.keys() | {'package-manifest.json'}: raise UpdateError('更新包内容与清单不一致。')
            if sum(i.file_size for i in infos) > MAX_EXPANDED: raise UpdateError('更新包展开后过大。')
            info, record = names['portable.json'], records['portable.json']
            if info.file_size > MAX_PORTABLE_METADATA or info.file_size != record['bytes']:
                raise UpdateError('更新包版本元数据过大或长度不符。')
            raw_metadata = archive.read('portable.json')
            if hashlib.sha256(raw_metadata).hexdigest() != record['sha256']:
                raise UpdateError('更新包版本元数据校验失败。')
            metadata = json.loads(raw_metadata)
            validate_metadata(metadata, manifest, expected_version, allow_candidate)
            if shutil.disk_usage(destination.parent).free < sum(i.file_size for i in infos) + 16*1024**2:
                raise UpdateError('磁盘空间不足以展开更新包。')
            destination.mkdir(parents=True)
            for name, item in names.items():
                if cancelled(): raise UpdateError('已取消下载，安装目录未改变。')
                path = child(destination, name); path.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256(); count = 0
                with archive.open(item) as source, path.open('xb') as target:
                    for chunk in iter(lambda: source.read(1024**2), b''):
                        if cancelled(): raise UpdateError('已取消下载，安装目录未改变。')
                        count += len(chunk)
                        if count > item.file_size: raise UpdateError('更新包文件长度异常。')
                        digest.update(chunk); target.write(chunk)
                record = records.get(name)
                if count != item.file_size or (record and (count != record['bytes'] or digest.hexdigest() != record['sha256'])):
                    raise UpdateError('更新包文件校验失败，安装目录未改变。')
            return metadata
    except (zipfile.BadZipFile, ValueError, KeyError, UnicodeError):
        raise UpdateError('更新包损坏或格式无效。') from None


def verified_inventory(root):
    root = Path(root); records = inventory(read_json(child(root, 'package-manifest.json')))
    for name, record in records.items():
        path = child(root, name)
        if not path.is_file() or path.stat().st_size != record['bytes'] or sha256(path) != record['sha256']:
            raise UpdateError('已下载的软件文件发生变化，请重新下载。')
    return records


def build_plan(root, stage, work):
    root, stage, work = (Path(p).absolute() for p in (root, stage, work))
    for path in (root, stage, work): reject_reparse(path)
    root, stage, work = (p.resolve() for p in (root, stage, work))
    if stage.is_relative_to(root) or work.is_relative_to(root) or root.is_relative_to(work):
        raise UpdateError('安装助手必须位于目标安装目录之外。')
    old_manifest = child(root, 'package-manifest.json')
    old = inventory(read_json(old_manifest)); new = verified_inventory(stage)
    files, preserved = [], []
    records = dict(new)
    records['package-manifest.json'] = {'path':'package-manifest.json', 'bytes':(stage/'package-manifest.json').stat().st_size,
                                      'sha256':sha256(stage/'package-manifest.json')}
    for name, record in sorted(records.items()):
        target = child(root, name)
        exists = target.exists()
        if exists and not target.is_file(): raise UpdateError('目标软件路径被其他目录占用。')
        previous = sha256(target) if exists else None
        if name == 'vocabularies/uiux-terms.txt' and exists and (name not in old or previous != old[name]['sha256']):
            preserved.append(name); continue
        if exists and name not in old and name != 'package-manifest.json':
            raise UpdateError('新软件文件与安装目录中的个人文件重名，已停止更新。')
        if exists and name in old and previous != old[name]['sha256']:
            raise UpdateError('现有软件文件已被修改，请先保留修改后再更新。')
        if previous != record['sha256']:
            files.append(dict(record, old_sha256=previous, old_bytes=target.stat().st_size if exists else 0))
    need = sum(r['bytes'] + r['old_bytes'] for r in files) + 32 * 1024**2
    if shutil.disk_usage(root).free < need: raise UpdateError('磁盘空间不足以保留更新备份。')
    plan = {'schema':1, 'id':uuid.uuid4().hex, 'root':str(root), 'stage':str(stage), 'work':str(work),
            'state':'prepared', 'files':files, 'preserved':preserved,
            'old_manifest_sha256':sha256(old_manifest),
            'version':read_json(stage/'portable.json')['version'], 'created':time.time()}
    work.mkdir(parents=True, exist_ok=True); atomic_json(work/'job.json', plan)
    return plan


def save_plan(plan):
    atomic_json(Path(plan['work'])/'job.json', plan)


def write_recovery_entry(plan):
    """Create a fixed relative launcher, without interpolating user paths into cmd."""
    work, stage = Path(plan['work']), Path(plan['stage'])
    if stage.resolve() != (work.parent/'package').resolve():
        raise UpdateError('恢复入口需要标准的独立更新目录。')
    path = child(work, RECOVERY_ENTRY)
    script = ('@echo off\r\nsetlocal DisableDelayedExpansion\r\nchcp 65001 >nul\r\n'
              'echo 请先关闭体验记录器和该目录启动的 OBS。恢复过程不会强制结束进程。\r\n'
              '"%~dp0..\\package\\runtime\\python.exe" -B "%~dp0update_installer.py" '
              '--job "%~dp0job.json" --recover --no-launch\r\n'
              'set "RECOVERY_EXIT=%ERRORLEVEL%"\r\n'
              'if "%RECOVERY_EXIT%"=="0" (\r\n'
              '  echo 已恢复更新前版本，可以重新打开体验记录器。备份和报告已保留。\r\n'
              ') else (\r\n'
              '  echo 恢复尚未完成。请确认相关程序已完全退出后重试，并保留此目录。\r\n'
              '  echo 详细结果保存在同目录的 job.json 中。\r\n'
              ')\r\npause\r\nexit /b %RECOVERY_EXIT%\r\n')
    with path.open('x', encoding='utf-8', newline='') as target:
        target.write(script); target.flush(); os.fsync(target.fileno())
    return path


def status(plan, state, message):
    plan['state'] = state; plan['message'] = message; save_plan(plan)
    root = Path(plan['root'])
    recovery = child(Path(plan['work']), RECOVERY_ENTRY)
    atomic_json(child(root, 'state/update-result.json'), {'schema':1, 'id':plan['id'], 'state':state,
        'version':plan['version'], 'message':message, 'transaction':str(Path(plan['work'])/'job.json'),
        'backup_path':str(Path(plan['work'])/'backup'),
        'recovery_path':str(recovery) if recovery.is_file() and state in ('recovery_required','startup_unconfirmed') else None,
        'time':time.time()})


def check_cancelled(plan):
    path=child(Path(plan['work']),'cancel.json')
    if path.exists():
        # An incomplete or malformed cancellation still means do not install.
        raise UpdateError('更新安装已取消，原软件文件未改变。')


_UNCHECKED = object()


def copy_atomic(source, target, expected=_UNCHECKED):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.update-' + uuid.uuid4().hex + '.tmp')
    with source.open('rb') as src, temporary.open('xb') as dst:
        shutil.copyfileobj(src, dst, 1024**2); dst.flush(); os.fsync(dst.fileno())
    # Check immediately before publication, after potentially long copying.
    reject_reparse(target)
    if expected is not _UNCHECKED:
        actual = sha256(target) if target.is_file() else None
        if actual != expected or (target.exists() and not target.is_file()):
            raise UpdateError('替换前发现目标文件已变化，已保留该文件和旧版本备份。')
    if expected is None:
        # Windows rename refuses a destination that appeared since the check.
        # Other platforms use atomic no-clobber linking; tests may run there.
        if os.name=='nt':os.rename(temporary,target)
        else:os.link(temporary,target)
    else:os.replace(temporary, target)


def install_files(plan, after_replace=lambda count: None):
    root, stage, work = (Path(plan[k]) for k in ('root','stage','work'))
    check_cancelled(plan)
    if sha256(child(root,'package-manifest.json')) != plan['old_manifest_sha256']:
        raise UpdateError('安装目录在准备后发生变化，请重新准备更新。')
    # Complete durable backup before the first replacement. Existing backups
    # cannot be overwritten by a retry after an interrupted transaction.
    for record in plan['files']:
        name = record['path']; source, target = child(stage,name), child(root,name)
        if sha256(source) != record['sha256']: raise UpdateError('暂存文件校验失败。')
        current = sha256(target) if target.exists() else None
        if current != record['old_sha256']: raise UpdateError('安装文件在准备后发生变化。')
        if current is not None:
            backup = child(work, 'backup/' + name)
            if backup.exists(): raise UpdateError('备份已存在，请恢复原更新事务。')
            backup.parent.mkdir(parents=True,exist_ok=True)
            with target.open('rb') as src, backup.open('xb') as dst:
                shutil.copyfileobj(src,dst,1024**2);dst.flush();os.fsync(dst.fileno())
            if sha256(backup) != current: raise UpdateError('旧版本备份校验失败。')
    check_cancelled(plan)
    plan['backup_complete'] = True; status(plan,'applying','正在安装已校验的软件文件。')
    for count, record in enumerate(plan['files'], 1):
        # The complete planned file list is durable before any replacement;
        # rollback inspects old/new hashes, not a possibly stale progress index.
        check_cancelled(plan)
        target = child(root,record['path']); source = child(stage,record['path'])
        copy_atomic(source,target,expected=record['old_sha256'])
        if sha256(target) != record['sha256']: raise UpdateError('安装后文件校验失败。')
        after_replace(count)
    status(plan,'files_installed','软件文件已安装，正在检查新版本。')


def rollback(plan):
    root, work = Path(plan['root']), Path(plan['work'])
    if not plan.get('backup_complete'):
        status(plan,'failed','更新尚未替换软件文件；原版本保留。'); return
    status(plan,'rolling_back','正在恢复更新前的软件。')
    conflicts=[]
    for record in reversed(plan['files']):
        target = child(root,record['path']); old = record['old_sha256']
        current = sha256(target) if target.exists() else None
        if current == old: continue
        if current != record['sha256']:
            conflicts.append(record['path']);continue
        if old is None:
            held = child(work,'rollback-new/'+record['path']);held.parent.mkdir(parents=True,exist_ok=True)
            if held.exists(): raise UpdateError('恢复暂存文件已存在，已停止覆盖。')
            os.replace(target,held)
        else:
            backup=child(work,'backup/'+record['path'])
            if not backup.is_file() or sha256(backup)!=old: raise UpdateError('旧版本备份不完整，已停止恢复。')
            copy_atomic(backup,target,expected=record['sha256'])
    if conflicts:
        plan['recovery_conflicts']=conflicts;save_plan(plan)
        raise UpdateError('恢复时保留了额外文件修改；其他可确认的软件文件已恢复，备份和报告保留。')
    status(plan,'rolled_back','新版本未通过检查，已恢复旧版本；备份和报告保留。')


@contextmanager
def file_lock(path):
    import msvcrt
    path=Path(path);reject_reparse(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0)
        try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:raise UpdateError('软件或另一个更新任务仍在运行。') from None
        try:yield
        finally:handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)


def process_running(pid, created=None):
    """Only a signaled Windows process handle proves termination, not an exit code."""
    import ctypes
    from ctypes import wintypes as W
    import psutil
    if os.name!='nt':
        try:
            process=psutil.Process(int(pid))
            return (created is None or abs(process.create_time()-float(created)) <= .01) and process.is_running()
        except psutil.NoSuchProcess:return False
        except psutil.AccessDenied:raise UpdateError('无法确认相关进程是否退出。') from None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
    kernel.CloseHandle.argtypes=[W.HANDLE]
    kernel.GetProcessTimes.argtypes=[W.HANDLE,*([__import__('ctypes').POINTER(W.FILETIME)]*4)]
    kernel.GetProcessTimes.restype=W.BOOL
    handle=kernel.OpenProcess(0x00101000,False,int(pid))
    if not handle:
        if ctypes.get_last_error()==87:return False
        raise UpdateError('无法确认相关进程是否退出。')
    try:
        wait=kernel.WaitForSingleObject(handle,0)
        if wait==0:return False
        if wait==258:
            if created is not None:
                born,ended,kernel_time,user_time=(W.FILETIME() for _ in range(4))
                if not kernel.GetProcessTimes(handle,ctypes.byref(born),ctypes.byref(ended),ctypes.byref(kernel_time),ctypes.byref(user_time)):
                    raise UpdateError('无法确认进程身份。')
                actual=((born.dwHighDateTime<<32)|born.dwLowDateTime)/10000000-11644473600
                if abs(actual-float(created))>.01:return False
            return True
        raise UpdateError('进程退出状态无法确认。')
    finally:kernel.CloseHandle(handle)


def blockers(root):
    import psutil
    root=Path(root).resolve(); result=[]
    for process in psutil.process_iter(['pid','exe','create_time']):
        try:
            executable=process.info.get('exe')
            if executable and Path(executable).resolve().is_relative_to(root) and process_running(process.pid,process.info['create_time']):
                result.append(process.pid)
        except psutil.NoSuchProcess:continue
    return result


def ensure_launch_allowed(root):
    root=Path(root)
    with file_lock(root/'update.lock'):
        path=child(root,'state/update-result.json')
        if path.is_file():
            info=read_json(path)
            if info.get('state') in ('applying','files_installed','rolling_back','recovery_required'):
                entry=info.get('recovery_path')
                if not entry and isinstance(info.get('transaction'),str):
                    candidate=Path(info['transaction']).parent/RECOVERY_ENTRY
                    if candidate.is_file():entry=str(candidate)
                detail=('请关闭相关程序后，双击恢复入口：\n'+entry) if isinstance(entry,str) and entry else '请运行保留的安装助手恢复旧版本后再启动。'
                raise UpdateError('上次更新尚未完成。'+detail)


def acknowledge_start(root):
    path=Path(root)/'state/update-result.json'
    if not path.is_file():return
    info=read_json(path)
    if info.get('state') in ('awaiting_start','startup_unconfirmed'):
        if read_json(Path(root)/'portable.json').get('version')!=info.get('version'):return
        atomic_json(child(root,'state/update-started.json'),{'schema':1,'id':info['id'],'pid':os.getpid(),
                                                          'version':info['version'],'time':time.time()})
        if info['state']=='startup_unconfirmed':
            info.update(state='complete',message='更新完成，新界面已确认启动。',time=time.time())
            atomic_json(path,info)


def self_check(root, work):
    report=Path(work)/'installed-self-check.json'
    process=subprocess.Popen([str(Path(root)/'ExperienceRecorder.exe'),'--self-check','--report',str(report)],
                          cwd=root,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                          creationflags=HIDDEN)
    try:code=process.wait(timeout=120)
    except subprocess.TimeoutExpired:raise UpdateError('环境检查尚未退出，已保留文件；请等待检查进程结束。') from None
    if code or not report.is_file() or read_json(report).get('ok') is not True:
        raise UpdateError('新版本环境检查未通过。')


def validate_job(path):
    path=Path(path).resolve();reject_reparse(path);plan=read_json(path)
    if plan.get('schema')!=1 or not re.fullmatch('[0-9a-f]{32}',str(plan.get('id',''))):raise UpdateError('更新任务无效。')
    if Path(plan.get('work','')).resolve()!=path.parent:raise UpdateError('更新任务归属不匹配。')
    root,stage,work=(Path(plan[k]).resolve() for k in ('root','stage','work'))
    if stage.is_relative_to(root) or work.is_relative_to(root) or root.is_relative_to(work):raise UpdateError('安装助手路径无效。')
    for p in (root,stage,work):reject_reparse(p)
    aliases=set()
    for record in plan['files']:
        name=safe_name(record['path'])
        if not managed_path(name) or name.casefold() in aliases:raise UpdateError('安装任务文件边界无效。')
        aliases.add(name.casefold())
        for key in ('sha256','old_sha256'):
            if record[key] is not None and not re.fullmatch('[0-9a-f]{64}',record[key]):raise UpdateError('安装任务校验值无效。')
    return plan


def run_job(path, *, recover=False, launch=True, parent_timeout=180, checker=self_check):
    plan=validate_job(path);root=Path(plan['root']);work=Path(plan['work'])
    original_state=plan['state']
    recovering=recover or original_state in ('applying','files_installed','rolling_back','recovery_required')
    if Path(__file__).resolve().is_relative_to(root) or Path(os.sys.executable).resolve().is_relative_to(root):
        raise UpdateError('安装助手不能从正在更新的软件目录运行。')
    try:
        with file_lock(root/'update.lock'):
            if not recovering:check_cancelled(plan)
            import psutil
            atomic_json(work/'helper-ready.json',{'schema':1,'id':plan['id'],'pid':os.getpid(),
                'created':psutil.Process().create_time(),'phase':'waiting_parent'})
            deadline=time.monotonic()+parent_timeout
            while plan.get('parent_pid') and process_running(plan['parent_pid'],plan.get('parent_created')):
                if not recovering:check_cancelled(plan)
                if time.monotonic()>deadline:raise UpdateError('记录器尚未完全退出，未替换软件文件。')
                time.sleep(.2)
            if not recovering:check_cancelled(plan)
            with file_lock(root/'app.lock'):
                if not recovering:check_cancelled(plan)
                if blockers(root):raise UpdateError('安装目录的录制引擎或其他进程仍未退出，未替换软件文件。')
                if recovering:
                    rollback(plan);return plan
                if original_state!='prepared':raise UpdateError('该更新任务已执行，请查看结果报告。')
                try:
                    install_files(plan)
                    checker(root,work)
                except Exception:
                    if blockers(root):raise UpdateError('新版本检查进程尚未退出，恢复任务和备份已保留。')
                    rollback(plan)
                    return plan
                status(plan,'awaiting_start' if launch else 'installed','新版本文件及环境检查通过；旧版本备份保留。')
        if launch:
            process=subprocess.Popen([str(root/'ExperienceRecorder.exe')],cwd=root,stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=HIDDEN)
            deadline=time.monotonic()+45
            while time.monotonic()<deadline:
                ack=root/'state/update-started.json'
                if ack.is_file() and read_json(ack).get('id')==plan['id']:
                    status(plan,'complete','更新完成，新界面已确认启动。');return plan
                if process.poll() is not None:break
                time.sleep(.2)
            status(plan,'startup_unconfirmed','新版本已完整安装，但界面尚未确认启动；旧版本备份和恢复任务保留。')
        return plan
    except Exception as error:
        if plan.get('backup_complete') and plan['state'] not in ('rolled_back','complete','installed','startup_unconfirmed'):
            state,message='recovery_required','更新未完成，请使用保留的安装助手恢复；不要删除备份。'
        else:
            state,message='failed',str(error) if isinstance(error,UpdateError) else '更新未完成，原文件和报告保留。'
        status(plan,state,message)
        return plan


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',required=True,type=Path);parser.add_argument('--recover',action='store_true')
    parser.add_argument('--no-launch',action='store_true')
    args=parser.parse_args()
    result=run_job(args.job,recover=args.recover,launch=not args.no_launch)
    return 0 if result['state'] in ('complete','installed','rolled_back') else 1


if __name__=='__main__':raise SystemExit(main())
