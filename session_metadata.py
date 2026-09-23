"""Short cross-process metadata transactions, independent of processing locks."""
from contextlib import contextmanager
from pathlib import Path
import threading
import time
import msvcrt

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


@contextmanager
def metadata_lock(folder):
    folder = Path(folder).resolve()
    with _LOCKS_GUARD:
        local = _LOCKS.setdefault(str(folder), threading.RLock())
    with local, (folder / '.metadata.lock').open('a+b') as handle:
        deadline = time.monotonic() + 5
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('场次信息正在更新，请稍后重试。')
                time.sleep(.01)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def update_metadata(folder, changes):
    from recorder import read, write
    folder = Path(folder).resolve()
    path = folder / 'session.json'
    if path.resolve().parent != folder:
        raise ValueError('场次信息文件已移动。')
    with metadata_lock(folder):
        current = read(path)
        current.update(changes)
        write(path, current)
        return current


def session_title(meta):
    return str(meta.get('session_name') or meta.get('game') or '体验回看')


def rename_session(folder, name):
    if not isinstance(name, str) or len(name) > 100 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError('片段名称最多 100 字，不能包含换行或控制字符。')
    meta = update_metadata(folder, {'session_name': name.strip()})
    return {'session_name': meta['session_name'], 'title': session_title(meta)}
