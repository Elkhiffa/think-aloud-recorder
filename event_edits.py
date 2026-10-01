"""Local human corrections, independent of immutable agent output and media."""
from copy import deepcopy
import difflib
import hashlib
import json
import re
import time
import uuid

FILE = 'experience-event-edits.json'
MAX_BYTES = 4 * 1024 * 1024
FIELDS = ('start', 'end', 'title', 'summary', 'issue', 'notes')


def editable(event):
    """Older agents put notes inside summary; keep them separately in the editor."""
    pieces = re.split(r'(?:^|\n)\s*备注[：:]\s*', event.get('summary', ''), maxsplit=1)
    return dict(start=event['start'], end=event['end'], title=event['title'],
                summary=pieces[0].strip(), issue=event.get('issue', ''),
                notes='\n'.join(s for s in (pieces[1].strip() if len(pieces) > 1 else '',
                                           event.get('notes', '')) if s))


def _read(folder):
    import agent_protocol as p
    try:
        value = p._load(folder, FILE, MAX_BYTES)
    except FileNotFoundError:
        return dict(version=1, history=[])
    rows = value.get('history')
    if value.get('version') != 1 or not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError('手动校准记录格式无效；请保留文件后检查。')
    for row in rows:
        if (not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in
                ('id', 'event_id', 'base_result_sha256', 'source_revision')) or
                any(not isinstance(row.get(k), dict) or set(row[k]) != set(FIELDS)
                    for k in ('before', 'after'))):
            raise ValueError('手动校准记录格式无效；请保留文件后检查。')
        for fields in (row['before'], row['after']):
            if (not all(p._number(fields[k]) for k in ('start', 'end')) or
                    not all(isinstance(fields[k], str) for k in ('title', 'summary', 'issue', 'notes'))):
                raise ValueError('手动校准记录字段无效。')
    return value


def _revision(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode('utf-8')).hexdigest() if value['history'] else ''


def context(folder):
    """A stable digest fences analysis against edits made after evidence was read."""
    value = _read(folder)
    rows = deepcopy(value['history'])
    for row in rows:
        row['changes'] = {k: dict(before=row['before'][k], after=row['after'][k])
                          for k in FIELDS if row['before'][k] != row['after'][k]}
        row['diff'] = '\n'.join(difflib.unified_diff(
            json.dumps(row['before'], ensure_ascii=False, indent=2).splitlines(),
            json.dumps(row['after'], ensure_ascii=False, indent=2).splitlines(),
            fromfile='修改前', tofile='手动校准后', lineterm=''))
    return dict(revision=_revision(value), history=rows)


def project(folder, result, digest):
    value = _read(folder)
    latest = {row['event_id']: row for row in value['history']
              if row['base_result_sha256'] == digest and row['source_revision'] == result['revision']}
    result = deepcopy(result)
    for event in result['events']:
        event.update(editable(event))
        if event['id'] in latest:
            event.update(latest[event['id']]['after'])
            event['manually_edited'] = True
    result['events'].sort(key=lambda row: row['start'])
    return result, dict(result_sha256=digest, corrections_revision=_revision(value))


def save(folder, request):
    import agent_protocol as p
    from session_metadata import metadata_lock
    if not isinstance(request, dict):
        raise ValueError('事件修改格式无效。')
    with metadata_lock(folder):
        meta, material, revision, _ = p._ready(folder)
        raw = p._load(folder, p.RESULT, p.MAX_RESULT)
        result = p.validate_result(folder, raw, meta, material, revision)
        digest = p._file_hash(p._path(folder, p.RESULT))
        shown, expected = project(folder, result, digest)
        if any(request.get(k) != v for k, v in expected.items()):
            raise ValueError('体验事件已更新，请关闭编辑后重新打开，避免覆盖其他修改。')
        event = next((row for row in shown['events'] if row['id'] == request.get('event_id')), None)
        if event is None:
            raise ValueError('该事件已不存在，请刷新后重试。')
        fields = request.get('fields')
        if not isinstance(fields, dict) or set(fields) != set(FIELDS):
            raise ValueError('请填写事件时间、名称、描述和备注。')
        after = dict(**p._span(fields, material['duration']),
                     title=p._text(fields['title'], 160, '事件名称'),
                     summary=p._text(fields['summary'], 3000, '事件描述'),
                     issue=p._text(fields['issue'], 3000, '问题与感受', empty=True),
                     notes=p._text(fields['notes'], 2000, '备注', empty=True))
        before = {k: event[k] for k in FIELDS}
        if before != after:
            value = _read(folder)
            value['history'].append(dict(id=uuid.uuid4().hex, event_id=event['id'],
                base_result_sha256=digest, source_revision=revision,
                edited_at=time.time(), before=before, after=after))
            if len(value['history']) > 2000 or len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > MAX_BYTES:
                raise ValueError('手动校准历史已达到容量上限；已有修改均已保留。')
            # All result publications use the same metadata lock. Source files
            # may be external, so recheck their revision before committing.
            if p._ready(folder)[2] != revision or p._file_hash(p._path(folder, p.RESULT)) != digest:
                raise ValueError('素材或体验事件已更新，请刷新后重试。')
            p._write(folder, FILE, value)
        return p.preprocessing_status(folder, include_result=True)


def reviewed(folder, candidate):
    """Require an explicit, current reconciliation before a new agent commit."""
    import agent_protocol as p
    revision = _revision(_read(folder))
    if not revision:
        return None
    review = candidate.get('corrections_review')
    if not isinstance(review, dict) or review.get('revision') != revision:
        raise ValueError('存在手动校准或校准已更新。请读取 evidence.manual_corrections 的 diff，重新核对并填写 corrections_review。')
    return dict(revision=revision, summary=p._text(review.get('summary'), 4000, '手动校准采纳说明'))
