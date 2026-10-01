"""Short cross-process metadata transactions, independent of processing locks."""
from contextlib import contextmanager
from pathlib import Path
import threading
import time
import msvcrt

_LOCKS = {}
_LOCKS_GUARD = threading.Lock()
MAX_SESSION_NAME = 4096


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


def session_naming(meta):
    """Project old combined names into separate fields without editing history.

    Only recorded agent-owned names/suffixes are separated. A manually saved
    title, including brackets, remains exactly the user's title.
    """
    name = str(meta.get('session_name') or '')
    previous = meta.get('activity_naming')
    previous = previous if isinstance(previous, dict) else {}
    manual, automatic = name, ''
    if meta.get('session_name_source') != 'manual':
        if name and name == previous.get('applied_name'):
            manual = str(previous.get('manual_name') or '')
            automatic = str(previous.get('short_title') or '')
        elif previous.get('naming_policy') == 'append-content-v2' and isinstance(previous.get('manual_name'), str) and previous['manual_name']:
            suffix = ' ' + str(previous.get('suggested_name') or '')
            if previous.get('applied_name') == previous['manual_name'] + suffix and name.endswith(suffix):
                manual = name[:-len(suffix)]
    rows = previous.get('activities')
    rows = rows if isinstance(rows, list) else []
    labels = [row['name'] for row in rows
              if isinstance(row, dict) and isinstance(row.get('name'), str) and row['name'].strip()]
    details = ' + '.join(dict.fromkeys(labels))
    if not details and isinstance(previous.get('suggested_name'), str):
        details = previous['suggested_name']
    return dict(manual_name=manual, short_title=automatic,
                session_name=manual or automatic, activity_details=details)


def session_presentation(meta):
    value = session_naming(meta)
    return dict(session_name=value['session_name'],
                title=value['session_name'] or str(meta.get('game') or '体验回看'),
                activity_details=value['activity_details'])


def session_title(meta):
    return session_presentation(meta)['title']


def rename_session(folder, name):
    if not isinstance(name, str) or len(name) > MAX_SESSION_NAME or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise ValueError('片段名称最多 4096 字，不能包含换行或控制字符。')
    meta = update_metadata(folder, {'session_name': name.strip(), 'session_name_source': 'manual'})
    return session_presentation(meta)
