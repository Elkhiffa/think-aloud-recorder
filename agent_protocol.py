"""Optional, local agent handoff. Recording never waits for an agent.

The ready manifest is published last; a result is one atomic commit. A leased
claim fences late workers. Source revisions deliberately exclude session names,
job state and user notes, so presenting a result cannot enqueue itself again.
"""
from session_metadata import session_title
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
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


def _transcript_rows(folder):
    raw = _load(folder, '录像.whisper.json', 32 * 1024 * 1024)
    return _rows(raw.get('segments'), 100000, '逐字稿')


def _transcript(folder, duration):
    rows = _transcript_rows(folder)
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


def _quote_word_source(rows, ref, duration):
    """Validate one original segment without filtering or renumbering its words."""
    if not isinstance(ref, str) or not re.fullmatch(r't[0-9]{6}', ref):
        raise ValueError('原话引用不存在。')
    index = int(ref[1:]) - 1
    if not 0 <= index < len(rows):
        raise ValueError('原话引用不存在。')
    row = rows[index]
    parent = dict(**_span(row, duration), text=row.get('text'))
    _text(parent['text'], 20000, '原话', empty=True)
    from speaker_roles import valid_speaker
    if valid_speaker(row.get('speaker_id')):
        parent['speaker_id'] = row['speaker_id']
    raw_words = _rows(row.get('words'), 20000, '原话词级时间戳')
    if not raw_words:
        raise ValueError('原话没有可用的词级时间戳，请引用整段原话。')
    words = []
    for i, word in enumerate(raw_words):
        if not isinstance(word, dict):
            raise ValueError('原话词级时间戳格式无效，请引用整段原话。')
        start, end = word.get('start'), word.get('end')
        # Qwen accepts a word at most 50 ms outside its parent sentence. Keep
        # those source times exactly, but never manufacture or clip a timestamp.
        if not (_number(start) and _number(end) and 0 <= start <= end <= duration
                and start >= parent['start'] - .05 - 1e-9
                and end <= parent['end'] + .05 + 1e-9
                and (not words or start >= words[-1]['start'])):
            raise ValueError('原话词级时间戳无效或超出范围，请引用整段原话。')
        token = word.get('word')
        _text(token, 20000, '原话词文本')
        words.append(dict(index=i, start=start, end=end, text=token))
    normalize = lambda text: ''.join(text.split())
    if normalize(''.join(word['text'] for word in words)) != normalize(parent['text']):
        raise ValueError('原话词文本与整段原话不一致，不能确定节选，请引用整段原话。')
    return parent, words


def quote_words(folder, ref, offset=0, limit=80):
    """Read bounded original words for one ref; default evidence stays compact."""
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('词级读取 offset 必须为非负整数，limit 必须为 1–200 的整数。')
    meta, material, revision, _ = _ready(folder)
    parent, words = _quote_word_source(_transcript_rows(folder), ref, material['duration'])
    if offset > len(words):
        raise ValueError('词级读取 offset 超出当前原话的词数。')
    stop = min(offset + limit, len(words))
    value = dict(version=VERSION, session_id=meta['id'], revision=revision,
                 ref=ref, timebase='video_seconds', parent=parent, total=len(words),
                 offset=offset, next_offset=stop if stop < len(words) else None,
                 words=words[offset:stop])
    if _ready(folder)[2] != revision:
        raise ValueError('读取期间素材已更新，请重试。')
    return value


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
                 title=session_title(meta),
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
    from event_edits import context as correction_context
    value['manual_corrections'] = correction_context(folder)
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
    word_rows, word_sources = None, {}
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
            if kind in ('quote', 'quote_words'):
                quote = transcript.get(item.get('ref')) if isinstance(item.get('ref'), str) else None
                if quote is None or coverage['transcript'] == 'none':
                    raise ValueError('原话引用不存在或未检查逐字稿。')
                ref = dict(kind=kind, ref=quote['id'], start=quote['start'], end=quote['end'], text=quote['text'])
                if 'speaker_id' in quote:
                    ref['speaker_id'] = quote['speaker_id']
                if kind == 'quote_words':
                    selected = item.get('word_range')
                    if (not isinstance(selected, list) or len(selected) != 2 or
                            any(type(index) is not int for index in selected)):
                        raise ValueError('原话节选 word_range 必须是两个原始词序号组成的列表。')
                    if quote['id'] not in word_sources:
                        if word_rows is None:
                            word_rows = _transcript_rows(folder)
                        word_sources[quote['id']] = _quote_word_source(word_rows, quote['id'], duration)[1]
                    words = word_sources[quote['id']]
                    first, stop = selected
                    if not 0 <= first < stop <= len(words):
                        raise ValueError('原话节选 word_range 超出原始词范围或为空。')
                    selection = words[first:stop]
                    ref.update(word_range=[first, stop], start=min(word['start'] for word in selection),
                               end=max(word['end'] for word in selection),
                               text=''.join(word['text'] for word in selection))
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
        if row['basis'] == 'explicit' and not any(ref['kind'] in ('quote', 'quote_words') for ref in refs):
            raise ValueError('明确表达的事件必须引用原话。')
        events.append(dict(id=ident, **span, title=_text(row.get('title'), 160, '事件标题'),
                           summary=_text(row.get('summary'), 3000, '事件描述'),
                           context=_text(row.get('context', ''), 2000, '上下文', empty=True),
                            issue=_text(row.get('issue', ''), 3000, '问题与感受', empty=True),
                            notes=_text(row.get('notes', ''), 2000, '备注', empty=True),
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


def _optional_object(folder, name, limit=65536):
    try:
        return _load(folder, name, limit)
    except (OSError, ValueError):
        return {}


def _committed(job, result):
    receipt = result.get('receipt')
    token = job.get('token')
    return (isinstance(token, str) and bool(token) and isinstance(receipt, dict)
            and receipt.get('token') == token)


def _active_lease(job, result):
    # The result receipt is the commit marker; STATE may still say processing.
    return (job.get('state') == 'processing' and _number(job.get('expires_at'))
            and job['expires_at'] > time.time() and not _committed(job, result))


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_result(folder):
    """Preserve exact bytes exclusively and verify them before changing a lease."""
    previous = _path(folder, RESULT)
    history = Path(folder).resolve() / 'agent-history'
    if history.resolve().parent != Path(folder).resolve():
        raise ValueError('结果历史目录不属于当前场次。')
    history.mkdir(exist_ok=True)
    backup = history / (uuid.uuid4().hex + '.json')
    digest, size = hashlib.sha256(), 0
    # Never replace a previous history entry, even if a filename collides.
    with previous.open('rb') as source, backup.open('xb') as target:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            target.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        target.flush()
        os.fsync(target.fileno())
    expected = digest.hexdigest()
    if _file_hash(backup) != expected:
        raise ValueError('旧结果备份校验失败；当前结果与领取状态未更改。')
    return dict(path=str(backup), sha256=expected, bytes=size)


def _baseline_preserved(folder, job):
    baseline = job.get('baseline')
    if not job.get('redo') or not isinstance(baseline, dict):
        return False
    try:
        path = Path(baseline['path']).resolve()
        history = Path(folder).resolve() / 'agent-history'
        if path.parent != history or history.resolve() != history:
            return False
        digest = baseline.get('sha256')
        return _file_hash(path) == digest == _file_hash(_path(folder, RESULT))
    except (KeyError, OSError, TypeError, ValueError):
        return False


def claim(folder, worker, seconds=1800):
    from session_metadata import metadata_lock
    worker = _text(worker, 160, '处理者名称')
    seconds = _lease_seconds(seconds)
    with metadata_lock(folder):
        meta, material, revision, _ = _ready(folder)
        result = _optional_object(folder, RESULT, MAX_RESULT)
        old = _optional_object(folder, STATE)
        if (_active_lease(old, result) and
                (old.get('revision') == revision or old.get('redo'))):
            return dict(claimed=False, reason='busy', revision=revision, expires_at=old['expires_at'])
        try:
            if result.get('revision') == revision:
                validate_result(folder, result, meta, material, revision)
                return dict(claimed=False, reason='complete', revision=revision)
        except (OSError, ValueError, TypeError):
            pass
        job = dict(version=VERSION, session_id=meta['id'], revision=revision,
                   state='processing', worker=worker, token=uuid.uuid4().hex,
                   updated_at=time.time(), expires_at=time.time() + seconds)
        _write(folder, STATE, job)
        return dict(claimed=True, **job)


def reprocess(folder, worker, reason, seconds=1800):
    """Explicitly lease another analysis while the previous result stays readable."""
    from session_metadata import metadata_lock
    from review_runtime import _safe_error
    worker = _text(worker, 160, '处理者名称')
    reason = _safe_error(_text(reason, 2000, '重新分析原因'))
    seconds = _lease_seconds(seconds)
    with metadata_lock(folder):
        meta, _, revision, _ = _ready(folder)
        result = _optional_object(folder, RESULT, MAX_RESULT)
        old = _optional_object(folder, STATE)
        if _active_lease(old, result):
            return dict(claimed=False, reason='busy', revision=revision, expires_at=old['expires_at'])
        if not _path(folder, RESULT).is_file():
            raise ValueError('尚无旧预处理结果，请使用 claim 领取首次分析。')
        baseline = _backup_result(folder)
        now = time.time()
        job = dict(version=VERSION, session_id=meta['id'], revision=revision,
                   state='processing', worker=worker, token=uuid.uuid4().hex,
                   updated_at=now, expires_at=now + seconds, redo=True,
                   redo_reason=reason, baseline=baseline)
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
        from event_edits import reviewed
        correction_review = reviewed(folder, value)
        if correction_review:
            result['corrections_review'] = correction_review
        # Recheck after potentially expensive evidence validation. No old worker
        # can overwrite a newer lease, even after a filesystem watcher restart.
        _owned(folder, token)
        previous = _path(folder, RESULT)
        if previous.is_file() and not _baseline_preserved(folder, job):
            _backup_result(folder)
        result['receipt'] = dict(worker=job['worker'], completed_at=time.time(), token=token)
        if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_RESULT:
            raise ValueError('展开证据后的结果超过 2 MB，请减少重复引用。')
        _write(folder, RESULT, result)
        return dict(state='complete', revision=revision, events=len(result['events']),
                    questions=len(result['questions']), ideas=len(result['ideas']))


def _activity_name_source(folder):
    """Read naming context under the caller's metadata lock; never return settings."""
    meta, material, revision, _ = _ready(folder)
    try:
        raw = _load(folder, RESULT, MAX_RESULT)
    except FileNotFoundError as error:
        raise ValueError('尚无已完成的预处理结果，请先提交体验事件再整理活动类型。') from error
    job = _optional_object(folder, STATE)
    if _active_lease(job, raw):
        raise ValueError('本场次仍在预处理，请完成提交后再整理活动类型。')
    result = validate_result(folder, raw, meta, material, revision)
    digest = _file_hash(_path(folder, RESULT))
    name = meta.get('session_name') or ''
    if not isinstance(name, str):
        raise ValueError('当前场次名称格式无效。')
    previous = meta.get('activity_naming')
    previous = previous if isinstance(previous, dict) else {}
    from session_metadata import session_naming
    manual_name = session_naming(meta)['manual_name']
    if not isinstance(manual_name, str):
        raise ValueError('已保存的手动名称格式无效。')
    return meta, result, dict(version=1, session_id=meta['id'], revision=revision,
                             result_sha256=digest, expected_name=name,
                             naming_policy='separate-title-v3', manual_name=manual_name,
                             can_auto_name=not manual_name,
                             activity_naming=previous)


def name_activities(folder, value=None, *, apply=False):
    """Give completed events a short title and separate, traceable content details.

    The result hash fences reanalysis with unchanged materials; expected_name
    fences concurrent manual edits. The optional projection never rewrites the
    source result, ready marker, lease, media or directory.
    """
    from session_metadata import MAX_SESSION_NAME, metadata_lock
    with metadata_lock(folder):
        meta, result, context = _activity_name_source(folder)
        if value is None:
            if apply:
                raise ValueError('应用活动命名需要 --file 候选文件。')
            return context
        if (not isinstance(value, dict) or type(value.get('version')) is not int
                or value['version'] != 1):
            raise ValueError('不支持的活动命名版本。')
        for key in ('session_id', 'revision', 'result_sha256'):
            if value.get(key) != context[key]:
                raise ValueError('活动命名不属于当前场次、素材或预处理结果，请重新核对。')
        worker = _text(value.get('worker'), 160, '处理者名称')
        expected = value.get('expected_name')
        if not isinstance(expected, str):
            raise ValueError('请提供读取时的 expected_name，未命名时为空字符串。')
        known_events = {event['id'] for event in result['events']}
        activities, seen = [], set()
        for row in _rows(value.get('activities'), 32, '活动类型'):
            if not isinstance(row, dict):
                raise ValueError('活动类型须包含名称和依据事件。')
            name = _text(row.get('name'), 24, '活动类型名称')
            if any(ord(c) < 32 or ord(c) == 127 or c in '+＋【】[]' for c in name):
                raise ValueError('活动类型名称不能包含控制字符、方括号或加号。')
            if name.casefold() in seen:
                raise ValueError('活动类型重复，请合并同义类型并保留全部依据。')
            seen.add(name.casefold())
            refs = _rows(row.get('event_ids'), 300, '活动依据事件')
            if not refs or any(not isinstance(ref, str) or ref not in known_events for ref in refs):
                raise ValueError('每种活动类型至少引用一个当前预处理结果中的事件。')
            activities.append(dict(name=name, event_ids=list(dict.fromkeys(refs))))
        if not activities:
            raise ValueError('暂无有依据的活动类型，请保留未命名并说明资料限制。')
        previous = context['activity_naming']
        # Older callers can still update content labels, but cannot recreate
        # a long combined title. New callers explicitly supply a short title.
        short_title = value.get('title', previous.get('short_title', ''))
        if not isinstance(short_title, str) or len(short_title) > 60 or any(ord(c) < 32 or ord(c) == 127 for c in short_title):
            raise ValueError('概括标题最多60字，不能包含换行或控制字符。')
        short_title = short_title.strip()
        suggested = '【' + '+'.join(row['name'] for row in activities) + '】'
        proposal = dict(version=1, session_id=context['session_id'], revision=context['revision'],
                        result_sha256=context['result_sha256'], expected_name=expected,
                        worker=worker, title=short_title, activities=activities, naming_policy=context['naming_policy'])
        fingerprint = hashlib.sha256(json.dumps(proposal, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        replayed = (previous.get('proposal_sha256') == fingerprint
                    and previous.get('display_name') == context['expected_name']
                    and previous.get('manual_name') == context['manual_name'])
        if expected != context['expected_name'] and not replayed:
            raise ValueError('场次名称已被修改，请重新读取；不会覆盖新的手动名称。')
        manual_name = context['manual_name']
        display_name = manual_name or short_title
        if len(display_name) > MAX_SESSION_NAME:
            raise ValueError('组合名称超过4096字，请精简重复内容；原名称保持不变。')
        response = dict(session_id=context['session_id'], revision=context['revision'],
                        result_sha256=context['result_sha256'], activities=activities,
                        suggested_name=suggested, session_name=display_name,
                        title=display_name or meta.get('game') or meta['id'], short_title=short_title,
                        activity_details=' + '.join(row['name'] for row in activities),
                        manual_name=manual_name, manual_name_preserved=bool(manual_name),
                        manual_summary_appended=False, replayed=replayed)
        if not apply:
            return dict(response, state='preview')
        if replayed:
            return dict(response, state='complete')
        # Validation can read a large transcript: check material and result again
        # immediately before the single metadata commit.
        if (_ready(folder)[2] != context['revision']
                or _file_hash(_path(folder, RESULT)) != context['result_sha256']):
            raise ValueError('命名期间素材或整理结果已更新，请重新核对。')
        meta['activity_naming'] = dict(proposal_sha256=fingerprint, version=1,
                                      revision=context['revision'], result_sha256=context['result_sha256'],
                                      worker=worker, activities=activities, suggested_name=suggested,
                                      short_title=short_title,
                                      naming_policy=context['naming_policy'], manual_name=manual_name,
                                      display_name=display_name, applied_name=display_name,
                                      previous_name=context['expected_name'], updated_at=time.time())
        meta.update(session_name=display_name,
                    session_name_source='manual' if manual_name else 'agent')
        if len(json.dumps(meta, ensure_ascii=False).encode('utf-8')) > 1024 * 1024:
            raise ValueError('活动分类使场次信息超过1 MB，请减少重复事件引用。')
        _write(folder, 'session.json', meta)
        return dict(response, state='complete')


def _reanalysis_status(job, raw):
    if not job.get('redo') or _committed(job, raw):
        return None
    value = dict(reason=str(job.get('redo_reason') or '')[:2000])
    if job.get('state') == 'processing':
        if _active_lease(job, raw):
            return dict(value, state='processing', expires_at=job['expires_at'])
        return dict(value, state='interrupted')
    return dict(value, state='failed', failure_reason=str(job.get('reason') or '')[:2000])


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
            from event_edits import project
            try:
                result, editing = project(folder, result, _file_hash(_path(folder, RESULT)))
            except (OSError, ValueError, TypeError):
                editing = dict(error='手动校准记录无法读取，暂时显示原整理结果；校准文件已保留。')
            value = dict(state='complete', label=f'已预处理 · {len(result["events"])} 个事件',
                         events=len(result['events']), questions=len(result['questions']),
                         ideas=len(result['ideas']), result=result, editing=editing)
            redo = _reanalysis_status(job, raw)
            if redo:
                value['reanalysis'] = redo
                label = '重新分析中' if redo['state'] == 'processing' else '重新分析未完成'
                value['label'] += f' · {label}，旧结果仍可回看'
            return value
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
        stats = _stats(folder, (READY, STATE, RESULT, 'experience-event-edits.json'))
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
            expiry = value.get('expires_at', value.get('reanalysis', {}).get('expires_at', time.time() + 86400))
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
