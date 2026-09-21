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

_LAYOUT_LOCK = threading.Lock()


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
    return dict(id=str(meta.get('id', Path(folder).name)), title=str(meta.get('game', '体验回看')),
                created=str(meta.get('created', '')), test=bool(meta.get('test')),
                segments=clean, desktop=desktop,
                video=contained_file(folder, '录像.mp4').as_uri() if desktop else '录像.mp4')


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
    from recorder import read, session_lock
    @session_lock
    def snapshot(owned):
        meta = read(contained_file(owned.path, 'session.json'))
        data = read(contained_file(owned.path, '录像.whisper.json'))
        return review_payload(owned.path, meta, data['segments'], desktop=True)
    payload = snapshot(session)
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
            if kind not in ('folder', 'video', 'transcript'):
                raise ValueError('未知文件类型。')
            path = self._folder if kind == 'folder' else contained_file(
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
