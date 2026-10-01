"""Bounded local pixel comparisons; results are candidates, never viewed evidence.

No images are issued here. Use visual-packet for any returned source PTS so the
existing per-session image ledger remains the only picture issuance boundary.
"""
from contextlib import closing
from datetime import datetime, timezone
from fractions import Fraction
import math
import re
import time

import agent_protocol as protocol
from recorder import write
from session_metadata import metadata_lock
import visual_evidence as evidence
import visual_nodes as visual

VERSION = 1
TIMING_VERSION = 2
MAX_CANDIDATES = 512
MAX_DECODE_FRAMES = 18000  # Includes seek preroll and end lookahead.
SIGNATURE_WIDTH = 192
PIXEL_DELTA = 18
MEAN_DELTA = 3.0
CHANGED_FRACTION = .012


def _region(values):
    values = [0., 0., 1., 1.] if values is None else list(values)
    if len(values) != 4 or any(not protocol._number(n) for n in values):
        raise ValueError('region 应为四个有限数值：归一化 x y width height。')
    x, y, width, height = map(float, values)
    if not (0 <= x < 1 and 0 <= y < 1 and width > 0 and height > 0
            and x + width <= 1 + 1e-9 and y + height <= 1 + 1e-9):
        raise ValueError('region 必须在画面内，宽高大于 0，坐标范围为 0–1。')
    return [x, y, width, height]


def _packet_frames(container, stream, origin, start, end, stats):
    """Retain coding-timeline diagnostics while the decoder reorders B frames."""
    previous_end = None
    for packet in container.demux(stream):
        if packet.size:
            stats['demux_packets'] = stats.get('demux_packets',0)+1
            if packet.pts is not None and packet.time_base is not None:
                pts = Fraction(packet.pts)*packet.time_base
                if start-1e-7 <= float(pts)-origin <= end+1e-7:
                    stats.setdefault('_packet_pts',set()).add(pts)
            else:
                stats['missing_packet_pts'] = stats.get('missing_packet_pts',0)+1
            if packet.dts is not None and packet.time_base is not None:
                dts = Fraction(packet.dts)*packet.time_base
                if previous_end is not None and dts != previous_end:
                    # Rational comparison, not an arbitrary millisecond epsilon.
                    interval = [float(min(previous_end,dts))-origin,
                                float(max(previous_end,dts))-origin]
                    if interval[1] >= start and interval[0] <= end:
                        stats['coding_timing_discontinuities'] = stats.get('coding_timing_discontinuities',0)+1
                        examples=stats.setdefault('coding_timing_examples',[])
                        if len(examples)<8: examples.append(interval)
                previous_end = dts+Fraction(packet.duration)*packet.time_base if packet.duration else None
                if not packet.duration:
                    stats['unknown_packet_durations'] = stats.get('unknown_packet_durations',0)+1
            else:
                stats['missing_packet_dts'] = stats.get('missing_packet_dts',0)+1
                previous_end = None
        yield from packet.decode()


def _frames(video, start, end, stats):
    """Source PTS define display boundaries; final EOF uses declared duration.

    B-frame packet durations may describe decode order, not the interval to
    the next displayed frame. Coding discontinuities remain explicit unknowns.
    """
    container, stream, origin = visual._open_video(video)
    try:
        stats.update(width=stream.width, height=stream.height,
                     time_base=str(stream.time_base), pts_origin_seconds=origin)
        if start > 0:
            container.seek(max(0, int((start + origin) / stream.time_base)),
                           stream=stream, backward=True, any_frame=False)
        previous_time, pending = None, None
        decoded = _packet_frames(container,stream,origin,start,end,stats)
        while stats['decoder_frames'] < MAX_DECODE_FRAMES:
            try:
                frame = next(decoded)
            except StopIteration:
                stats['reached_eof'] = True
                break
            stats['decoder_frames'] += 1
            if frame.pts is None or frame.time_base is None:
                stats['missing_timestamps'] += 1
                continue
            at = float(frame.pts * frame.time_base) - origin
            if previous_time is not None and at <= previous_time:
                raise ValueError('视频时间戳重复或倒退，无法可靠比较。')
            previous_time = at
            stats['last_decoded_time'] = at
            duration = float((frame.duration or 0) * frame.time_base)
            row = dict(time=at, pts=frame.pts, time_base=str(frame.time_base),
                       pts_origin_seconds=origin, frame_end=at+max(0,duration),
                       declared_frame_end=at+max(0,duration), frame_end_basis='declared_duration')
            if start-1e-7 <= at <= end+1e-7:
                stats.setdefault('_decoded_pts',set()).add(Fraction(frame.pts)*frame.time_base)
            if pending is not None:
                old,old_frame=pending
                declared_end=Fraction(old_frame.pts+(old_frame.duration or 0))*old_frame.time_base
                if declared_end != Fraction(frame.pts)*frame.time_base and old['time'] >= start:
                    stats['presentation_duration_mismatches'] = stats.get('presentation_duration_mismatches',0)+1
                old['frame_end'],old['frame_end_basis']=at,'next_source_pts'
                if old['time'] >= 0 and old['time'] <= end+1e-7 and at > start:
                    _cover(stats,old,start,end)
                    if at > end+1e-7:stats['reached_end']=True
                    yield old,old_frame
                if at > end+1e-7:
                    stats['reached_end']=True
                    return
            pending=row,frame
        else:
            stats['stopped_at_decode_limit'] = True
        if pending is not None:
            row,frame=pending
            if row['time'] >= 0 and row['time'] <= end+1e-7 and row['frame_end'] > start:
                _cover(stats, row, start, end)
                yield row, frame
    finally:
        container.close()


def _cover(stats, row, start, end):
    """Track actual decoded display intervals, including gaps and early EOF."""
    left, right = max(start,row['time']), min(end,row['frame_end'])
    if right < left or row['frame_end'] <= row['time']:
        if row['frame_end'] <= row['time']:
            stats['unknown_frame_durations'] = stats.get('unknown_frame_durations',0)+1
        return
    intervals = stats.setdefault('_covered_intervals',[])
    if intervals and left <= intervals[-1][1]+1e-7:
        intervals[-1][1] = max(right,intervals[-1][1])
    else:
        intervals.append([left,right])


def _targets(index, start, end):
    points = {start: [], end: []}
    for record in visual._candidate_rows(index, start, end):
        for frame in record['row']['frames']:
            at = frame['time']
            if start <= at <= end:
                points.setdefault(at, []).append(record['id'])
    if len(points) > MAX_CANDIDATES:
        raise ValueError(f'区间含 {len(points)} 个候选时间点，超过 {MAX_CANDIDATES}；请缩短区间，不静默抽稀。')
    return points


def _candidate_frames(decoded, targets, stats):
    """Resolve millisecond-rounded index times to source frames, not new PTS."""
    pending = iter(sorted(targets))
    target = next(pending, None)
    previous, last_emitted = None, None
    unresolved = stats.setdefault('unresolved_target_times',[])
    def resolve(chosen, target):
        tolerance = .00051 if targets[target] else 1e-7
        return chosen is not None and (abs(chosen[0]['time']-target) <= tolerance
            or chosen[0]['time'] <= target < chosen[0]['frame_end'])
    for row, frame in decoded:
        while target is not None and target <= row['time'] + .00051:
            # Index times may be rounded to 3 decimals. Otherwise use the frame
            # visible at the requested time, not the next frame after a gap.
            tolerance = .00051 if targets[target] else 1e-7
            chosen = (row, frame) if abs(target-row['time']) <= tolerance else previous
            if resolve(chosen,target):
                if chosen[0]['time'] != last_emitted:
                    last_emitted = chosen[0]['time']
                    yield chosen[0] | dict(requested_time=target,
                                           candidate_refs=targets[target]), chosen[1]
            else:
                unresolved.append(target)
            target = next(pending, None)
        previous = row, frame
        if target is None:
            return
    while target is not None:
        if resolve(previous,target):
            if previous[0]['time'] != last_emitted:
                last_emitted=previous[0]['time']
                yield previous[0] | dict(requested_time=target, candidate_refs=targets[target]), previous[1]
        else:
            unresolved.append(target)
        target=next(pending,None)


def _signature(frame, region):
    import av
    x, y, width, height = region
    left, top = math.floor(x*frame.width), math.floor(y*frame.height)
    right = min(frame.width, math.ceil((x+width)*frame.width))
    bottom = min(frame.height, math.ceil((y+height)*frame.height))
    if right-left < 2 or bottom-top < 2:
        raise ValueError('region 在原片中不足 2×2 像素，请扩大区域。')
    # Crop at native resolution before reducing. Reducing the full screen first
    # would discard exactly the small local differences this command targets.
    crop = frame.to_ndarray(format='rgb24')[top:bottom, left:right].copy()
    size = min(SIGNATURE_WIDTH, max(crop.shape[:2]))
    w = max(2, round(crop.shape[1]*size/max(crop.shape[:2])))
    h = max(2, round(crop.shape[0]*size/max(crop.shape[:2])))
    return av.VideoFrame.from_ndarray(crop, format='rgb24').reformat(
        width=w, height=h, format='rgb24').to_ndarray().astype('float32')


def _difference(left, right):
    import numpy as np
    if left.shape != right.shape:
        raise ValueError('比较区间的视频尺寸发生变化，请拆分区间。')
    delta = np.abs(left-right).mean(axis=2)
    mean, changed = float(delta.mean()), float((delta > PIXEL_DELTA).mean())
    return dict(mean_delta=round(mean, 6), changed_fraction=round(changed, 6),
                different=mean > MEAN_DELTA or changed > CHANGED_FRACTION)


def _occurrences(samples, region, allowed_range=None):
    runs, anchor = [], None
    compared = 0
    for row, frame in samples:
        row = dict(row)
        row['packet_eligible'] = (allowed_range is None or
                                 allowed_range['start'] <= row['time'] <= allowed_range['end'])
        if not row['packet_eligible']:
            row['packet_exclusion'] = 'source_pts_outside_plan_range'
        signature = _signature(frame, region)
        compared += 1
        difference = _difference(anchor, signature) if anchor is not None else None
        if anchor is None or difference['different']:
            runs.append(dict(id=f's{len(runs)+1:04d}', **row,
                             first_sample=row['time'], last_sample=row['time'], samples=1,
                             difference_from_previous=difference,
                             reason='first_observation' if anchor is None else 'local_pixel_change'))
            anchor = signature
        else:
            runs[-1]['last_sample'] = row['time']
            runs[-1]['samples'] += 1
            if not runs[-1]['packet_eligible'] and row['packet_eligible']:
                runs[-1].update(row)
                runs[-1].pop('packet_exclusion',None)
                runs[-1]['reason'] = 'first_packet_eligible_sample_in_occurrence'
    return runs, compared


def compare(plan_path, request_id, *, question, start, end, region=None,
            mode='candidates', limit=8):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', request_id or ''):
        raise ValueError('请求编号只能包含字母、数字、横线和下划线，最长 64 字。')
    question = protocol._text(question, 1000, '本次需要核对的问题')
    region = _region(region)
    if mode not in ('candidates', 'scan') or type(limit) is not int or not 1 <= limit <= 24:
        raise ValueError('mode 应为 candidates/scan，limit 应为 1–24。')
    root, plan, index = evidence._plan(plan_path)
    protocol._span(dict(start=start, end=end), index['source']['duration_seconds'])
    cap = 30 if mode == 'scan' else 120
    if not (start < end and end-start <= cap and start >= index['range']['start']
            and end <= index['range']['end']):
        raise ValueError(f'区间须在计划范围内，大于 0 且不超过 {cap} 秒。')
    spec = dict(version=VERSION, timing_version=TIMING_VERSION, question=question, start=start, end=end,
                region=region, mode=mode, limit=limit, revision=plan['revision'],
                index_sha256=plan['index_sha256'], plan_sha256=evidence._hash(root/'plan.json'))
    requests = root/'comparisons'
    receipt_path = requests/(request_id+'.json')
    with metadata_lock(root):
        requests.mkdir(exist_ok=True)
        if receipt_path.exists():
            old = evidence._load(receipt_path)
            if old.get('spec') != spec:
                raise ValueError('比较请求编号已用于另一组问题或参数。')
            return old | dict(replayed=True)
        write(receipt_path, dict(state='pending', request_id=request_id, spec=spec))
    began = time.perf_counter()
    stats = dict(decoder_frames=0, missing_timestamps=0, stopped_at_decode_limit=False)
    try:
        targets = _targets(index, start, end) if mode == 'candidates' else None
        video = protocol._path(index['source']['session_folder'], '录像.mp4')
        with closing(_frames(video, start, end, stats)) as decoded:
            samples = _candidate_frames(decoded, targets, stats) if targets is not None else decoded
            with closing(samples):
                occurrences, compared = _occurrences(samples, region, plan['range'])
        evidence._plan(plan_path)
        if evidence._hash(root/'plan.json') != spec['plan_sha256']:
            raise ValueError('比较期间计划改变，不能发布结果。')
        # Chronological prefix, never a temporal-spacing rule that hides a
        # short A→B→A sequence. Omitted occurrences are explicitly resumable.
        selected, omitted = occurrences[:limit], occurrences[limit:]
        covered = stats.pop('_covered_intervals',[])
        packet_pts,decoded_pts=stats.pop('_packet_pts',set()),stats.pop('_decoded_pts',set())
        unmatched=sorted(packet_pts-decoded_pts)
        stats['unaccounted_packet_pts_count']=len(unmatched)
        stats['unaccounted_packet_pts']=[float(t)-stats.get('pts_origin_seconds',0) for t in unmatched[:8]]
        unscanned, cursor = [], start
        for left,right in covered:
            if left > cursor+1e-7:
                unscanned.append([cursor,left])
            cursor=max(cursor,right)
        if cursor < end-1e-7:
            unscanned.append([cursor,end])
        result = dict(state='ready', request_id=request_id, spec=spec,
                      created_at=datetime.now(timezone.utc).isoformat(),
                      source=dict(session_id=plan['session_id'], revision=plan['revision'],
                                  video=str(video), fingerprint=index['source'].get('fingerprint'),
                                  index_sha256=plan['index_sha256']),
                      occurrences=selected, total_occurrences=len(occurrences),
                      selected_times=[row['time'] for row in selected if row['packet_eligible']],
                      omitted_occurrences=len(omitted),
                      next_start=omitted[0]['time'] if omitted else None,
                      comparison=dict(signature_max_side=SIGNATURE_WIDTH, pixel_delta=PIXEL_DELTA,
                                      mean_delta=MEAN_DELTA, changed_fraction=CHANGED_FRACTION,
                                      grouping='consecutive_against_occurrence_first_sample'),
                      coverage=dict(requested_range=[start,end],
                                    sampled_range=[occurrences[0]['first_sample'],occurrences[-1]['last_sample']]
                                    if occurrences else None,
                                    sampling='existing_candidate_pts_and_boundaries' if targets is not None else 'every_decoded_frame',
                                    complete_decoding=bool(compared) and not unscanned
                                    and not stats['stopped_at_decode_limit'] and not stats['missing_timestamps']
                                    and not stats.get('unknown_frame_durations')
                                    and not stats.get('coding_timing_discontinuities')
                                    and not stats.get('unknown_packet_durations')
                                    and not stats.get('missing_packet_pts') and not stats.get('missing_packet_dts')
                                    and not stats.get('unaccounted_packet_pts_count')
                                    and not stats.get('unresolved_target_times'),
                                    undecoded_ranges=unscanned[:32], undecoded_range_count=len(unscanned),
                                    resume_start=unscanned[0][0] if unscanned else None,
                                    unsampled_intervals_possible=mode=='candidates',
                                    boundary_basis='next_source_pts; final_frame_declared_duration',
                                    recording_drop_detection=False,
                                    continuous_semantic_coverage=False),
                      cost=dict(**stats, compared_frames=compared,
                                indexed_target_times=len(targets) if targets is not None else None,
                                elapsed_seconds=round(time.perf_counter()-began,6),
                                decoded_frame_cap=MAX_DECODE_FRAMES, images_issued=0),
                      actual_image_inspection=False,
                      notes=['局部像素不同不等于语义状态不同；动画也可能产生多个候选段。',
                             '段起止仅是已比较采样点，不证明期间一直相同；未采样处可能有短暂状态。',
                             '解码覆盖按相邻显示PTS计算，末帧用声明时长；不证明录制前未掉帧，编码时间不连续另列为未知。',
                             '保留连续出现顺序，不全局合并 A→B→A；limit 截断按时间顺序，不按间隔排除近邻。',
                             '用返回的 time 经原 visual-packet --at 领取图片，仍消耗同一份看图额度。'])
        if not occurrences:
            result['state'] = 'no_samples'
        with metadata_lock(root):
            write(receipt_path, result)
        return result | dict(replayed=False)
    except Exception as error:
        stats.pop('_packet_pts',None)
        stats.pop('_decoded_pts',None)
        with metadata_lock(root):
            write(receipt_path, dict(state='failed', request_id=request_id, spec=spec,
                                    error=str(error), cost=stats))
        raise
