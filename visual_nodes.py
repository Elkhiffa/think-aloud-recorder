"""Local, read-only visual evidence preparation. No model, upload, or session writes.

The index describes pixel changes, not UI states, player intent or problems.
A full detection pass followed by sequential or targeted screenshot decoding.
"""
from collections import Counter
from contextlib import closing, contextmanager
from fractions import Fraction
import hashlib
from io import BytesIO
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit

import agent_protocol as protocol

VERSION = 1
MAX_INDEX_BYTES = 32 * 1024 * 1024
CAUTIONS = [
    '机械候选只表示画面变化，不等于界面节点、体验目标或体验问题。',
    '镜头、动画和特效可能造成误报；低分辨率检测可能漏掉小文字、颜色或焦点变化。',
    '原话未表达目标不等于没有目标；输入缺失不等于没有操作。',
    '图片预算只限制配图；未配图的候选仍需按时间回看，不能当作没有变化。',
]


class _Timings:
    """Disjoint caller wall times, never CPU time or a sum across workers."""
    def __init__(self):
        self.started = time.perf_counter()
        self.seconds = Counter()
        self.calls = Counter()

    @contextmanager
    def measure(self, name):
        began = time.perf_counter()
        try:
            yield
        finally:
            self.seconds[name] += time.perf_counter() - began
            self.calls[name] += 1

    def snapshot(self):
        wall = time.perf_counter() - self.started
        return dict(wall_seconds=round(wall, 6),
                    stages={name: dict(seconds=round(seconds, 6), calls=self.calls[name])
                            for name, seconds in self.seconds.items()},
                    unattributed_seconds=round(max(0, wall - sum(self.seconds.values())), 6))


def _timed_frames(frames, timings, stage):
    """Time frame supply only, excluding the consumer's work between yields."""
    try:
        while True:
            with timings.measure(stage):
                try:
                    value = next(frames)
                except StopIteration:
                    return
            yield value
    finally:
        with timings.measure(stage):
            frames.close()


def _dump(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)


def _open_video(path):
    import av
    container = av.open(str(path))
    if not container.streams.video:
        container.close()
        raise ValueError('素材没有视频轨。')
    stream = container.streams.video[0]
    stream.thread_count = 2
    # Browser playback begins at the container origin, not the first decoded
    # video frame. In early OBS recordings video may start 21 ms after audio.
    origin = float(container.start_time / av.time_base) if container.start_time is not None else 0.0
    return container, stream, origin


def _decode(path, start, end, stats):
    container, stream, origin = _open_video(path)
    try:
        stats.update(width=stream.width, height=stream.height,
                     time_base=str(stream.time_base), pts_origin_seconds=origin)
        if start > 0:
            container.seek(max(0, int((start + origin) / stream.time_base)), stream=stream,
                           backward=True, any_frame=False)
        previous, boundary, started = None, None, False
        def observe(at, frame):
            nonlocal previous
            if previous is not None and at <= previous:
                raise ValueError('视频时间戳重复或倒退，无法生成可靠的时间索引。')
            previous = at
            stats.setdefault('first_frame', at)
            stats['last_frame'] = at
            stats['last_frame_end'] = at + float((frame.duration or 0) * frame.time_base)
            stats['decoded_frames'] = stats.get('decoded_frames', 0) + 1
            return at, frame
        for frame in container.decode(stream):
            # Includes preroll and lookahead discarded before yielding a frame.
            # Output-frame counts alone understate the cost of targeted seeks.
            stats['decoder_frames'] = stats.get('decoder_frames', 0) + 1
            if frame.pts is None or frame.time_base is None:
                stats['missing_timestamps'] = stats.get('missing_timestamps', 0) + 1
                continue
            at = float(frame.pts * frame.time_base) - origin
            if at < start - 1e-7:
                if at >= 0:
                    boundary = at, frame
                continue
            if not started:
                # A VFR frame can remain visible across the requested start.
                # Keep its real PTS rather than inventing a frame at `start`.
                if boundary is not None and at > start + 1e-7:
                    stats['preceding_boundary_frame'] = boundary[0]
                    yield observe(*boundary)
                started = True
            if at > end + 1e-7:
                stats['reached_end'] = True
                break
            yield observe(at, frame)
        else:
            if not started and boundary is not None:
                at, frame = boundary
                if at + float((frame.duration or 0) * frame.time_base) > start:
                    stats['preceding_boundary_frame'] = at
                    yield observe(at, frame)
            stats['reached_eof'] = True
    finally:
        container.close()


def _jpeg(frame, width=960):
    import av
    width = min(width, frame.width)
    width -= width % 2
    height = max(2, round(frame.height * width / frame.width / 2) * 2)
    codec = av.CodecContext.create('mjpeg', 'w')
    codec.width, codec.height = width, height
    codec.pix_fmt = 'yuvj420p'
    codec.time_base = Fraction(1, 25)
    picture = frame.reformat(width=width, height=height, format='yuvj420p')
    picture.pts = 0
    return b''.join(bytes(p) for p in list(codec.encode(picture)) + list(codec.encode(None)))


def _spread(rows, count):
    if count >= len(rows):
        return rows
    if count <= 0:
        return []
    if count == 1:
        return [rows[len(rows) // 2]]
    return [rows[round(i * (len(rows) - 1) / (count - 1))] for i in range(count)]


def _select_times(nodes, budget):
    """Prefer one image per occurrence, spread omissions across the full range."""
    normal, low, remaining = [], [], []
    for node in nodes:
        frames = node['frames']
        for picture in frames:
            picture['path'] = None
        if not frames:
            continue
        best = next((f for f in frames if f['role'] in ('representative', 'peak')), frames[0])
        (low if node.get('image_priority') == 'low' else normal).append(best['time'])
        remaining.extend(f['time'] for f in frames if f is not best)
    chosen = set(_spread(sorted(set(normal)), budget))
    chosen.update(_spread(sorted(set(low) - chosen), budget - len(chosen)))
    rest = sorted(set(remaining) - chosen)
    chosen.update(_spread(rest, budget - len(chosen)))
    return chosen


def _context(folder, meta, duration, nodes):
    notes = []
    transcript, speakers = [], {}
    if protocol._path(folder, '录像.whisper.json').is_file():
        try:
            transcript = protocol._transcript(folder, duration)
            from speaker_roles import speaker_payload
            speakers = speaker_payload(folder, meta, transcript)
        except (OSError, ValueError, TypeError) as error:
            notes.append('逐字稿未展开：' + str(error))
    else:
        notes.append('尚无逐字稿；画面检测可独立完成。')
    try:
        inputs = protocol._normalized_inputs(folder, meta, duration)
    except (OSError, ValueError, TypeError):
        inputs = dict(state='failed', intervals=[], gaps=[])
    intervals, gaps = inputs.get('intervals', []), inputs.get('gaps', [])
    # O(nodes * log(rows) + overlaps): avoid rescanning an hour of input for
    # every visual occurrence while keeping repeated evidence references.
    intervals = sorted(intervals, key=lambda row: row['start'])
    transcript = sorted(transcript, key=lambda row: row['start'])
    active_inputs, active_quotes, ip, tp = [], [], 0, 0
    for node in sorted(nodes, key=lambda row: row['start']):
        start, end = node['start'], node['end']
        while ip < len(intervals) and intervals[ip]['start'] <= end:
            active_inputs.append(intervals[ip]); ip += 1
        while tp < len(transcript) and transcript[tp]['start'] <= end:
            active_quotes.append(transcript[tp]); tp += 1
        active_inputs = [r for r in active_inputs if r['end'] >= start]
        active_quotes = [r for r in active_quotes if r['end'] >= start]
        operations = [r for r in active_inputs if r['start'] <= end]
        quotes = [r for r in active_quotes if r['start'] <= end]
        node['transcript'] = quotes[:30]
        node['transcript_omitted'] = max(0, len(quotes) - 30)
        keys = Counter(str(r.get('label') or r.get('code') or r.get('device') or '?') for r in operations)
        node['input_summary'] = dict(state=inputs.get('state', 'missing'), count=len(operations),
                                    keys=[key for key, _ in keys.most_common(12)],
                                    refs=[r['id'] for r in operations[:24]],
                                    refs_omitted=max(0, len(operations) - 24),
                                    gap_count=sum(g['start'] <= end and g['end'] >= start for g in gaps))
    return dict(notes=notes, speakers=speakers,
                inputs={k: inputs[k] for k in ('state', 'error', 'alignment', 'timebase') if k in inputs})


def _image_frames(video, start, end, chosen, stats, mode):
    """Provide image candidates without changing their detection-pass timestamps."""
    if not chosen:
        return
    if mode == 'sequential':
        stats['decode_requests'] = 1
        yield from _decode(video, start, end, stats)
        return
    pending = set(chosen)
    for wanted in sorted(chosen):
        local = {}
        stats['decode_requests'] = stats.get('decode_requests', 0) + 1
        try:
            with closing(_decode(video, wanted, wanted, local)) as frames:
                result = next(frames, None)
                if result is None or result[0] != wanted:
                    # Container seeking is approximate (including B-frame
                    # reordering). Recover once from the original range, never
                    # retry each target or substitute a neighbouring frame.
                    stats['sequential_recovery'] = dict(
                        reason='exact_timestamp_unavailable', requested_time=wanted,
                        returned_time=result[0] if result is not None else None)
                    break
                pending.remove(wanted)
                yield result
        finally:
            for key in ('decoded_frames', 'decoder_frames', 'missing_timestamps'):
                stats[key] = stats.get(key, 0) + local.get(key, 0)
            if 'last_frame' in local:
                stats['last_frame'] = local['last_frame']
    if not pending:
        return
    local = {}
    stats['decode_requests'] += 1
    try:
        with closing(_decode(video, start, end, local)) as frames:
            for at, picture in frames:
                if at not in pending:
                    continue
                pending.remove(at)
                yield at, picture
                if not pending:
                    break
    finally:
        for key in ('decoded_frames', 'decoder_frames', 'missing_timestamps'):
            stats[key] = stats.get(key, 0) + local.get(key, 0)
        if 'last_frame' in local:
            stats['last_frame'] = local['last_frame']
        stats['sequential_recovery']['remaining_targets'] = len(pending)


def extract(folder, output, *, start=0, end=None, max_images=120, config=None, progress=None,
            image_mode='sequential'):
    """Create a fresh evidence directory outside the source library, or fail.

    Partial files remain diagnostic artifacts after a failure, with status.json
    failed. index.json and review.html appear only after source revalidation.
    """
    from av.video.reformatter import VideoReformatter
    from visual_change import VisualChangeDetector
    started = time.monotonic()
    timings = _Timings()
    folder, output = Path(folder).resolve(), Path(output).resolve()
    with timings.measure('source_validation'):
        meta, material, revision, _ = protocol._identity(folder)
    if meta.get('state') == '录制中':
        raise ValueError('该场次仍在录制，请等待录像保存后再提取。')
    duration = material['duration']
    end = duration if end is None else end
    protocol._span(dict(start=start, end=end), duration)
    if start >= end:
        raise ValueError('提取结束时间必须晚于开始时间。')
    if type(max_images) is not int or not 1 <= max_images <= 500:
        raise ValueError('图片预算应为 1–500。')
    if image_mode not in ('sequential', 'seek'):
        raise ValueError('配图模式应为 sequential 或 seek。')
    library = folder.parent.parent if folder.parent.name == '场次' else folder
    if output.is_relative_to(library):
        raise ValueError('候选证据请保存到资料库以外的新工作目录。')
    if output.exists():
        raise ValueError('输出目录已存在，请选择新目录以保留历史结果。')
    video = protocol._path(folder, '录像.mp4')
    if not video.is_file() or video.stat().st_size == 0:
        raise ValueError('场次尚无已保存的 MP4 录像。')
    detector = VisualChangeDetector(config or dict(max_dimension=320))
    output.mkdir(parents=True)
    (output / 'images').mkdir()
    stats, image_stats = {}, {}
    try:
        # Keep the scaler context for this extraction instead of rebuilding it
        # for every decoded frame. Reformat still receives each frame's format
        # and colour metadata; no sampling or detector parameters change.
        reformatter = VideoReformatter()
        last_notice = 0
        with closing(_timed_frames(_decode(video, start, end, stats), timings, 'detect_decode')) as frames:
            for at, picture in frames:
                with timings.measure('detect_resize'):
                    width = min(320, picture.width)
                    height = max(1, round(picture.height * width / picture.width))
                    rgb = reformatter.reformat(picture, width=width, height=height,
                                               format='rgb24').to_ndarray()
                with timings.measure('detect_changes'):
                    detector.feed(at, rgb)
                if progress and time.monotonic() - last_notice >= 5:
                    with timings.measure('progress_callback'):
                        progress(dict(phase='detect', at=at, end=end, frames=stats['decoded_frames']))
                    last_notice = time.monotonic()
        if not stats.get('decoded_frames'):
            raise ValueError('该区间没有可解码画面。')
        display_start = max(start, stats['first_frame'])
        display_end = end if stats.get('reached_end') else min(end, stats['last_frame_end'])
        stats['display_coverage'] = dict(start=display_start, end=display_end)
        with timings.measure('detect_finish'):
            result = detector.finish(max(stats['last_frame'], display_end))
        with timings.measure('select_images'):
            nodes = sorted(result['nodes'], key=lambda n: (n['start'], n['end']))
            for i, node in enumerate(nodes):
                node['id'] = f'v{i + 1:06d}'
            chosen = _select_times(nodes, max_images)
        images = {}
        if progress:
            with timings.measure('progress_callback'):
                progress(dict(phase='images', selected=len(chosen), nodes=len(nodes)))
        with closing(_timed_frames(_image_frames(video, start, end, chosen, image_stats, image_mode),
                                   timings, 'image_decode')) as frames:
            for at, picture in frames:
                if at not in chosen:
                    continue
                with timings.measure('image_resize_encode'):
                    content = _jpeg(picture)
                with timings.measure('image_hash_write'):
                    digest = hashlib.sha256(content).hexdigest()
                    relative = 'images/' + digest + '.jpg'
                    path = output / relative
                    if not path.exists():
                        with path.open('xb') as handle:
                            handle.write(content)
                    images[at] = relative
                if len(images) == len(chosen):
                    break
        if len(images) != len(chosen):
            raise ValueError('第二次解码未能复现选中的时间戳；未发布索引。')
        for node in nodes:
            for frame in node['frames']:
                frame['path'] = images.get(frame['time'])
                if frame['time'] < start:
                    frame['boundary_context'] = '起点前已显示、跨越起点的原始帧；时间未改写。'
            # Weak pixel observations remain searchable without automatically
            # restoring the frame flood we compressed from camera motion.
            for observation in node.get('motion_observations', []):
                for frame in observation['frames']:
                    frame['path'] = None
        with timings.measure('associate_evidence'):
            context = _context(folder, meta, duration, nodes)
        with timings.measure('source_validation'):
            if protocol._identity(folder)[2] != revision:
                raise ValueError('提取期间素材、转写或输入同步已更新；请在新目录重新提取。')
        missed = sum(not any(f['path'] for f in n['frames']) for n in nodes)
        uncovered = []
        if display_start > start + 1e-7:
            uncovered.append(dict(start=start, end=display_start, reason='before_first_video_frame'))
        if display_end < end - 1e-7:
            uncovered.append(dict(start=max(start, display_end), end=end, reason='after_last_video_frame'))
        scan_complete = not stats.get('missing_timestamps') and not uncovered
        detector_stats = result.get('stats', {})
        extra_notes = []
        if detector_stats.get('truncated'):
            extra_notes.append(f"索引达到上限，有 {detector_stats['omitted_nodes']} 个主要候选和 "
                               f"{detector_stats.get('omitted_weak_motion_observations', 0)} 处弱观察未列出；"
                               '按具体疑点查询短窗，仅在证据不足时局部补查，沿用原取材预算。')
        if stats.get('missing_timestamps'):
            extra_notes.append('有画面缺少时间戳，已跳过，不能认为检测完整。')
        if any(r['reason'] == 'after_last_video_frame' for r in uncovered):
            extra_notes.append('视频在所选范围结束前已到文件末尾，后段没有可解码画面。')
        if any(r['reason'] == 'before_first_video_frame' for r in uncovered):
            extra_notes.append('所选范围起点早于视频首帧，首帧之前没有画面证据。')
        if 'preceding_boundary_frame' in stats:
            extra_notes.append('保留了跨越范围起点的前一帧，仍使用其真实时间戳。')
        # Decode-through-end and semantic coverage are intentionally different.
        index = dict(version=VERSION, kind='visual-change-candidates', session_id=meta['id'],
                     revision=revision, title=meta.get('session_name') or meta.get('game') or meta['id'],
                     source=dict(video_uri=video.as_uri(), session_folder=str(folder),
                                 duration_seconds=duration, fingerprint=material['sources']['录像.mp4'],
                                 fingerprint_kind='size-and-mtime', timebase='video_seconds'),
                     range=dict(start=start, end=end), stats={**stats, 'detector': result.get('stats', {})},
                     detector_config=detector_stats.get('config', {}),
                     coverage=dict(candidate_nodes=len(nodes), selected_images=len(images),
                                   unique_image_files=len(set(images.values())), max_images=max_images,
                                   total_frame_candidates=len({f['time'] for n in nodes for f in n['frames']}),
                                   unpictured_nodes=missed, complete=scan_complete,
                                   uncovered_ranges=uncovered,
                                   weak_motion_observations_without_images=sum(len(n.get('motion_observations', [])) for n in nodes),
                                   node_index_complete=detector_stats.get('node_index_complete', True),
                                   meaning='complete 仅表示所选范围内有时间戳的解码帧已检查，不表示语义无遗漏。',
                                   notes=CAUTIONS + extra_notes + context.pop('notes')),
                     context=context, nodes=nodes, metrics_file='metrics.json',
                     elapsed_seconds=round(time.monotonic() - started, 3))
        with timings.measure('publish_index_review'):
            serialized = json.dumps(index, ensure_ascii=False, allow_nan=False)
            if len(serialized.encode('utf-8')) > MAX_INDEX_BYTES:
                raise ValueError('候选索引过大，请缩小提取区间。')
            template = (Path(__file__).resolve().parent / 'ui' / 'visual-nodes.html').read_text(encoding='utf-8')
            safe_json = serialized.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
            if template.count('__VISUAL_DATA__') != 1:
                raise ValueError('检查页模板数据插槽无效。')
            with (output / 'review.html').open('x', encoding='utf-8') as handle:
                handle.write(template.replace('__VISUAL_DATA__', safe_json))
            _dump(output / 'index.json', index)
        metrics = dict(version=1, kind='visual-preprocess-metrics', state='complete',
                       session_id=meta['id'], revision=revision, range=index['range'],
                       timing=timings.snapshot(),
                       timing_scope='extract entry through saved index/review; excludes metrics/status writes and CLI response',
                       timing_basis='single-task caller wall time; not CPU time; parallel task times must not be added as wall time',
                       detector_config=index['detector_config'], max_images=max_images, image_mode=image_mode,
                       image_sequential_recovery=image_stats.get('sequential_recovery'),
                       counts=dict(detect_frames=stats.get('decoded_frames', 0),
                                   detect_decoder_frames=stats.get('decoder_frames', 0),
                                   image_pass_frames=image_stats.get('decoded_frames', 0),
                                   image_decoder_frames=image_stats.get('decoder_frames', 0),
                                   image_decode_requests=image_stats.get('decode_requests', 0),
                                   image_pass_last_frame=image_stats.get('last_frame'),
                                   candidate_nodes=len(nodes),
                                   weak_observations=index['coverage']['weak_motion_observations_without_images'],
                                   omitted_nodes=detector_stats.get('omitted_nodes', 0),
                                   omitted_weak_observations=detector_stats.get('omitted_weak_motion_observations', 0),
                                   selected_image_times=len(images), unique_image_files=len(set(images.values())),
                                   unpictured_nodes=missed, index_bytes=(output/'index.json').stat().st_size,
                                   review_bytes=(output/'review.html').stat().st_size),
                       coverage=dict(decoded_range_complete=scan_complete,
                                     node_index_complete=index['coverage']['node_index_complete'],
                                     uncovered_ranges=uncovered,
                                     omitted_time_range=detector_stats.get('omitted_time_range'),
                                     meaning='Machine counts only; selected images are not images inspected by an agent.'))
        _dump(output / 'metrics.json', metrics)
        _dump(output / 'status.json', dict(state='complete', session_id=meta['id'], revision=revision))
        return dict(index=str(output / 'index.json'), review=str(output / 'review.html'),
                    metrics=str(output / 'metrics.json'),
                    image_mode=image_mode, image_sequential_recovery=image_stats.get('sequential_recovery'),
                    coverage=index['coverage'], elapsed_seconds=index['elapsed_seconds'])
    except Exception as error:
        try:
            if not (output / 'metrics.json').exists():
                _dump(output / 'metrics.json', dict(version=1, kind='visual-preprocess-metrics', state='failed',
                      timing=timings.snapshot(), image_mode=image_mode,
                      image_sequential_recovery=image_stats.get('sequential_recovery'),
                      counts=dict(detect_frames=stats.get('decoded_frames', 0),
                      detect_decoder_frames=stats.get('decoder_frames', 0),
                      image_pass_frames=image_stats.get('decoded_frames', 0),
                      image_decoder_frames=image_stats.get('decoder_frames', 0),
                      image_decode_requests=image_stats.get('decode_requests', 0)),
                      timing_scope='partial attempt through failure; incomplete counts are not final coverage'))
        except Exception:
            pass  # Optional diagnostics must not mask the original failure.
        try:
            _dump(output / 'status.json', dict(state='failed', error=str(error)))
        except Exception:
            pass  # Preserve the root exception even when the destination is full.
        raise


def _read_fresh_index(path, timings):
    with timings.measure('read_parse_index'):
        index_bytes = path.stat().st_size
        if index_bytes > MAX_INDEX_BYTES:
            raise ValueError('索引超过 32 MB。')
        index = json.loads(path.read_text(encoding='utf-8'))
    if index.get('version') != VERSION or index.get('kind') != 'visual-change-candidates':
        raise ValueError('不支持的画面候选索引。')
    # Shared by detail and overview: compact reads cannot bypass source checks.
    with timings.measure('source_validation'):
        if protocol._identity(Path(index['source']['session_folder']))[2] != index['revision']:
            raise ValueError('源素材或同步信息已改变，此索引已过期。')
    return index, index_bytes


def read_index(path, *, start=None, end=None, offset=0, limit=40):
    timings = _Timings()
    path = Path(path).resolve()
    index, index_bytes = _read_fresh_index(path, timings)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('offset 需非负，limit 应为 1–100。')
    if start is not None or end is not None:
        if start is None or end is None:
            raise ValueError('请同时提供 start 与 end。')
        protocol._span(dict(start=start, end=end), index['source']['duration_seconds'])
    with timings.measure('filter_resolve_images'):
        rows = index['nodes']
        if start is not None:
            rows = [n for n in rows if n['end'] >= start and n['start'] <= end]
        selected = rows[offset:offset + limit]
        for node in selected:
            for frame in node['frames']:
                if frame.get('path'):
                    image = (path.parent / frame['path']).resolve()
                    if not image.is_relative_to(path.parent / 'images') or not image.is_file():
                        raise ValueError('候选图片路径无效。')
                    frame['absolute_path'] = str(image)
    value = {k: v for k, v in index.items() if k != 'nodes'} | dict(
        index=str(path), total_matching=len(rows), offset=offset,
        next_offset=offset + limit if offset + limit < len(rows) else None, nodes=selected)
    with timings.measure('measure_response'):
        characters = len(json.dumps(value, ensure_ascii=False, allow_nan=False))
    value['read_metrics'] = dict(version=1, timing=timings.snapshot(), index_bytes=index_bytes,
                                returned_nodes=len(selected), data_characters_without_read_metrics=characters,
                                returned_unique_image_paths=len({f['absolute_path'] for n in selected
                                    for f in n['frames'] if f.get('absolute_path')}),
                                meaning='Characters of returned data before read_metrics; excludes CLI envelope; not tokens or proof of image inspection.')
    return value


def _candidate_rows(index,start,end):
    """Flatten only intersecting observations; never embed an entire motion tree."""
    for node in index['nodes']:
        if node['end']<start or node['start']>end:
            continue
        yield dict(id=node['id'],parent=None,level='primary',row=node)
        for i,row in enumerate(node.get('motion_observations',[])):
            if row['end']>=start and row['start']<=end:
                ordinal = row.get('observation_ordinal', i + 1)
                yield dict(id=f"{node['id']}/w{ordinal}",parent=node['id'],level='weak',row=row)


def _omission_windows(detector, start, end):
    """Intersect disclosed loss envelopes with a question, never schedule work.

    Old indexes only know one envelope. They cannot retroactively recover exact
    missing timestamps. New bounded bins describe where losses may occur; even
    their counts are not exact counts inside an arbitrary clipped query.
    """
    bins = detector.get('omission_bins')
    counts = dict(major_nodes=detector.get('omitted_nodes', 0),
                  weak_observations=detector.get('omitted_weak_motion_observations', 0))
    complete_bins = isinstance(bins, list) and all(
        sum(row.get(key, 0) for row in bins) == total for key, total in counts.items())
    basis = 'time_bin_envelopes' if complete_bins else 'legacy_global_envelope'
    envelope = detector.get('omitted_time_range')
    spans = [(row['start'], row['end']) for row in bins] if complete_bins else ([envelope] if envelope else [])
    windows = []
    for left, right in sorted(spans):
        if right < start or left > end:
            continue
        left, right = max(start, left), min(end, right)
        if windows and left <= windows[-1]['end']:
            windows[-1]['end'] = max(windows[-1]['end'], right)
        else:
            windows.append(dict(start=left, end=right))
    return basis, windows


def _existing_image_stats(path):
    """Describe one existing JPEG; never classify its semantic usefulness."""
    import av
    with path.open('rb') as handle:
        content = handle.read(16 * 1024 * 1024 + 1)
    if len(content) > 16 * 1024 * 1024:
        return dict(state='unknown', reason='image_size_limit')
    digest = hashlib.sha256(content).hexdigest()
    if path.name != digest + '.jpg':
        return dict(state='unknown', reason='image_hash_mismatch')
    try:
        with av.open(BytesIO(content), format='mjpeg') as image:
            stream = image.streams.video[0]
            if stream.width * stream.height > 8_000_000:
                return dict(state='unknown', reason='image_dimensions_limit')
            frame = next(image.decode(stream))
            rgb = frame.reformat(width=64, height=36, format='rgb24').to_ndarray()
    except av.FFmpegError:
        return dict(state='unknown', reason='image_read_failed')
    return dict(state='measured', sha256=digest, rgb_min=int(rgb.min()), rgb_max=int(rgb.max()),
                rgb_mean=round(float(rgb.mean()), 4), rgb_std=round(float(rgb.std()), 4),
                pixels_all_channels_below_10=round(float((rgb.max(axis=2) < 10).mean()), 6))


def _candidate_image_hints(index_path, records, start, end):
    """At most 12 existing JPEG reads, with explicit unknowns for other frames."""
    measured, identifiers, hints = {}, {}, []
    for record in records:
        references = []
        for frame in record['row']['frames']:
            relative = frame.get('path')
            key = 'unpictured'
            if relative:
                path = (index_path.parent / relative).resolve()
                if not path.is_relative_to(index_path.parent / 'images') or not path.is_file():
                    raise ValueError('候选图片路径无效。')
                if path in identifiers:
                    key = identifiers[path]
                elif len(measured) >= 12:
                    key = 'inspection_limit'
                else:
                    key = f'p{len(measured)+1:02d}'
                    identifiers[path] = key
                    try:
                        measured[key] = _existing_image_stats(path)
                    except (OSError, ValueError, StopIteration):
                        measured[key] = dict(state='unknown', reason='image_read_failed')
            references.append([frame['time'], frame['role'], start <= frame['time'] <= end, key])
        hints.append(references)
    return hints, measured


def read_candidates(path, *, start, end, offset=0, limit=24, level='all', parent=None,
                    image_stats=False):
    """Compact interval navigation with a single bound across primary/weak rows."""
    timings=_Timings()
    path=Path(path).resolve()
    index,index_bytes=_read_fresh_index(path,timings)
    protocol._span(dict(start=start,end=end),index['source']['duration_seconds'])
    if start>=end or end-start>120:
        raise ValueError('候选区间须大于 0 且不超过 120 秒。')
    if start<index['range']['start'] or end>index['range']['end']:
        raise ValueError('候选区间须位于索引范围内。')
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=60:
        raise ValueError('offset 需非负，limit 应为 1–60。')
    if level not in ('all','primary','weak'):
        raise ValueError('level 应为 all、primary 或 weak。')
    if parent is not None and (level!='weak' or not isinstance(parent,str)
                               or not any(n['id']==parent for n in index['nodes'])):
        raise ValueError('parent 需为索引内的主要候选 ID，且仅用于 level=weak。')
    records=list(_candidate_rows(index,start,end))
    matching_by_level={kind:sum(r['level']==kind for r in records) for kind in ('primary','weak')}
    weak_counts=Counter(r['parent'] for r in records if r['level']=='weak')
    records=sorted((r for r in records if (level=='all' or r['level']==level)
                    and (parent is None or r['parent']==parent)),
                   key=lambda r:(r['row']['start'],r['row']['end'],r['id']))
    rows=[]
    for record in records[offset:offset+limit]:
        row=record['row']
        rows.append([record['id'],record['level'],row['kind'],row['start'],row['end'],
                     [f['time'] for f in row['frames'] if start<=f['time']<=end],
                     sum(bool(f.get('path')) for f in row['frames'] if start<=f['time']<=end),
                     record['parent'],weak_counts.get(record['id'],0)])
    detector=index['stats'].get('detector',{})
    omitted=detector.get('omitted_time_range')
    omission_basis, follow_up_ranges = _omission_windows(detector, start, end)
    value=dict(version=1,kind='visual-interval-candidates',index=str(path),
               session_id=index['session_id'],revision=index['revision'],range=dict(start=start,end=end),
               total_matching=len(records),offset=offset,level=level,parent=parent,
               matching_by_level=matching_by_level,
               next_offset=offset+limit if offset+limit<len(records) else None,
               columns=['id','level','kind','start','end','frame_times_in_range','pictured_in_range',
                        'parent_id','retained_weak_in_range'],rows=rows,
               node_index_complete=index['coverage'].get('node_index_complete',False),
               omissions=dict(major_nodes=detector.get('omitted_nodes',0),
                              weak_observations=detector.get('omitted_weak_motion_observations',0),
                              time_range=omitted,
                              overlaps_query=bool(follow_up_ranges), basis=omission_basis),
               follow_up=dict(ranges=follow_up_ranges[:8], total_ranges=len(follow_up_ranges),
                              truncated=len(follow_up_ranges)>8, automatic=False,
                              note='仅为疑点窗口内的遗漏包络，不是精确缺失或必查清单。证据不足才在新目录局部补索引；'
                                   '沿用原计划通过 visual-packet --at 取图，保留补索引 SHA 与候选 ID，不新建预算。'),
               actual_image_inspection=False,
               note='仅像素候选导航；层级筛选不删除原始证据。matching_by_level 是 parent 筛选前的整个查询区间数量；weak 数仅计保留项。遗漏数量与 time_range 属于全索引，不表示逐秒缺失。用同场 visual-packet 预算取图。')
    if image_stats:
        with timings.measure('existing_image_stats'):
            hints, measured = _candidate_image_hints(path, records[offset:offset+limit], start, end)
        value['columns'].append('frame_hints')
        for row, references in zip(rows, hints):
            row.append(references)
        value['image_stats'] = dict(
            representation='Existing JPEG resized to 64x36 RGB; channel values 0..255.',
            frame_hint_columns=['actual_time','role','in_query_range','image_stats_key_or_unknown_reason'],
            pictures=measured, max_image_reads=12, attempted_image_reads=len(measured),
            seconds=round(timings.seconds['existing_image_stats'], 6),
            note='unpictured/inspection_limit 为未知；统计只对应列出的原帧，不代表任意区间中点。'
                 '均匀或暗画面仍可有意义，不能据此判定模糊、无用或自动跳过。未解码视频、未发图、未实际看图。')
    characters=len(json.dumps(value,ensure_ascii=False,allow_nan=False))
    value['read_metrics']=dict(index_bytes=index_bytes,returned_rows=len(rows),
                               data_characters_without_read_metrics=characters,returned_unique_image_paths=0)
    return value


def read_overview(path, *, bins=32):
    """Bounded, non-semantic navigation over every indexed interval; no pictures."""
    if type(bins) is not int or not 1 <= bins <= 120:
        raise ValueError('概览分区数应为 1–120。')
    timings = _Timings()
    path = Path(path).resolve()
    index, index_bytes = _read_fresh_index(path, timings)
    start, end = index['range']['start'], index['range']['end']
    if end <= start:
        raise ValueError('候选索引时间范围无效。')
    nodes = index['nodes']
    omitted = index['stats'].get('detector', {}).get('omitted_time_range')
    with timings.measure('aggregate_timeline'):
        weak_starts = [max(start, row['start']) for n in nodes for row in n.get('motion_observations', [])]
        table = []
        for i in range(bins):
            left = start + (end - start) * i / bins
            right = end if i == bins - 1 else start + (end - start) * (i + 1) / bins
            def owns(at):
                return left <= at < right or (i == bins - 1 and at == right)
            overlapping = [n for n in nodes if n['end'] >= left and
                           (n['start'] < right or (i == bins - 1 and n['start'] == right))]
            quotes = {r['id'] for n in overlapping for r in n.get('transcript', [])}
            table.append([left, right, len(overlapping), sum(owns(max(start,n['start'])) for n in nodes),
                          dict(Counter(n['kind'] for n in overlapping)),
                          sum(any(f.get('path') for f in n['frames']) for n in overlapping),
                          sum(owns(at) for at in weak_starts), len(quotes),
                          sum(n.get('transcript_omitted',0)>0 for n in overlapping),
                          sum(n.get('input_summary',{}).get('gap_count',0)>0 for n in overlapping),
                          bool(_omission_windows(index['stats'].get('detector',{}),left,right)[1])])
        value = dict(version=VERSION, kind='visual-candidate-overview', index=str(path),
                     session_id=index['session_id'], revision=index['revision'], range=index['range'],
                     coverage=index['coverage'],
                     omissions=dict(major_nodes=index['stats'].get('detector',{}).get('omitted_nodes',0),
                                    weak_observations=index['stats'].get('detector',{}).get('omitted_weak_motion_observations',0),
                                    time_range=omitted),
                     columns=['start','end','overlapping_nodes','node_starts','node_kinds',
                              'pictured_nodes','weak_starts','linked_quote_refs',
                              'nodes_with_omitted_quotes','nodes_with_input_gaps','index_omissions'], rows=table,
                     actual_image_inspection=False,
                     notes=['分区仅汇总完整索引；未重新抽帧、未删除候选，不代表目标或流程分段。',
                            '跨分区节点会重复计入 overlapping_nodes；node_starts 与 weak_starts 按起点归属。',
                            '有配图节点不代表所看分区内一定有配图；原话引用只来自有限关联，不等于全部逐字稿。',
                            '本概览没有展示图片或原话；空计数不证明无操作或无目标。'],
                     next_step='先单独读取完整原话；用 visual-plan/visual-packet 限额看图，visual-candidates 按短区间紧凑定位。')
    with timings.measure('measure_response'):
        characters = len(json.dumps(value, ensure_ascii=False, allow_nan=False))
    value['read_metrics'] = dict(version=1, timing=timings.snapshot(), index_bytes=index_bytes,
                                returned_rows=len(table), data_characters_without_read_metrics=characters,
                                returned_unique_image_paths=0,
                                meaning='Overview characters before read_metrics; not tokens, model cost or semantic coverage.')
    return value


def review_server(path, port=0):
    """A token-scoped loopback viewer. Only its HTML, images and one video exist."""
    path = Path(path).resolve()
    read_index(path, limit=1)  # Schema, source freshness and evidence binding.
    index = json.loads(path.read_text(encoding='utf-8'))
    folder = path.parent
    video = protocol._path(index['source']['session_folder'], '录像.mp4')
    prefix = '/' + secrets.token_urlsafe(24) + '/'
    allowed_images = {f['path'] for n in index['nodes'] for f in n['frames'] if f.get('path')}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_GET(self, head=False):
            route = urlsplit(self.path).path
            if not route.startswith(prefix):
                self.send_error(404); return
            relative = route[len(prefix):]
            if relative in ('', 'review.html', 'video.mp4'):
                try:
                    fresh = protocol._identity(index['source']['session_folder'])[2] == index['revision']
                except (OSError, ValueError, TypeError):
                    fresh = False
                if not fresh:
                    message = '源素材或同步信息已经改变，本检查页已过期。请重新提取候选。'.encode('utf-8')
                    self.send_response(409)
                    self.send_header('Content-Type', 'text/plain; charset=utf-8')
                    self.send_header('Content-Length', str(len(message)))
                    self.send_header('Cache-Control', 'no-store')
                    self.end_headers()
                    if not head: self.wfile.write(message)
                    return
            if relative in ('', 'review.html'):
                html = (folder / 'review.html').read_text(encoding='utf-8')
                # source URI is JSON-encoded inside the page; replace only its value.
                html = html.replace(json.dumps(index['source']['video_uri'], ensure_ascii=False),
                                    json.dumps(prefix + 'video.mp4'))
                body = html.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
                if not head: self.wfile.write(body)
                return
            if relative == 'video.mp4':
                target, mime = video, 'video/mp4'
            elif relative in allowed_images:
                target, mime = (folder / relative).resolve(), 'image/jpeg'
                if not target.is_relative_to(folder / 'images'):
                    self.send_error(404); return
            else:
                self.send_error(404); return
            size = target.stat().st_size
            first, last, partial = 0, size - 1, False
            request_range = self.headers.get('Range')
            if request_range:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', request_range)
                if match and any(match.groups()):
                    a, b = match.groups()
                    first = int(a) if a else max(0, size - int(b))
                    last = min(size - 1, int(b)) if a and b else size - 1
                else:
                    first = size
                if first > last or first >= size:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.end_headers(); return
                partial = True
            self.send_response(206 if partial else 200)
            self.send_header('Content-Type', mime)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Length', str(last - first + 1))
            self.send_header('Cache-Control', 'no-store')
            if partial: self.send_header('Content-Range', f'bytes {first}-{last}/{size}')
            self.end_headers()
            if not head:
                try:
                    with target.open('rb') as handle:
                        handle.seek(first)
                        remaining = last - first + 1
                        while remaining:
                            block = handle.read(min(remaining, 256 * 1024))
                            if not block: break
                            self.wfile.write(block); remaining -= len(block)
                except (ConnectionError, OSError):
                    pass
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.review_url = f'http://127.0.0.1:{server.server_port}{prefix}'
    return server
