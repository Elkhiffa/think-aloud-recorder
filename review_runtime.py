"""Render desktop and portable reviews from the same local player assets."""
import ctypes
import html
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid
import re
import hashlib
from session_metadata import session_title, rename_session as rename_session_metadata

_LAYOUT_LOCK = threading.Lock()


def _safe_error(value):
    text = str(value or '')[:3000]
    text = re.sub(r'(?i)\b(?:sk|dsk)-[\w-]+', '[已隐藏]', text)
    text = re.sub(r'(?i)(authorization|api[_ -]?key|password|token)\s*[:=]\s*\S+', r'\1=[已隐藏]', text)
    return re.sub(r'https?://\S+\?\S+', '[临时链接已隐藏]', text)


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def input_payload(folder, meta):
    """Only the review schema crosses into HTML; never include raw device data."""
    duration = (meta.get('media') or {}).get('duration', 0)
    duration = duration if _number(duration) and duration >= 0 else 0
    base = dict(version=1, state='disabled', duration=duration, timebase='video_seconds', intervals=[], gaps=[])
    path = Path(folder) / 'input-events.json'
    if not path.exists():
        if (meta.get('settings') or {}).get('record_inputs'):
            base.update(state='interrupted', error='本场次的操作记录尚未保存或已中断。')
        else:
            base['error'] = '本场次未启用操作记录。' if 'record_inputs' in (meta.get('settings') or {}) else '旧场次没有操作记录。'
        return base
    try:
        data = json.loads(contained_file(folder, 'input-events.json').read_text(encoding='utf-8'))
        if (not isinstance(data, dict) or data.get('version') != 1 or data.get('timebase') != 'video_seconds'
                or data.get('state') not in ('complete', 'recording', 'failed', 'interrupted', 'disabled')):
            raise ValueError('操作记录格式不正确。')
        end = data.get('duration')
        if not _number(end) or end < 0:
            raise ValueError('操作记录时长无效。')
        base.update(state=data['state'], duration=end)
        for key in ('intervals', 'gaps'):
            rows = data.get(key, [])
            if not isinstance(rows, list):
                raise ValueError('操作记录条目无效。')
            for row in rows:
                if (not isinstance(row, dict) or not _number(row.get('start')) or not _number(row.get('end'))
                        or not 0 <= row['start'] <= row['end'] <= end + .001):
                    raise ValueError('操作记录时间位置无效。')
                clean = {field: row[field] for field in ('start', 'end')}
                strings = ('id', 'device', 'code', 'label', 'kind', 'direction') if key == 'intervals' else ('type', 'reason')
                for field in strings:
                    if field in row:
                        clean[field] = str(row[field])[:300]
                if key == 'gaps' and row.get('device') in ('keyboard','mouse','xbox','dualsense'):
                    clean['device'] = row['device']
                for field in ('value', 'x', 'y') if key == 'intervals' else ():
                    if field in row and _number(row[field]):
                        clean[field] = row[field]
                if key == 'intervals' and row.get('resumed') is True:
                    clean['resumed'] = True
                base[key].append(clean)
        if data.get('error'):
            base['error'] = _safe_error(data['error'])
        # The durable fence precedes journal/checkpoint cleanup. A crash during
        # cleanup must not let a stale canonical file bypass the same revocation
        # that recovery applies. Only the fixed, contained sidecar may be read.
        from input_capture import _read_revocation
        marker=Path(folder)/'input-events.revocation.json'
        revoked=_read_revocation(marker) if marker.resolve().is_relative_to(Path(folder).resolve()) else 0.
        if revoked is not None and revoked<end:
            for key in ('intervals','gaps'):
                base[key]=[dict(row,end=min(row['end'],revoked)) for row in base[key] if row['start']<revoked]
            base['gaps'].append(dict(start=revoked,end=end,type='capture',reason='前台边界无法确认，不可信操作数据已清除'))
            base.update(state='failed',error='操作记录存在撤销区间，已隐藏不可信数据。')
        return base
    except (OSError, ValueError, TypeError) as error:
        return {**base, 'state': 'failed', 'intervals': [], 'gaps': [], 'error': _safe_error(error)}


def contained_file(folder, name):
    folder = Path(folder).resolve()
    path = (folder / name).resolve()
    if not path.is_relative_to(folder) or not path.is_file():
        raise ValueError('场次文件不存在或不属于此场次：' + name)
    return path


def review_payload(folder, meta, segments, *, desktop=False):
    if not isinstance(segments, list):
        raise ValueError('逐字稿格式不正确，请恢复整理。')
    clean = []
    for row in segments:
        if not isinstance(row, dict):
            raise ValueError('逐字稿条目格式不正确。')
        start, end = row.get('start'), row.get('end')
        if (not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end):
            raise ValueError('逐字稿时间位置无效，请恢复整理。')
        clean.append({'start': start, 'end': end, 'text': str(row.get('text', ''))})
    clean.sort(key=lambda row: row['start'])
    transcription_state = meta.get('transcription_state')
    if transcription_state not in ('pending', 'ready', 'failed'):
        transcription_state = 'failed' if meta.get('state') == '失败' else ('ready' if (Path(folder) / '录像.whisper.json').is_file() else 'pending')
    transcription_error = _safe_error(meta.get('error')) if transcription_state == 'failed' else ''
    if not (Path(folder) / '录像.whisper.json').is_file() and (transcription_state == 'ready' or
            (meta.get('transcription_state') is None and meta.get('state') == '可回看')):
        transcription_state='failed'
        transcription_error='已完成的逐字稿文件缺失，请恢复文件或重新转写；录像仍可回看。'
    return dict(id=str(meta.get('id', Path(folder).name)), title=session_title(meta),
                game=str(meta.get('game', '')), session_name=str(meta.get('session_name') or ''),
                created=str(meta.get('created', '')), test=bool(meta.get('test')),
                vault_path=str(Path(folder).resolve().parent.parent) if desktop else '../..',
                inputs=input_payload(folder, meta),
                transcription={'state': transcription_state, 'error': transcription_error},
                segments=clean, desktop=desktop,
                video=contained_file(folder, '录像.mp4').as_uri() if desktop else '录像.mp4')


def session_review_payload(folder, *, desktop=False):
    from recorder import read
    meta = read(contained_file(folder, 'session.json'))
    transcript = Path(folder) / '录像.whisper.json'
    try:
        if not transcript.is_file() and (meta.get('transcription_state') == 'ready' or
                (meta.get('transcription_state') is None and meta.get('state') == '可回看')):
            raise ValueError('已完成的逐字稿文件缺失，请恢复文件或重新转写；录像仍可回看。')
        segments = read(contained_file(folder, '录像.whisper.json')).get('segments', []) if transcript.is_file() else []
        return review_payload(folder, meta, segments, desktop=desktop)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        # A damaged or interrupted transcript never hides an already published
        # recording. Keep the failure explicit and permit a later snapshot retry.
        meta = {**meta, 'transcription_state': 'failed', 'error': '逐字稿暂不可用：' + _safe_error(error)}
        return review_payload(folder, meta, [], desktop=desktop)


def render_player(root, payload):
    root = Path(root)
    def read(name):
        return (root / name).read_text(encoding='utf-8')
    data = json.dumps(payload, ensure_ascii=False).replace('<', '\\u003c')
    values = {
        'TITLE': html.escape(payload['title']), 'DATA': data,
        'PLYR_CSS': read('ui/vendor/plyr/plyr.css'),
        'PLYR_JS': read('ui/vendor/plyr/plyr.min.js').replace('</script', '<\\/script'),
        'PLYR_SVG': read('ui/vendor/plyr/plyr.svg'),
        'LICENSE': read('licenses/Plyr-MIT.txt').replace('--', '—'),
        'CSS': read('ui/review.css'), 'JS': read('ui/review.js'),
    }
    import re
    return re.sub(r'%%([A-Z_]+)%%', lambda match: values[match[1]], read('player.html'))


def prepare_window(root, session):
    # The processing lock can span hours of transcription. Readers only consume
    # atomically published files, so opening a video never waits on that lock.
    payload = session_review_payload(session.path, desktop=True)
    directory = Path(root) / 'state/reviews'
    directory.mkdir(parents=True, exist_ok=True)
    page = directory / (uuid.uuid4().hex + '.html')
    page.write_text(render_player(root, payload), encoding='utf-8')
    return page, payload


def copy_text(text):
    """Unicode clipboard transfer; ownership moves to Windows only on success."""
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.OpenClipboard.argtypes = [wintypes.HWND]
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.argtypes = [wintypes.HGLOBAL]
    data = (text + '\0').encode('utf-16-le')
    for _ in range(20):
        if user.OpenClipboard(None):
            break
        time.sleep(.025)
    else:
        raise RuntimeError('剪贴板正被其他程序使用，请重试。')
    handle = None
    try:
        handle = kernel.GlobalAlloc(0x0002, len(data))
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())
        ctypes.memmove(pointer, data, len(data))
        kernel.GlobalUnlock(handle)
        if not user.EmptyClipboard() or not user.SetClipboardData(13, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        handle = None
    finally:
        if handle:
            kernel.GlobalFree(handle)
        user.CloseClipboard()


class ReviewAPI:
    """A viewer accesses only its bound session, never recording/settings APIs."""
    def __init__(self, folder, payload, layout_path=None):
        self._folder = Path(folder).resolve()
        self._payload = payload
        self._ready = threading.Event()
        self._error = None
        self._layout_path = Path(layout_path) if layout_path is not None else None

    def _read_layout(self):
        if self._layout_path is None:
            return {}
        try:
            values = json.loads(self._layout_path.read_text(encoding='utf-8'))
            if not isinstance(values, dict):
                return {}
            return {axis: ratio for axis, ratio in values.items()
                    if axis in ('columns', 'rows') and self._valid_ratio(ratio)}
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _valid_ratio(ratio):
        return (type(ratio) in (int, float) and math.isfinite(ratio)
                and .05 <= ratio <= .95)

    def get_layout(self):
        with _LAYOUT_LOCK:
            return {'ok': True, 'data': self._read_layout()}

    def save_layout(self, axis, ratio):
        try:
            if axis not in ('columns', 'rows') or not self._valid_ratio(ratio):
                raise ValueError('回看布局比例无效。')
            if self._layout_path is None:
                raise ValueError('回看布局保存位置尚未就绪。')
            from recorder import write
            with _LAYOUT_LOCK:
                values = self._read_layout()
                values[axis] = ratio
                write(self._layout_path, values)
            return {'ok': True}
        except Exception as error:
            return {'ok': False, 'error': str(error)}

    def ready(self, error=None):
        self._error = str(error)[:500] if error else None
        self._ready.set()
        return {'ok': True}

    def _snapshot_revision(self):
        files=[]
        for name in ('session.json','录像.whisper.json','input-events.json','input-events.revocation.json'):
            try:
                info=(self._folder/name).stat()
                files.append((name,info.st_mtime_ns,info.st_size))
            except FileNotFoundError:
                files.append((name,'missing'))
        # Names are fixed protocol fields; neither native paths nor user content
        # crosses the bridge as part of this inexpensive version fingerprint.
        return hashlib.sha256(json.dumps(files,ensure_ascii=True,separators=(',',':')).encode('utf-8')).hexdigest()

    def get_snapshot(self, known_revision=None):
        try:
            revision=self._snapshot_revision()
            if isinstance(known_revision,str) and known_revision==revision:
                return {'ok': True,'data': {'unchanged': True,'revision': revision}}
            payload = session_review_payload(self._folder, desktop=True)
            # Use the pre-read version. If a publication raced this read, the
            # following poll observes its new stat and cannot cache stale data.
            payload['revision']=revision
            self._payload = payload
            return {'ok': True, 'data': payload}
        except Exception as error:
            return {'ok': False, 'error': _safe_error(error)}

    def rename_session(self, name):
        try:
            contained_file(self._folder, 'session.json')
            return {'ok': True, 'data': rename_session_metadata(self._folder, name)}
        except Exception as error:
            return {'ok': False, 'error': _safe_error(error)}

    def open_folder(self):
        try:
            if not self._folder.is_dir():
                raise ValueError('资料文件夹已移动或不可用。')
            os.startfile(self._folder)
            return {'ok': True}
        except Exception as error:
            return {'ok': False, 'error': str(error)}

    def copy_path(self, kind='folder'):
        try:
            if kind not in ('folder', 'video', 'transcript', 'vault'):
                raise ValueError('未知文件类型。')
            path = self._folder.parent.parent if kind == 'vault' else self._folder if kind == 'folder' else contained_file(
                self._folder, '录像.mp4' if kind == 'video' else '录像.whisper.json')
            copy_text(str(path))
            return {'ok': True}
        except Exception as error:
            return {'ok': False, 'error': str(error)}

    def open_document(self, kind):
        try:
            if kind not in ('notes', 'transcript'):
                raise ValueError('未知文件类型。')
            os.startfile(contained_file(self._folder, '复盘.md' if kind == 'notes' else '逐字稿.md'))
            return {'ok': True}
        except Exception as error:
            return {'ok': False, 'error': str(error)}
