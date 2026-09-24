"""Manual, unauthenticated GitHub Release updates for this fixed public project."""
from __future__ import annotations
from copy import deepcopy
from functools import total_ordering
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import quote, urljoin, urlsplit
import uuid

import httpx
from app_paths import application_root, installation_root, metadata_path
from update_installer import (UpdateError, MAX_ARCHIVE, acknowledge_start, atomic_json, build_plan,
                              child, extract_package, read_json, reject_reparse, self_check, sha256,
                              write_recovery_entry)

REPOSITORY = 'Elkhiffa/think-aloud-recorder'
API = 'https://api.github.com/repos/' + REPOSITORY + '/releases'
RELEASES = 'https://github.com/' + REPOSITORY + '/releases'
CDN_HOSTS = {'release-assets.githubusercontent.com', 'objects.githubusercontent.com',
             'github-releases.githubusercontent.com'}


@total_ordering
class SemVer:
    def __init__(self, value):
        match = re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
                             r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?'
                             r'(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?', str(value))
        if not match: raise ValueError('Invalid semantic version')
        self.core = tuple(int(match[i]) for i in (1, 2, 3))
        self.pre = tuple(match[4].split('.')) if match[4] else ()
        if any(part.isdigit() and len(part)>1 and part.startswith('0') for part in self.pre):
            raise ValueError('Invalid numeric prerelease identifier')
    def __eq__(self, other):
        if not isinstance(other, SemVer): return NotImplemented
        return (self.core, self.pre) == (other.core, other.pre)
    def __lt__(self, other):
        if not isinstance(other, SemVer): return NotImplemented
        if self.core != other.core: return self.core < other.core
        if not self.pre or not other.pre: return bool(self.pre) and not other.pre
        for left, right in zip(self.pre, other.pre):
            if left == right: continue
            if left.isdigit() and right.isdigit(): return int(left) < int(right)
            if left.isdigit() != right.isdigit(): return left.isdigit()
            return left < right
        return len(self.pre) < len(other.pre)


def tag_version(tag):
    if not isinstance(tag, str): raise ValueError('Invalid tag')
    value = tag[1:] if tag.startswith('v') else tag
    return value, SemVer(value)


def select_release(releases, include_prerelease=False):
    choices = []
    for item in releases:
        if not isinstance(item, dict) or item.get('draft') is not False: continue
        try: value, version = tag_version(item.get('tag_name'))
        except ValueError: continue
        if not include_prerelease and (item.get('prerelease') is not False or version.pre): continue
        choices.append((version, item))
    return max(choices, key=lambda pair:pair[0])[1] if choices else None


def valid_url(url, *, api=False, initial=False):
    try: parsed = urlsplit(url)
    except ValueError: return False
    if parsed.scheme!='https' or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,443): return False
    if api:
        return parsed.hostname=='api.github.com' and parsed.path=='/repos/'+REPOSITORY+'/releases'
    if parsed.hostname=='github.com':
        return parsed.path.startswith('/'+REPOSITORY+'/releases/download/')
    return not initial and parsed.hostname in CDN_HOSTS


def release_assets(release, version):
    base='ExperienceRecorder-'+version+'-windows-x64'
    expected=(base+'.zip',base+'-SHA256SUMS.txt')
    assets=release.get('assets')
    if not isinstance(assets,list):raise UpdateError('该 Release 尚未提供完整的 Windows 软件包。')
    result={}
    for name in expected:
        matching=[a for a in assets if isinstance(a,dict) and a.get('name')==name and a.get('state')=='uploaded']
        if len(matching)!=1:raise UpdateError('该 Release 尚未提供完整的软件包和校验文件。')
        item=matching[0]; url=item.get('browser_download_url',''); size=item.get('size')
        path='/'+REPOSITORY+'/releases/download/'+quote(release['tag_name'],safe='')+'/'+quote(name,safe='')
        if not valid_url(url,initial=True) or urlsplit(url).path!=path or urlsplit(url).query:
            raise UpdateError('发布文件地址不属于本项目的官方 GitHub Release。')
        limit=MAX_ARCHIVE if name.endswith('.zip') else 1024**2
        if type(size) is not int or not 0<size<=limit:raise UpdateError('发布文件大小无效。')
        digest=item.get('digest')
        if digest is not None and (not isinstance(digest,str) or not re.fullmatch('sha256:[0-9a-f]{64}',digest)):
            raise UpdateError('GitHub 文件校验值无效。')
        result[name]=dict(name=name,url=url,size=size,digest=digest[7:] if digest else None)
    return tuple(result[name] for name in expected)


class Cancelled(Exception):pass


class UpdateManager:
    def __init__(self, root, *, client_factory=None):
        reject_reparse(root)
        self.root=application_root(root)
        self.install_root=installation_root(root)
        self.client_factory=client_factory or (lambda:httpx.Client(timeout=httpx.Timeout(30,connect=10),follow_redirects=False,
            headers={'Accept':'application/vnd.github+json','User-Agent':'ThinkAloud-Updater',
                     'X-GitHub-Api-Version':'2026-03-10','Accept-Encoding':'identity'}))
        try:
            version=read_json(metadata_path(self.root))['version'];SemVer(version)
        except (OSError,ValueError,KeyError,TypeError):version='unknown'
        self._state=dict(current_version=version,state='idle',latest_version=None,release_url=None,notes='',
                         downloaded_bytes=0,total_bytes=0,error=None,include_prerelease=False)
        self._lock=threading.RLock();self._cancel=threading.Event();self._thread=None
        self._release=self._assets=self._work=self._stage=None
        self._preparing=False
        self._prepared=None
        self._installer=None
        self._install_lock=threading.Lock()

    def snapshot(self):
        with self._lock:result=deepcopy(self._state)
        try:
            saved=read_json(child(self.root,'state/update-result.json'))
            result['last_install']={key:saved.get(key) for key in ('state','version','message','time','backup_path','recovery_path')}
        except (OSError,ValueError,UpdateError):result['last_install']=None
        return result

    def _set(self,**values):
        with self._lock:self._state.update(values)

    def wait(self,timeout=None):
        thread=self._thread
        if thread and thread is not threading.current_thread():thread.join(timeout)
        return not (thread and thread.is_alive()) and not self._preparing

    def cancel(self):
        self._cancel.set()
        return self.snapshot()

    def _check_cancel(self):
        if self._cancel.is_set():raise Cancelled()

    def _launch(self,state,operation):
        with self._lock:
            if self._preparing or (self._thread and self._thread.is_alive()):raise UpdateError('上一个更新操作尚未结束。')
            self._cancel.clear();self._state.update(state=state,error=None)
            def worker():
                try:operation()
                except Cancelled:self._set(state='available' if self._release else 'idle',error=None)
                except UpdateError as error:self._set(state='error',error=str(error))
                except Exception:self._set(state='error',error='无法完成更新操作，请检查网络、文件权限和磁盘空间后重试。')
            self._thread=threading.Thread(target=worker,name='manual-software-update',daemon=True)
            self._thread.start()
        return self.snapshot()

    def _receive(self,client,url,limit,*,api=False,expected=None,target=None,progress=False):
        destination=url
        for _ in range(6):
            self._check_cancel()
            if not valid_url(destination,api=api):raise UpdateError('更新服务器重定向到了未允许的地址。')
            with client.stream('GET',destination,follow_redirects=False) as response:
                if response.status_code in (301,302,303,307,308):
                    destination=urljoin(destination,response.headers.get('location',''));continue
                if response.status_code!=200:raise UpdateError('GitHub 暂时未能提供更新信息或下载文件，请稍后重试。')
                if response.headers.get('content-encoding','identity')!='identity':raise UpdateError('更新响应采用了不支持的编码。')
                declared=response.headers.get('content-length')
                if declared and (not declared.isdigit() or int(declared)>limit or (expected is not None and int(declared)!=expected)):
                    raise UpdateError('更新响应长度不符合发布信息。')
                chunks=[];count=0;digest=hashlib.sha256()
                handle=Path(target).open('xb') if target else None
                try:
                    for chunk in response.iter_bytes(1024**2):
                        self._check_cancel();count+=len(chunk)
                        if count>limit or (expected is not None and count>expected):raise UpdateError('更新下载超出声明大小。')
                        digest.update(chunk)
                        if handle:handle.write(chunk)
                        else:chunks.append(chunk)
                        if progress:self._set(downloaded_bytes=count)
                    if expected is not None and count!=expected:raise UpdateError('更新下载未完成，原软件未改变。')
                    if handle:handle.flush();os.fsync(handle.fileno())
                finally:
                    if handle:handle.close()
                return digest.hexdigest(),b''.join(chunks)
        raise UpdateError('更新服务器重定向次数过多。')

    def check(self,include_prerelease=False):
        if type(include_prerelease) is not bool:raise UpdateError('预览版本选项无效。')
        def operation():
            self._release=self._assets=self._work=self._stage=None
            self._set(include_prerelease=include_prerelease,latest_version=None,release_url=None,notes='',downloaded_bytes=0,total_bytes=0)
            try:current=SemVer(self._state['current_version'])
            except ValueError:raise UpdateError('无法识别当前版本，请使用完整软件包。') from None
            releases=[]
            with self.client_factory() as client:
                for page in range(1,21):
                    _,body=self._receive(client,API+'?per_page=100&page='+str(page),8*1024**2,api=True)
                    try:items=json.loads(body)
                    except ValueError:raise UpdateError('GitHub 返回的发布信息无效。') from None
                    if not isinstance(items,list):raise UpdateError('GitHub 返回的发布信息无效。')
                    releases.extend(items)
                    if len(items)<100:break
                else:raise UpdateError('发布记录过多，无法完整确认版本。')
            release=select_release(releases,include_prerelease)
            if release is None:
                self._set(state='no_release',notes='尚无可用于此更新通道的 GitHub Release。');return
            version,semantic=tag_version(release['tag_name'])
            release_url=RELEASES+'/tag/'+quote(release['tag_name'],safe='')
            self._set(latest_version=version,release_url=release_url,notes=str(release.get('body') or '')[:50000])
            if semantic<=current:self._set(state='current');return
            assets=release_assets(release,version)
            self._release,self._assets=release,assets
            self._set(state='available',total_bytes=assets[0]['size'])
        return self._launch('checking',operation)

    def download(self):
        if not self._release or not self._assets:raise UpdateError('请先检查并选择可用更新。')
        release,assets=deepcopy(self._release),deepcopy(self._assets)
        def operation():
            base=self.install_root.parent/'.think-aloud-updates'/hashlib.sha256(str(self.install_root).casefold().encode()).hexdigest()[:16]
            reject_reparse(base);work=base/uuid.uuid4().hex;work.mkdir(parents=True)
            if shutil.disk_usage(work).free < assets[0]['size']+32*1024**2:
                raise UpdateError('磁盘空间不足以下载更新包。')
            self._set(downloaded_bytes=0,total_bytes=assets[0]['size'])
            software,sums=assets
            with self.client_factory() as client:
                digest,text=self._receive(client,sums['url'],1024**2,expected=sums['size'])
                if sums['digest'] and sums['digest']!=digest:raise UpdateError('GitHub 校验文件摘要不匹配。')
                matches=[]
                try:
                    for line in text.decode('utf-8').splitlines():
                        match=re.fullmatch(r'([0-9a-fA-F]{64})[ \t]+\*?([^/\\]+)',line)
                        if match and match[2]==software['name']:matches.append(match[1].lower())
                except UnicodeError:raise UpdateError('发布校验文件编码无效。') from None
                if len(matches)!=1:raise UpdateError('发布校验文件未唯一列出所选软件包。')
                if software['digest'] and software['digest']!=matches[0]:raise UpdateError('GitHub 摘要与发布校验文件不一致。')
                partial=work/'package.zip.partial'
                actual,_=self._receive(client,software['url'],MAX_ARCHIVE,expected=software['size'],target=partial,progress=True)
                if actual!=matches[0]:raise UpdateError('更新包校验失败，安装目录未改变。')
            self._check_cancel();archive=work/'package.zip';os.replace(partial,archive)
            stage=work/'package'
            version,_=tag_version(release['tag_name'])
            extract_package(archive,stage,expected_version=version,cancelled=self._cancel.is_set)
            self._check_cancel();self._work,self._stage=work,stage
            self._set(state='ready',error=None)
        return self._launch('downloading',operation)

    def prepare_install(self,parent_pid):
        """May perform disk validation; caller runs this off its UI thread.

        Returns executable/args/cwd/job_path. It does NOT launch or exit the app.
        The caller launches only after safe-close admission; helper waits for the
        original parent handle to signal and all target-directory processes.
        """
        import psutil
        with self._lock:
            if self._state['state']!='ready' or not self._stage or self._preparing:raise UpdateError('更新尚未下载并校验完成。')
            if self._thread and self._thread.is_alive():raise UpdateError('更新校验尚未结束。')
            if type(parent_pid) is not int or parent_pid<=0:raise UpdateError('记录器进程信息无效。')
            if self._installer is not None and self._installer.poll() is None:
                raise UpdateError('上一次安装助手尚未退出，请稍后重试。')
            self._preparing=True
        try:
            self._check_cancel()
            attempt=self._work/('attempt-'+uuid.uuid4().hex)
            attempt.mkdir()
            # This stage has no user configuration. The existing environment
            # self-check may initialize its own disposable portable settings.
            self_check(self._stage,attempt)
            self._check_cancel()
            plan=build_plan(self.root,self._stage,attempt)
            plan.update(parent_pid=parent_pid,parent_created=psutil.Process(parent_pid).create_time())
            atomic_json(attempt/'job.json',plan)
            helper=attempt/'update_installer.py'
            shutil.copy2(Path(__file__).with_name('update_installer.py'),helper)
            # The private helper cannot import code from the install it replaces.
            shutil.copy2(Path(__file__).with_name('app_paths.py'),attempt/'app_paths.py')
            write_recovery_entry(plan)
            executable=application_root(self._stage)/'runtime/pythonw.exe'
            prepared={'executable':str(executable),'args':[str(helper),'--job',str(attempt/'job.json')],
                    'cwd':str(attempt),'job_path':str(attempt/'job.json'),
                    'version':plan['version'],'transaction_id':plan['id']}
            self._prepared=deepcopy(prepared)
            self._installer=None
            return prepared
        finally:
            with self._lock:self._preparing=False

    def _own_prepared(self,prepared):
        if not self._prepared or prepared!=self._prepared:raise UpdateError('安装任务不属于本次更新准备。')
        return Path(prepared['job_path']).parent

    def launch_install(self,prepared):
        """Launch only the private prepared helper; return after its ready fence."""
        from update_installer import HIDDEN
        with self._install_lock:
            work=self._own_prepared(prepared)
            if (work/'cancel.json').exists():raise UpdateError('这次更新安装已取消，请重新准备。')
            if self._installer is not None:raise UpdateError('更新安装助手已启动。')
            self._installer=subprocess.Popen([prepared['executable'],*prepared['args']],cwd=prepared['cwd'],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=HIDDEN)
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            if self._installer.poll() is not None:break
            ready=work/'helper-ready.json'
            if ready.is_file():
                value=read_json(ready)
                if value.get('id')==prepared['transaction_id'] and value.get('pid')==self._installer.pid and value.get('phase')=='waiting_parent':
                    return {'ready':True,'pid':self._installer.pid,'transaction_id':prepared['transaction_id']}
            time.sleep(.05)
        self.cancel_install(prepared)
        raise UpdateError('安装助手未确认就绪，已取消安装并保留当前窗口。')

    def cancel_install(self,prepared):
        work=self._own_prepared(prepared)
        atomic_json(work/'cancel.json',{'schema':1,'id':prepared['transaction_id'],'cancelled':True})
        return {'cancelled':True,'transaction_id':prepared['transaction_id']}
