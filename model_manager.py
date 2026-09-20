"""Optional, pinned local models. Construction/status never download or hash weights.

The registry is the activation boundary, shared with transcription workers. A
successful full SHA256 pass records size/mtime; subsequent resolves re-read
the registry and check every file's identity. This is a local integrity cache,
not a signature against malicious edits to both files and registry.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import uuid
from urllib.parse import urlsplit


class _Paused(Exception):
    pass


class ModelManager:
    CHUNK = 256 * 1024
    OVERLAP = 64 * 1024

    def __init__(self, root, *, manifest=None, client_factory=None):
        self.root = Path(root).resolve()
        self.registry = self.root / 'state' / 'models.json'
        if manifest is None:
            manifest = json.loads((self.root / 'model-manifest.json').read_text(encoding='utf-8'))
        self.manifest = json.loads(json.dumps(manifest))
        self._validate_manifest()
        self.files = self.manifest['files']
        self.total = sum(f['bytes'] for f in self.files)
        self._factory = client_factory
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread = None
        self._state = {'state': 'missing', 'model': 'large-v3', 'path': None,
                       'downloaded_bytes': 0, 'total_bytes': self.total,
                       'error': None, 'source': None, 'revision': self.manifest['revision']}

    def _validate_manifest(self):
        m = self.manifest
        if m.get('model') != 'large-v3' or m.get('repository') != 'Systran/faster-whisper-large-v3':
            raise ValueError('模型清单来源无效。')
        if not re.fullmatch(r'[a-f0-9]{40}', m.get('revision', '')):
            raise ValueError('模型清单必须固定到完整版本。')
        names = set()
        if not m.get('files'):
            raise ValueError('模型清单为空。')
        for item in m['files']:
            name = item.get('name', '')
            # Deliberately only flat runtime filenames, no separators, ADS or devices.
            if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name)
                    or name.endswith(('.', ' ')) or name.lower() in names
                    or name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                       *('COM' + str(i) for i in range(1, 10)), *('LPT' + str(i) for i in range(1, 10))}
                    or not isinstance(item.get('bytes'), int) or item['bytes'] <= 0
                    or not re.fullmatch(r'[a-f0-9]{64}', item.get('sha256', ''))):
                raise ValueError('模型清单文件名、大小或校验值无效。')
            names.add(name.lower())

    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    @staticmethod
    def _stats(path):
        s = path.stat()
        if not path.is_file():
            raise ValueError('模型文件不是普通文件。')
        return {'size': s.st_size, 'mtime_ns': s.st_mtime_ns}

    @staticmethod
    def _file(directory, name):
        path = directory / name
        if path.is_symlink() or path.resolve().parent != directory.resolve():
            raise ValueError('模型文件不能指向所选目录外。')
        return path

    def _read_ready(self):
        try:
            entry = json.loads(self.registry.read_text(encoding='utf-8'))
            if (entry.get('schema') != 1 or entry.get('model') != 'large-v3'
                    or entry.get('revision') != self.manifest['revision']):
                return None
            raw = Path(entry['path'])
            if entry.get('relative'):
                if raw.is_absolute() or '..' in raw.parts:
                    return None
                directory = (self.root / raw).resolve()
                if not directory.is_relative_to(self.root):
                    return None
            else:
                if not raw.is_absolute():
                    return None
                directory = raw.resolve()
            records = entry['files']
            if set(records) != {f['name'] for f in self.files}:
                return None
            for item in self.files:
                record = records[item['name']]
                stats = self._stats(self._file(directory, item['name']))
                if (record.get('sha256') != item['sha256'] or stats['size'] != item['bytes']
                        or any(record.get(key) != value for key, value in stats.items())):
                    return None
            return str(directory), entry.get('source', 'import')
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def resolve_model(self):
        ready = self._read_ready()
        return ready[0] if ready else None

    def status(self):
        with self._lock:
            state = dict(self._state)
        if state['state'] in ('missing', 'ready'):
            ready = self._read_ready()
            if ready:
                state.update(state='ready', path=ready[0], source=ready[1],
                             downloaded_bytes=self.total, error=None)
            else:
                state.update(state='missing', downloaded_bytes=0, path=None)
        return state

    def _process_lock(self):
        self.registry.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.registry.parent / 'models.lock', 'a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                if handle.seek(0, 2) == 0:
                    handle.write(b'0')
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except OSError:
            handle.close()
            raise RuntimeError('另一个进程正在下载或校验模型，请稍后再试。')

    def _launch(self, operation, directory, source):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return {'ok': False, 'error': '模型任务仍在运行，请等待或暂停后再操作。'}
            self._cancel.clear()
            self._set(state='downloading' if source == 'download' else 'verifying',
                      path=str(directory), source=source, error=None, downloaded_bytes=0)
            def run():
                handle = None
                try:
                    handle = self._process_lock()
                    operation(directory)
                except _Paused:
                    self._set(state='paused', error=None)
                except Exception as exc:
                    # Do not leak signed redirect URLs or proxy credentials from HTTP exceptions.
                    if type(exc).__module__.startswith(('httpx', 'httpcore')):
                        message = '模型下载连接失败，已有部分已保留，可稍后继续。'
                    else:
                        message = str(exc)
                    self._set(state='error', error=message)
                finally:
                    if handle:
                        handle.close()
            self._thread = threading.Thread(target=run, daemon=True, name='optional-model')
            self._thread.start()
        return {'ok': True, 'data': self.status()}

    def start_download(self, directory=None):
        try:
            path = Path(directory).expanduser().resolve() if directory else self.root / 'models' / 'large-v3'
            return self._launch(self._download, path, 'download')
        except (ValueError, OSError, TypeError) as exc:
            return {'ok': False, 'error': str(exc)}

    def use_existing(self, path):
        try:
            if not path:
                raise ValueError('请选择已有模型目录。')
            directory = Path(path).expanduser().resolve()
            if not directory.is_dir():
                raise ValueError('模型目录不存在。')
            return self._launch(self._import, directory, 'import')
        except (ValueError, OSError, TypeError) as exc:
            return {'ok': False, 'error': str(exc)}

    def pause_download(self):
        self._cancel.set()
        return {'ok': True, 'data': self.status()}

    def wait(self, timeout=None):
        with self._lock:
            thread = self._thread
        if thread:
            thread.join(timeout)
            return not thread.is_alive()
        return True

    def _check_pause(self):
        if self._cancel.is_set():
            raise _Paused()

    def _verify(self, directory, item):
        self._check_pause()
        path = self._file(directory, item['name'])
        before = self._stats(path)
        if before['size'] != item['bytes']:
            raise ValueError('模型文件大小不符：' + item['name'])
        digest = hashlib.sha256()
        with path.open('rb') as source:
            while True:
                self._check_pause()
                block = source.read(self.CHUNK)
                if not block:
                    break
                digest.update(block)
        if before != self._stats(path) or digest.hexdigest() != item['sha256']:
            raise ValueError('模型文件校验失败，原文件已保留：' + item['name'])
        return {**before, 'sha256': item['sha256']}

    def _activate(self, directory, source):
        self._set(state='verifying')
        records = {item['name']: self._verify(directory, item) for item in self.files}
        self._check_pause()
        # Recheck all files after the last hash, before publishing one complete registry.
        for item in self.files:
            stats = self._stats(self._file(directory, item['name']))
            if any(records[item['name']][key] != value for key, value in stats.items()):
                raise ValueError('校验期间模型文件发生变化，请重新导入。')
        relative = directory.is_relative_to(self.root)
        entry = {'schema': 1, 'model': 'large-v3', 'revision': self.manifest['revision'],
                 'source': source, 'path': str(directory.relative_to(self.root) if relative else directory),
                 'relative': relative, 'files': records}
        temp = self.registry.with_name('models.' + uuid.uuid4().hex + '.tmp')
        with temp.open('x', encoding='utf-8') as target:
            json.dump(entry, target, ensure_ascii=False, indent=2)
            target.flush()
            os.fsync(target.fileno())
        self._check_pause()
        os.replace(temp, self.registry)
        self._set(state='ready', downloaded_bytes=self.total, path=str(directory), source=source)

    def _import(self, directory):
        self._activate(directory, 'import')

    @staticmethod
    def _official_request(request):
        url = urlsplit(str(request.url))
        host = url.hostname or ''
        if (url.scheme != 'https' or url.username or url.password or url.port not in (None, 443)
                or not (host == 'huggingface.co' or host.endswith('.huggingface.co')
                        or host == 'hf.co' or host.endswith('.hf.co'))):
            raise ValueError('模型下载重定向不是官方 HTTPS 地址。')

    def _client(self):
        import httpx
        kwargs = {'follow_redirects': True, 'timeout': httpx.Timeout(30, connect=10),
                  'event_hooks': {'request': [self._official_request]},
                  'headers': {'Accept-Encoding': 'identity'}}
        return self._factory(**kwargs) if self._factory else httpx.Client(**kwargs)

    def _download(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        remaining = 0
        progress = 0
        for item in self.files:
            final = self._file(directory, item['name'])
            part = self._file(directory, '.' + item['name'] + '.part')
            if final.exists():
                self._verify(directory, item)
                progress += item['bytes']
            else:
                size = self._stats(part)['size'] if part.exists() else 0
                if size > item['bytes']:
                    raise ValueError('部分文件超过预期大小，请选择新的下载目录：' + item['name'])
                remaining += item['bytes'] - size
                progress += size
        self._set(downloaded_bytes=progress)
        # A little working headroom for registry/filesystem bookkeeping, not a second model copy.
        if shutil.disk_usage(directory).free < remaining + 16 * 1024 * 1024:
            raise ValueError('所选磁盘空间不足，请选择其他下载目录。')
        with self._client() as client:
            for item in self.files:
                self._check_pause()
                final = self._file(directory, item['name'])
                if final.exists():
                    continue
                part = self._file(directory, '.' + item['name'] + '.part')
                offset = self._stats(part)['size'] if part.exists() else 0
                if offset < item['bytes']:
                    progress = self._receive(client, item, part, offset, progress)
                self._set(state='verifying')
                self._verify(directory, {**item, 'name': part.name})
                self._check_pause()
                # Atomic no-clobber promotion. Retain the .part as a hard link, with
                # no duplicate disk allocation; never delete or replace user files.
                try:
                    os.link(part, final)
                except OSError:
                    if os.name != 'nt':
                        raise
                    # exFAT/FAT portable disks lack hard links. Windows rename is
                    # atomic and refuses existing destinations; only this fully
                    # verified completed part is renamed, never an incomplete one.
                    os.rename(part, final)
                self._set(state='downloading')
        self._activate(directory, 'download')

    def _receive(self, client, item, part, offset, progress):
        begin = max(0, offset - self.OVERLAP) if offset else 0
        overlap = offset - begin
        old_tail = b''
        if offset:
            with part.open('rb') as existing:
                existing.seek(begin)
                old_tail = existing.read(overlap)
        headers = {'Range': f'bytes={begin}-'} if offset else {}
        url = ('https://huggingface.co/' + self.manifest['repository'] + '/resolve/'
               + self.manifest['revision'] + '/' + item['name'])
        with client.stream('GET', url, headers=headers) as response:
            if response.status_code != (206 if offset else 200):
                raise ValueError('下载服务器未正确支持此次请求，部分文件已保留。')
            expected = item['bytes'] - begin
            if (response.headers.get('content-encoding', 'identity') != 'identity'
                    or response.headers.get('content-length') != str(expected)):
                raise ValueError('下载响应长度无效，部分文件已保留。')
            if offset and response.headers.get('content-range') != f"bytes {begin}-{item['bytes'] - 1}/{item['bytes']}":
                raise ValueError('续传范围无效，部分文件已保留。')
            if not offset and 'content-range' in response.headers:
                raise ValueError('完整下载返回了意外的局部内容。')
            received = 0
            matched = 0
            with part.open('r+b' if part.exists() else 'xb') as target:
                target.seek(offset)
                for block in response.iter_bytes(self.CHUNK):
                    self._check_pause()
                    received += len(block)
                    if received > expected:
                        raise ValueError('下载响应超出预期长度，部分文件已保留。')
                    if matched < overlap:
                        take = min(len(block), overlap - matched)
                        if block[:take] != old_tail[matched:matched + take]:
                            raise ValueError('续传接点校验失败，部分文件已保留，请选择新的下载目录。')
                        matched += take
                        block = block[take:]
                    if block:
                        target.write(block)
                        target.flush()
                        progress += len(block)
                        self._set(downloaded_bytes=progress)
                target.flush()
                os.fsync(target.fileno())
            if received != expected or matched != overlap:
                raise ValueError('下载不完整，部分文件已保留，可继续下载。')
        return progress
