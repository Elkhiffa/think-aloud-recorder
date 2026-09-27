"""Optional, local agent handoff. Recording never waits for an agent.

The ready manifest is published last; a result is one atomic commit. A leased
claim fences late workers. Source revisions deliberately exclude session names,
job state and user notes, so presenting a result cannot enqueue itself again.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

VERSION = 1
READY = 'agent-ready.json'
STATE = 'agent-state.json'
RESULT = 'experience-events.json'
FILES = ('录像.mp4', '口述.flac', '录像.whisper.json',
         'input-events.json', 'input-events.revocation.json')
MAX_RESULT = 2 * 1024 * 1024
_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _path(folder, name):
    folder = Path(folder).resolve()
    path = folder / name
    if path.resolve().parent != folder:
        raise ValueError('接口文件必须位于当前场次内。')
    return path


def _load(folder, name, limit=65536):
    path = _path(folder, name)
    if path.stat().st_size > limit:
        raise ValueError(name + ' 超过大小限制。')
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError(name + ' 必须是 JSON 对象。')
    return data


def _write(folder, name, data):
    path = _path(folder, name)
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)
    tmp = _path(folder, name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with tmp.open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        for attempt in range(40):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(.05)
    finally:
        tmp.unlink(missing_ok=True)


def _number(value):
    return type(value) in (float, int) and math.isfinite(value)


def _text(value, limit, label, empty=False):
    if (not isinstance(value, str) or len(value) > limit or
            (not empty and not value.strip()) or
            any(ord(c) < 32 and c not in '\n\t' for c in value)):
        raise ValueError(label + ' 为空、过长或含无效字符。')
    return value.strip()


def _rows(value, limit, label):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(label + ' 必须是有数量上限的列表。')
    return value


def _span(row, duration):
    if not isinstance(row, dict):
        raise ValueError('时间段必须是对象。')
    start, end = row.get('start'), row.get('end')
    if not (_number(start) and _number(end) and 0 <= start <= end <= duration + .001):
        raise ValueError('证据或事件时间超出录像范围。')
    return dict(start=start, end=min(end, duration))


def _stats(folder, names):
    values = {}
    for name in names:
        path = _path(folder, name)
        try:
            info = path.stat()
            if not path.is_file():
                raise ValueError(name + ' 不是文件。')
            values[name] = dict(bytes=info.st_size, mtime_ns=info.st_mtime_ns)
        except FileNotFoundError:
            values[name] = None
    return values


def _identity(folder, meta=None):
    meta = meta if meta is not None else _load(folder, 'session.json', 1024 * 1024)
    ident = meta.get('id')
    duration = (meta.get('media') or {}).get('duration')
    if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', ident):
        raise ValueError('场次编号无效。')
    if not _number(duration) or duration <= 0:
        raise ValueError('场次时长无效。')
    from review_runtime import input_alignment
    role = meta.get('recorder_speaker')
    role = {k: role.get(k) for k in ('transcript_id', 'speaker_id', 'source')} if isinstance(role, dict) else None
    sources = _stats(folder, FILES)
    material = dict(version=VERSION, id=ident, game=meta.get('game', ''), duration=duration,
                    sources=sources, alignment=input_alignment(meta), recorder_speaker=role)
    revision = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False,
                                        allow_nan=False).encode('utf-8')).hexdigest()
    complete = (meta.get('state') == '可回看' and meta.get('transcription_state') in (None, 'ready')
                and all(sources[name] and sources[name]['bytes'] > 0
                        for name in ('录像.mp4', '录像.whisper.json')))
    return meta, material, revision, complete


def _transcript(folder, duration):
    raw = _load(folder, '录像.whisper.json', 32 * 1024 * 1024)
    rows = _rows(raw.get('segments'), 100000, '逐字稿')
    from speaker_roles import valid_speaker
    result = []
    for i, row in enumerate(rows):
        item = dict(id=f't{i + 1:06d}', **_span(row, duration),
                    text=_text(row.get('text'), 20000, '原话', empty=True))
        item['text'] = row['text']  # Preserve exact text for speaker identity and quotation.
        if valid_speaker(row.get('speaker_id')):
            item['speaker_id'] = row['speaker_id']
        result.append(item)
    return result


def publish_ready(folder):
    """Idempotent explicit publication, also usable to enroll older sessions."""
    from session_metadata import metadata_lock
    with metadata_lock(folder):
        meta, material, revision, complete = _identity(folder)
        if not complete:
            raise ValueError('录像和转写尚未整理完成；不会发布素材就绪信号。')
        # Validate the required structured artifact before advertising readiness.
        segments = _transcript(folder, material['duration'])
        try:
            old = _load(folder, READY)
            if old.get('version') == VERSION and old.get('revision') == revision:
                return old
        except (OSError, ValueError):
            pass
        value = dict(version=VERSION, session_id=meta['id'], revision=revision,
                     published_at=time.time(), timebase='video_seconds',
                     duration_seconds=material['duration'], sources=material['sources'],
                     transcript_segments=len(segments), test=bool(meta.get('test')))
        _write(folder, READY, value)
        return value


def try_publish_ready(folder):
    """Optional integration errors cannot fail ASR, playback or metadata saves."""
    try:
        publish_ready(folder)
        return True
    except Exception:
        # An external worker can inspect/publish again; do not turn this into a
        # recording error or expose implementation details in the recorder UI.
        return False


def _ready(folder):
    meta, material, revision, complete = _identity(folder)
    manifest = _load(folder, READY)
    if (not complete or manifest.get('version') != VERSION or
            manifest.get('session_id') != meta['id'] or manifest.get('revision') != revision):
        raise ValueError('素材已改变或尚未就绪，请重新发布并领取当前版本。')
    return meta, material, revision, manifest


def _normalized_inputs(folder, meta, duration):
    from review_runtime import input_payload
    path = _path(folder, 'input-events.json')
    if path.is_file() and path.stat().st_size > 128 * 1024 * 1024:
        return dict(state='failed', intervals=[], gaps=[], window_states=[],
                    error='操作文件过大，接口未展开；不能据此推断没有操作。')
    inputs = input_payload(folder, meta)
    offset = inputs['alignment']['offset_seconds']
    def shift(row, leading=False):
        start = 0 if leading and row['start'] == 0 else row['start'] + offset
        end = row['end'] + offset
        if end < 0 or start > duration:
            return None
        return {**row, 'start': max(0, start), 'end': min(duration, max(0, end)),
                'source_start': row['start'], 'source_end': row['end']}
    for field in ('intervals', 'gaps', 'window_states'):
        rows = []
        for i, row in enumerate(inputs.get(field, [])):
            shifted = shift(row, field != 'intervals')
            if shifted:
                if field == 'intervals':
                    shifted['source_id'] = shifted.get('id')
                    shifted['id'] = f'i{i + 1:07d}'
                rows.append(shifted)
        inputs[field] = rows
    inputs['timebase'] = 'video_seconds_aligned'
    return inputs


def evidence(folder, start=None, end=None):
    """Summary by default; bounded detailed inputs only for an explicit range."""
    meta, material, revision, manifest = _ready(folder)
    duration = material['duration']
    if start is not None or end is not None:
        if start is None or end is None:
            raise ValueError('请同时提供时间段的开始与结束。')
        _span(dict(start=start, end=end), duration)
        if end - start > 600:
            raise ValueError('每次最多读取 10 分钟的操作证据。')
    segments = _transcript(folder, duration)
    inputs = _normalized_inputs(folder, meta, duration)
    from speaker_roles import speaker_payload
    speakers = speaker_payload(folder, meta, segments)
    value = dict(version=VERSION, session_id=meta['id'], revision=revision,
                 title=meta.get('session_name') or meta.get('game') or meta['id'],
                 test=bool(meta.get('test')), duration_seconds=duration,
                 timebase='video_seconds', speakers=speakers,
                 paths={name: str(_path(folder, name)) for name in FILES if material['sources'][name]},
                 transcript=segments, inputs={k: inputs[k] for k in
                     ('state', 'error', 'alignment', 'recording_scope', 'timebase') if k in inputs},
                 coverage=dict(transcript_segments=len(segments),
                               last_transcript_end=max((s['end'] for s in segments), default=None),
                               input_intervals=len(inputs['intervals']), gaps=inputs['gaps'],
                               window_states=inputs['window_states']),
                 cautions=['原话可能误转写；未讲述不等于没有体验问题。',
                           '设备输入不证明游戏收到操作；后台手柄可能有效。',
                           '自动推荐的记录者身份需要核对；原声与画面优先。'])
    if start is not None:
        inside = lambda row: row['end'] >= start and row['start'] <= end
        value['range'] = dict(start=start, end=end)
        value['transcript'] = [s for s in segments if inside(s)]
        rows = [row for row in inputs['intervals'] if inside(row)]
        value['inputs']['intervals'] = rows[:10000]
        value['inputs']['truncated'] = len(rows) > 10000
        value['inputs']['matching_intervals'] = len(rows)
        for field in ('gaps', 'window_states'):
            value['coverage'][field] = [row for row in inputs[field] if inside(row)]
    # Do not return a mixture when transcription or synchronization changes
    # during a read. The caller can retry with the new ready manifest.
    if _ready(folder)[2] != revision:
        raise ValueError('读取期间素材已更新，请重试。')
    return value


def validate_result(folder, value, meta=None, material=None, revision=None):
    """Validate references and return an allowlisted, display-safe projection."""
    if meta is None:
        meta, material, revision, _ = _ready(folder)
    if not isinstance(value, dict) or type(value.get('version')) is not int or value['version'] != VERSION:
        raise ValueError('不支持的预处理结果版本。')
    if value.get('session_id') != meta['id'] or value.get('revision') != revision:
        raise ValueError('结果不属于当前场次或素材版本。')
    duration = material['duration']
    coverage = value.get('coverage')
    if not isinstance(coverage, dict):
        raise ValueError('请说明实际检查过的素材范围。')
    ranges = [_span(row, duration) for row in _rows(coverage.get('video_ranges'), 1000, '画面检查范围')]
    for key in ('transcript', 'inputs'):
        if coverage.get(key) not in ('full', 'partial', 'none'):
            raise ValueError('请说明逐字稿和操作记录的检查范围。')
    limitations = [_text(s, 1000, '资料限制') for s in _rows(coverage.get('limitations'), 30, '资料限制')]
    transcript = {s['id']: s for s in _transcript(folder, duration)}
    input_rows = None
    events, identifiers, expanded_bytes = [], set(), 0
    for row in _rows(value.get('events'), 300, '体验事件'):
        span = _span(row, duration)
        ident = _text(row.get('id'), 80, '事件编号')
        if ident in identifiers:
            raise ValueError('事件编号重复。')
        identifiers.add(ident)
        if row.get('basis') not in ('explicit', 'observed', 'inferred'):
            raise ValueError('事件需区分明确表达、可见现象和推测。')
        if row.get('kind') not in ('friction', 'positive', 'routine', 'question'):
            raise ValueError('事件类型无效。')
        refs = []
        for item in _rows(row.get('evidence'), 30, '事件证据'):
            if not isinstance(item, dict):
                raise ValueError('证据格式无效。')
            kind = item.get('kind')
            if kind == 'quote':
                quote = transcript.get(item.get('ref')) if isinstance(item.get('ref'), str) else None
                if quote is None or coverage['transcript'] == 'none':
                    raise ValueError('原话引用不存在或未检查逐字稿。')
                ref = dict(kind=kind, ref=quote['id'], start=quote['start'], end=quote['end'], text=quote['text'])
                if 'speaker_id' in quote:
                    ref['speaker_id'] = quote['speaker_id']
            elif kind == 'video':
                ref = dict(kind=kind, **_span(item, duration),
                           text=_text(item.get('observation', item.get('text')), 2000, '画面事实'))
                if not any(r['start'] <= ref['start'] and r['end'] >= ref['end'] for r in ranges):
                    raise ValueError('画面证据不在已检查范围内。')
            elif kind == 'input':
                if coverage['inputs'] == 'none':
                    raise ValueError('未检查操作记录，不能引用操作证据。')
                if input_rows is None:
                    input_rows = {r['id']: r for r in _normalized_inputs(folder, meta, duration)['intervals']}
                source = input_rows.get(item.get('ref')) if isinstance(item.get('ref'), str) else None
                if source is None:
                    raise ValueError('操作引用不存在或已被撤销。')
                ref = dict(kind=kind, ref=source['id'], start=source['start'], end=source['end'],
                           text=str(source.get('label') or source.get('code') or '操作'),
                           device=source.get('device', ''), source_start=source['source_start'], source_end=source['source_end'])
            else:
                raise ValueError('未知证据类型。')
            if ref['start'] < span['start'] - .001 or ref['end'] > span['end'] + .001:
                raise ValueError('证据必须位于它所支持的事件时间段内。')
            expanded_bytes += len(json.dumps(ref, ensure_ascii=False).encode('utf-8'))
            if expanded_bytes > MAX_RESULT:
                raise ValueError('展开证据超过 2 MB，请减少重复引用。')
            refs.append(ref)
        if not refs:
            raise ValueError('每个体验事件至少需要一条可回溯证据。')
        if row['basis'] == 'explicit' and not any(ref['kind'] == 'quote' for ref in refs):
            raise ValueError('明确表达的事件必须引用原话。')
        events.append(dict(id=ident, **span, title=_text(row.get('title'), 160, '事件标题'),
                           summary=_text(row.get('summary'), 3000, '事件描述'),
                           context=_text(row.get('context', ''), 2000, '上下文', empty=True),
                           basis=row['basis'], kind=row['kind'], evidence=refs))
    def related(field, text_key, limit):
        result, ids = [], set()
        for row in _rows(value.get(field, []), limit, field):
            if not isinstance(row, dict):
                raise ValueError('问题或想法格式无效。')
            ident = _text(row.get('id'), 80, '编号')
            if ident in ids or row.get('event_id') not in identifiers | {None}:
                raise ValueError('问题或想法的编号重复，或引用的事件不存在。')
            ids.add(ident)
            result.append(dict(id=ident, event_id=row.get('event_id'),
                               **{text_key: _text(row.get(text_key), 2000, text_key)},
                               reason=_text(row.get('reason'), 2000, '依据')))
        return result
    return dict(version=VERSION, session_id=meta['id'], revision=revision,
                summary=_text(value.get('summary'), 4000, '整理概述'),
                coverage=dict(video_ranges=ranges, transcript=coverage['transcript'],
                              inputs=coverage['inputs'], limitations=limitations),
                events=sorted(events, key=lambda e: e['start']),
                questions=related('questions', 'question', 30), ideas=related('ideas', 'idea', 100))


def _lease_seconds(seconds):
    if type(seconds) is not int or not 60 <= seconds <= 86400:
        raise ValueError('领取有效期需为 60–86400 秒。')
    return seconds


def claim(folder, worker, seconds=1800):
    from session_metadata import metadata_lock
    worker = _text(worker, 160, '处理者名称')
    seconds = _lease_seconds(seconds)
    with metadata_lock(folder):
        meta, material, revision, _ = _ready(folder)
        try:
            result = _load(folder, RESULT, MAX_RESULT)
            if result.get('revision') == revision:
                validate_result(folder, result, meta, material, revision)
                return dict(claimed=False, reason='complete', revision=revision)
        except (OSError, ValueError, TypeError):
            pass
        try:
            old = _load(folder, STATE)
        except (OSError, ValueError):
            old = {}
        if old.get('revision') == revision and old.get('state') == 'processing' and _number(old.get('expires_at')) and old['expires_at'] > time.time():
            return dict(claimed=False, reason='busy', revision=revision, expires_at=old['expires_at'])
        job = dict(version=VERSION, session_id=meta['id'], revision=revision,
                   state='processing', worker=worker, token=uuid.uuid4().hex,
                   updated_at=time.time(), expires_at=time.time() + seconds)
        _write(folder, STATE, job)
        return dict(claimed=True, **job)


def _owned(folder, token):
    meta, material, revision, manifest = _ready(folder)
    job = _load(folder, STATE)
    if (not isinstance(token, str) or not token or job.get('token') != token or
            job.get('revision') != revision or job.get('state') != 'processing' or
            not _number(job.get('expires_at')) or job['expires_at'] <= time.time()):
        raise ValueError('领取已到期、已结束或属于其他处理者，请重新领取。')
    try:
        result = _load(folder, RESULT, MAX_RESULT)
    except (OSError, ValueError):
        result = {}
    receipt = result.get('receipt')
    if result.get('revision') == revision and isinstance(receipt, dict) and receipt.get('token') == token:
        raise ValueError('此任务已经提交，不能再次更改。')
    return meta, material, revision, job


def renew(folder, token, seconds=1800):
    from session_metadata import metadata_lock
    seconds = _lease_seconds(seconds)
    with metadata_lock(folder):
        _, _, _, job = _owned(folder, token)
        job.update(updated_at=time.time(), expires_at=time.time() + seconds)
        _write(folder, STATE, job)
        return job


def fail(folder, token, reason):
    from session_metadata import metadata_lock
    from review_runtime import _safe_error
    reason = _safe_error(_text(reason, 2000, '未完成原因'))
    with metadata_lock(folder):
        _, _, _, job = _owned(folder, token)
        job.update(state='failed', reason=reason, updated_at=time.time(), expires_at=0)
        _write(folder, STATE, job)
        return dict(state='failed', reason=reason)


def submit(folder, token, value):
    from session_metadata import metadata_lock
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')) > MAX_RESULT:
        raise ValueError('预处理结果超过 2 MB。')
    with metadata_lock(folder):
        meta, material, revision, job = _owned(folder, token)
        result = validate_result(folder, value, meta, material, revision)
        # Recheck after potentially expensive evidence validation. No old worker
        # can overwrite a newer lease, even after a filesystem watcher restart.
        _owned(folder, token)
        previous = _path(folder, RESULT)
        if previous.is_file():
            history = Path(folder).resolve() / 'agent-history'
            if history.resolve().parent != Path(folder).resolve():
                raise ValueError('结果历史目录不属于当前场次。')
            history.mkdir(exist_ok=True)
            shutil.copyfile(previous, history / (uuid.uuid4().hex + '.json'))
        result['receipt'] = dict(worker=job['worker'], completed_at=time.time(), token=token)
        if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_RESULT:
            raise ValueError('展开证据后的结果超过 2 MB，请减少重复引用。')
        _write(folder, RESULT, result)
        return dict(state='complete', revision=revision, events=len(result['events']),
                    questions=len(result['questions']), ideas=len(result['ideas']))


def _status(folder, meta):
    meta, material, revision, complete = _identity(folder, meta)
    try:
        marker = _load(folder, READY)
    except FileNotFoundError:
        return dict(state='none')
    has_result = _path(folder, RESULT).exists()
    try:
        job = _load(folder, STATE)
    except FileNotFoundError:
        job = {}
    if not has_result and not job:
        return dict(state='none')
    if not complete or marker.get('revision') != revision or marker.get('version') != VERSION:
        return dict(state='stale', label='需重新预处理', reason='素材已更新，旧整理结果已保留。')
    if has_result:
        raw = _load(folder, RESULT, MAX_RESULT)
        if raw.get('revision') == revision:
            result = validate_result(folder, raw, meta, material, revision)
            return dict(state='complete', label=f'已预处理 · {len(result["events"])} 个事件',
                        events=len(result['events']), questions=len(result['questions']),
                        ideas=len(result['ideas']), result=result)
    if job.get('revision') != revision:
        return dict(state='stale', label='需重新预处理', reason='素材已更新，旧整理结果已保留。')
    if job.get('state') == 'processing':
        if _number(job.get('expires_at')) and job['expires_at'] > time.time():
            return dict(state='processing', label='预处理中', expires_at=job['expires_at'])
        return dict(state='interrupted', label='预处理未完成', reason='处理者未续期，可由外部会话重新领取。')
    return dict(state='failed', label='预处理未完成', reason=str(job.get('reason') or '外部预处理没有完成。')[:2000])


def preprocessing_status(folder, meta=None, include_result=False):
    """Bounded cache: polling never re-reads an unchanged large sidecar."""
    try:
        meta, material, revision, complete = _identity(folder, meta)
        stats = _stats(folder, (READY, STATE, RESULT))
        key = str(Path(folder).resolve())
        signature = json.dumps([revision, complete, stats], sort_keys=True)
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached and cached[0] == signature and cached[1] > time.time():
                value = cached[2]
            else:
                value = None
        if value is None:
            value = _status(folder, meta)
            expiry = value.get('expires_at', time.time() + 86400)
            with _CACHE_LOCK:
                _CACHE[key] = (signature, expiry, value)
                _CACHE.move_to_end(key)
                while len(_CACHE) > 64:
                    _CACHE.popitem(last=False)
        return deepcopy(value if include_result else {k: v for k, v in value.items() if k != 'result'})
    except Exception:
        # Malformed optional output cannot suppress any recording from the UI.
        try:
            attempted = _path(folder, RESULT).exists() or _path(folder, STATE).exists()
        except Exception:
            attempted = False
        return dict(state='invalid', label='预处理结果不可用', reason='结果格式或证据引用无效；原始录像仍可回看。') if attempted else dict(state='none')
