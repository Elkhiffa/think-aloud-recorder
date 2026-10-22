"""Library transcript corrections: agents propose, the user confirms, the raw transcript is never rewritten.

`<vault>/transcript-corrections.json` = {version:1, corrections:[...]}. Each correction has id (c001…), from, to,
basis, status (proposed / confirmed / rejected), proposed_by, proposed_at and, once decided, decided_at.
With session_id + ref it fixes one transcript segment; without them it is a term rule for the whole library, and
`exclude` lists segments the rule must leave alone.

Confirmed corrections are applied when results and evidence are read: quotes keep `text` (the transcript) and gain
`corrected_text`. The session revision does not change, so confirming never turns a result stale.
"""
from datetime import datetime
import json
from pathlib import Path
import re

import agent_protocol as protocol
from session_metadata import metadata_lock


FILE = 'transcript-corrections.json'
STATUSES = ('proposed', 'confirmed', 'rejected')
MAX_FILE = 4 * 1024 * 1024
_cache = {}


def _now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def _vault_of(folder):
    folder = Path(folder).resolve()
    return folder.parent.parent if folder.parent.name == '场次' else None


def read(vault):
    path = Path(vault).resolve() / FILE
    if not path.is_file():
        return dict(version=1, corrections=[])
    data = protocol._load(Path(vault).resolve(), FILE, MAX_FILE)
    if data.get('version') != 1 or not isinstance(data.get('corrections'), list):
        raise ValueError(FILE + ' 格式无效。')
    return data


def _confirmed(vault):
    """Confirmed corrections, longest original first so a longer fix wins over a shorter one inside it."""
    path = Path(vault).resolve() / FILE
    try:
        stat = path.stat()
    except OSError:
        return []
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if _cache.get('key') != key:
        rows = [row for row in read(vault)['corrections'] if row.get('status') == 'confirmed']
        _cache.update(key=key, rows=sorted(rows, key=lambda row: -len(row['from'])))
    return _cache['rows']


def _correct(text, session_id, ref, rows):
    if not isinstance(text, str):
        return text
    for row in rows:
        if 'ref' in row:
            if (row['session_id'], row['ref']) != (session_id, ref):
                continue
        elif any((item['session_id'], item['ref']) == (session_id, ref) for item in row.get('exclude', [])):
            continue
        text = text.replace(row['from'], row['to'])
    return text


def project(folder, result):
    """Add corrected_text beside every quote whose confirmed correction changes it; the result is not written."""
    vault = _vault_of(folder)
    rows = _confirmed(vault) if vault else []
    if not rows:
        return result
    session_id = result.get('session_id')
    quotes = [said for item in result.get('instances', []) for said in item.get('said', [])]
    quotes += [ref for event in result.get('events', []) for ref in event.get('evidence', [])
               if ref.get('kind') in ('quote', 'quote_words')]
    for quote in quotes:
        corrected = _correct(quote.get('text'), session_id, quote.get('ref'), rows)
        if corrected != quote.get('text'):
            quote['corrected_text'] = corrected
    return result


def annotate(folder, session_id, segments):
    """Evidence segments: the same corrected_text, so agents quote the confirmed wording."""
    vault = _vault_of(folder)
    rows = _confirmed(vault) if vault else []
    for segment in segments if rows else []:
        corrected = _correct(segment['text'], session_id, segment['id'], rows)
        if corrected != segment['text']:
            segment['corrected_text'] = corrected
    return segments


def _sessions(vault):
    found = {}
    for path in sorted((Path(vault).resolve() / '场次').glob('*/session.json')):
        try:
            ident = json.loads(path.read_text(encoding='utf-8-sig')).get('id')
        except (OSError, ValueError):
            continue
        if isinstance(ident, str) and (path.parent / '录像.whisper.json').is_file():
            found[ident] = path.parent
    return found


def _segments(folder):
    return [(f't{i + 1:06d}', row) for i, row in enumerate(protocol._transcript_rows(folder))]


def hits(vault, row, sessions=None):
    """Every transcript segment the correction would change, with its time and both wordings."""
    sessions = sessions if sessions is not None else _sessions(vault)
    targets = [row['session_id']] if 'ref' in row else sorted(sessions)
    excluded = {(item['session_id'], item['ref']) for item in row.get('exclude', [])}
    found = []
    for session_id in targets:
        if session_id not in sessions:
            continue
        for ref, segment in _segments(sessions[session_id]):
            text = segment.get('text')
            if ('ref' in row and ref != row['ref']) or not isinstance(text, str) or row['from'] not in text:
                continue
            found.append(dict(session_id=session_id, ref=ref, start=segment.get('start'), text=text,
                              corrected=text.replace(row['from'], row['to']),
                              excluded=(session_id, ref) in excluded))
    return found


def _phrase(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or '\n' in value:
        raise ValueError(f'{label}必须是 1–{limit} 字、不含换行的文字。')
    return value


def propose(vault, rows, worker):
    """Add proposals; every row is checked (and must change at least one segment) before anything is written."""
    if not isinstance(rows, list) or not rows:
        raise ValueError('至少需要一条转写修正提议。')
    _phrase(worker, '提议者', 80)
    with metadata_lock(vault):
        data = read(vault)
        sessions = _sessions(vault)
        taken = {(row['from'], row['to'], row.get('session_id'), row.get('ref'))
                 for row in data['corrections'] if row['status'] != 'rejected'}
        numbers = [int(row['id'][1:]) for row in data['corrections'] if re.fullmatch(r'c\d+', row.get('id', ''))]
        added = []
        for item in rows:
            # 路径 3：整理场次的 agent 从上下文认出误转写，提议后交用户确认；提议本身不改任何引用。
            if not isinstance(item, dict):
                raise ValueError('转写修正提议必须是对象。')
            row = dict(id=f'c{max(numbers + [0]) + len(added) + 1:03d}', **{'from': _phrase(item.get('from'), '原文', 40)},
                       to=_phrase(item.get('to'), '改成', 40), basis=_phrase(item.get('basis'), '依据', 300),
                       status='proposed', proposed_by=worker, proposed_at=_now())
            if row['from'] == row['to']:
                raise ValueError('原文和改成相同：' + row['from'])
            if ('session_id' in item) != ('ref' in item):
                raise ValueError('单处修正要同时给出 session_id 和 ref；全库规则两者都不写。')
            if 'ref' in item:
                if item['session_id'] not in sessions:
                    raise ValueError('场次不存在或还没有逐字稿：' + str(item['session_id']))
                row.update(session_id=item['session_id'], ref=item['ref'])
            key = (row['from'], row['to'], row.get('session_id'), row.get('ref'))
            if key in taken:
                raise ValueError(f'已有相同的修正：{row["from"]} → {row["to"]}')
            found = hits(vault, row, sessions)
            if not found:
                raise ValueError(f'逐字稿里找不到要改的原文：{row["from"]}')
            taken.add(key)
            added.append(row)
        data['corrections'] += added
        protocol._write(Path(vault).resolve(), FILE, data)
        return [dict(id=row['id'], hits=len(hits(vault, row, sessions)), **{'from': row['from']}, to=row['to'])
                for row in added]


def list_corrections(vault, status='proposed', session_id=None):
    """Corrections with every hit, for the user to read before confirming."""
    if status not in STATUSES + ('all',):
        raise ValueError('状态只能是 proposed、confirmed、rejected 或 all。')
    sessions = _sessions(vault)
    result = []
    for row in read(vault)['corrections']:
        if status != 'all' and row['status'] != status:
            continue
        found = hits(vault, row, sessions)
        if session_id and not any(item['session_id'] == session_id for item in found):
            continue
        result.append(dict(row, hits=found))
    return result


def decide(vault, ids, status):
    """Confirm or reject; a confirmed rule may not give the same original two different corrections."""
    if status not in ('confirmed', 'rejected'):
        raise ValueError('只能确认或驳回。')
    if not ids:
        raise ValueError('至少需要一个修正编号。')
    with metadata_lock(vault):
        data = read(vault)
        index = {row['id']: row for row in data['corrections']}
        for ident in ids:
            # 路径 3：用户在对话里看过全部命中后才确认；任何一个编号不对整批都不写。
            if ident not in index:
                raise ValueError('修正不存在：' + str(ident))
            row = index[ident]
            if status == 'confirmed' and 'ref' not in row:
                clash = [other for other in data['corrections'] if other is not row and other['status'] == 'confirmed'
                         and 'ref' not in other and other['from'] == row['from'] and other['to'] != row['to']]
                if clash:
                    raise ValueError(f'“{row["from"]}”已有确认的全库规则（{clash[0]["id"]}），请先驳回其中一条。')
            row.update(status=status, decided_at=_now())
        protocol._write(Path(vault).resolve(), FILE, data)
        return [index[ident] for ident in ids]


def exclude(vault, ident, session_id, ref):
    """Keep one segment out of a library rule (the transcript there was right)."""
    with metadata_lock(vault):
        data = read(vault)
        row = next((row for row in data['corrections'] if row['id'] == ident), None)
        if row is None or 'ref' in row:
            raise ValueError('全库规则不存在：' + str(ident))
        if not any((item['session_id'], item['ref']) == (session_id, ref) for item in hits(vault, row)):
            raise ValueError(f'这条规则没有命中 {session_id}/{ref}。')
        row.setdefault('exclude', [])
        if dict(session_id=session_id, ref=ref) not in row['exclude']:
            row['exclude'].append(dict(session_id=session_id, ref=ref))
        protocol._write(Path(vault).resolve(), FILE, data)
        return row
