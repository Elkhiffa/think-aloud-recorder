"""Offline evidence grouping and a shared issued-image budget; no model calls.

The detailed index is immutable. Similar pixels are not equivalent UI states.
Packets reserve budget before extraction, including repeated review requests.
"""
from bisect import bisect_right
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re

import agent_protocol as protocol
from recorder import write
from session_metadata import metadata_lock
import visual_nodes as visual

VERSION = 2
SELECTION_VERSION = 2


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    path = Path(path).resolve()
    if path.stat().st_size > visual.MAX_INDEX_BYTES:
        raise ValueError('取材文件过大。')
    return json.loads(path.read_text(encoding='utf-8'))


def _picture(index_path, relative):
    path = (index_path.parent / relative).resolve()
    if not path.is_relative_to(index_path.parent / 'images') or not path.is_file():
        raise ValueError('候选图片路径无效。')
    return path


def _signature(path):
    import av
    with av.open(str(path)) as image:
        frame = next(image.decode(video=0))
        return frame.reformat(width=64, height=36, format='rgb24').to_ndarray().astype('float32')


def _similar(left, right):
    import numpy as np
    difference = np.abs(left - right).mean(axis=2)
    return float(difference.mean()) <= 2.5 and float((difference > 18).mean()) <= .01


def _groups(index, index_path):
    """Consecutive occurrences only: A -> B -> A never becomes one global state."""
    pictures = {}
    transitions = []
    barriers = sorted(n['start'] for n in index['nodes'] if n['kind'] in ('change', 'transient'))
    for node in index['nodes']:
        if node['kind'] == 'transient':
            transitions.append(dict(kind='transient', start=node['start'], end=node['end'],
                                    times=sorted({f['time'] for f in node['frames']}),
                                    nodes=[node['id']], reason='before_peak_after_kept_together'))
        for frame in node['frames']:
            if frame.get('path'):
                row = pictures.setdefault(frame['time'], dict(path=frame['path'], nodes=[], motion=[]))
                row['nodes'].append(node['id'])
                if node['kind'] == 'motion':
                    row['motion'].append(node['id'])
    groups, anchor = [], None
    for at, row in sorted(pictures.items()):
        signature = _signature(_picture(index_path, row['path']))
        row['near_black'] = float(signature.max()) < 10
        previous = groups[-1] if groups else None
        barrier = previous and bisect_right(barriers, previous['end']) != bisect_right(barriers, at)
        motion = bool(previous and set(previous['motion']).intersection(row['motion']))
        similar = previous is not None and _similar(anchor, signature)
        if previous and not barrier and (similar or motion):
            previous['end'] = at
            previous['times'].append(at)
            previous['nodes'] = sorted(set(previous['nodes'] + row['nodes']))
            previous['motion'] = sorted(set(previous['motion']).intersection(row['motion']))
            if motion and not similar:
                previous['kind'] = 'motion'
                previous['reason'] = 'same_existing_motion_interval_not_same_ui_state'
        else:
            groups.append(dict(kind='appearance', start=at, end=at, times=[at], nodes=row['nodes'],
                               motion=row['motion'], reason='consecutive_near_pixels_only'))
            anchor = signature
    for group in groups:
        group.pop('motion')
    groups += transitions
    groups.sort(key=lambda g:(g['start'],g['end'],g['kind']))
    for i, group in enumerate(groups):
        group['id'] = f'g{i+1:05d}'
    return groups, pictures


def _initial_times_legacy(groups, limit):
    if not groups:
        return [], []
    chosen = {min(g['times'][0] for g in groups)}
    if limit > 1:
        chosen.add(max(g['times'][-1] for g in groups))
    protected = [g for g in groups if g['kind'] == 'transient']
    # Offer complete transitions. Shared frame times can also be offered by an
    # appearance group, but an incomplete transition remains explicitly deferred.
    # Reserve at least half the packet for broad temporal orientation. Otherwise
    # two three-frame transitions can consume an entire eight-image first look.
    transition_slots = min(limit-len(chosen), limit//2)
    ordered = visual._spread(protected, min(len(protected), transition_slots//3))
    for group in ordered:
        if len(chosen | set(group['times'])) <= limit:
            chosen.update(group['times'])
    others = [g for g in groups if g['kind'] != 'transient']
    representatives = {g['times'][len(g['times'])//2] for g in others} - chosen
    while representatives and len(chosen) < limit:
        # Cover the largest remaining time gap, rather than repeatedly picking
        # frames near already-selected endpoints. No extra fixed-rate extraction.
        at = max(representatives, key=lambda t:(min(abs(t-c) for c in chosen), -t))
        chosen.add(at)
        representatives.remove(at)
    deferred = [g['id'] for g in protected if not set(g['times']).issubset(chosen)]
    return sorted(chosen), deferred


def _initial_times(groups, limit, pictures=None):
    """A first look is temporal orientation, not a bundle-completeness quota.

    Preserve all transition references in the plan, but offer one representative
    per occurrence initially. Close neighbours are deferred to targeted packets.
    """
    pictures = pictures or {}
    available = {g['times'][len(g['times'])//2] for g in groups}
    usable = {t for t in available if not pictures.get(t, {}).get('near_black')}
    available = usable or available  # Dark footage can still be the only evidence.
    if not available:
        return [], []
    chosen = {min(available)}
    if limit > 1:
        chosen.add(max(available))
    spacing = (max(available)-min(available)) / max(2, 2*limit)
    remaining = available-chosen
    while remaining and len(chosen) < limit:
        at = max(remaining, key=lambda t:(min(abs(t-c) for c in chosen), -t))
        if min(abs(at-c) for c in chosen) < spacing:
            break
        chosen.add(at)
        remaining.remove(at)
    deferred = [g['id'] for g in groups if g['kind']=='transient'
                and not set(g['times']).issubset(chosen)]
    return sorted(chosen), deferred


def create_plan(index_path, output, *, total=24, initial=12, review=4):
    for value in (total,initial,review):
        if type(value) is not int or value < 0:
            raise ValueError('预算须为非负整数。')
    if not 1 <= initial <= total <= 200 or initial + review > total:
        raise ValueError('总预算应为 1–200，首轮至少 1，首轮加复核预留不能超过总预算。')
    index_path, output = Path(index_path).resolve(), Path(output).resolve()
    index, _ = visual._read_fresh_index(index_path, visual._Timings())
    digest = _hash(index_path)
    folder = Path(index['source']['session_folder']).resolve()
    library = folder.parent.parent if folder.parent.name == '场次' else folder
    if output.exists() or output.is_relative_to(library):
        raise ValueError('取材计划需保存在资料库以外的新目录。')
    groups, pictures = _groups(index,index_path)
    times, deferred = _initial_times(groups,initial,pictures)
    if _hash(index_path) != digest or protocol._identity(folder)[2] != index['revision']:
        raise ValueError('准备期间来源发生变化，请重新准备。')
    plan = dict(version=VERSION, selection_version=SELECTION_VERSION,
                kind='visual-evidence-plan', index=str(index_path), index_sha256=digest,
                revision=index['revision'], session_id=index['session_id'], range=index['range'],
                budget=dict(total=total, initial=initial, review_reserve=review),
                groups=groups, initial_times=times, deferred_transitions=deferred,
                source_coverage=index['coverage'],
                near_black_candidates=sum(p.get('near_black',False) for p in pictures.values()),
                notes=['相似像素分组不是界面等价、目标分段或已完成检查。',
                       '未配图节点与弱变化仍在完整索引中；它们没有因本计划被审查。',
                       '预算计经此入口发放的时间点次数，含补图和重复复核；不是实际模型用量。'])
    output.mkdir(parents=True)
    (output/'requests').mkdir()
    (output/'images').mkdir()
    visual._dump(output/'plan.json',plan)
    visual._dump(output/'budget.json',dict(version=VERSION,requests={}))
    return dict(plan=str(output/'plan.json'), available_image_times=len(pictures),
                appearance_groups=sum(g['kind']!='transient' for g in groups),
                protected_transitions=sum(g['kind']=='transient' for g in groups),
                initial_image_times=len(times), deferred_transitions=len(deferred),
                budget=plan['budget'], selection_version=SELECTION_VERSION,
                near_black_candidates=plan['near_black_candidates'], source_coverage=plan['source_coverage'],
                instruction='先领 initial 包；完整索引是回查资料，不是必须全读的任务清单。')


def _plan(path):
    path = Path(path).resolve()
    plan = _load(path)
    if path.name != 'plan.json' or plan.get('version') not in (1,VERSION) or plan.get('kind') != 'visual-evidence-plan':
        raise ValueError('取材计划格式无效。')
    if plan['version']==2 and 'selection_version' not in plan:
        raise ValueError('取材计划缺少选图版本。')
    if plan.get('selection_version',1) not in (1,SELECTION_VERSION):
        raise ValueError('不支持此计划的选图版本。')
    index_path = Path(plan['index']).resolve()
    index, _ = visual._read_fresh_index(index_path, visual._Timings())
    if _hash(index_path) != plan['index_sha256'] or index['revision'] != plan['revision']:
        raise ValueError('取材计划已过期，不能继续使用旧图。')
    return path.parent, plan, index


def _usage(plan, ledger):
    extensions=ledger.get('extensions',{})
    if not isinstance(extensions,dict):
        raise ValueError('追加额度记录无效。')
    additional=0
    for key,entry in extensions.items():
        if (not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key) or not isinstance(entry,dict)
                or type(entry.get('additional')) is not int or entry['additional']<1
                or entry.get('base_total')!=plan['budget']['total']
                or entry.get('index_sha256')!=plan['index_sha256']):
            raise ValueError('追加额度记录无效或不属于此计划。')
        additional+=entry['additional']
    total=plan['budget']['total']+additional
    if total>200:
        raise ValueError('单计划累计额度不能超过200。')
    phases = {phase:sum(len(r['times']) for r in ledger['requests'].values() if r['phase']==phase)
              for phase in ('initial','inspect','review')}
    used = sum(phases.values())
    return dict(issued=used, remaining=total-used, by_phase=phases,
                base_total=plan['budget']['total'],additional_total=additional,effective_total=total,
                extension_ids=list(extensions),
                review_reserved_remaining=max(0,plan['budget']['review_reserve']-phases['review']),
                note='pending/failed 请求仍保守计入；重复获取同一回执不再计入，实际重新看图请发新请求。')


def budget_status(plan_path):
    root,plan,_ = _plan(plan_path)
    with metadata_lock(root):
        return _usage(plan,_load(root/'budget.json'))


def extend_budget(plan_path, request_id, *, additional, reason):
    """Append an explicit, idempotent allowance; retain plan and every receipt."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',request_id or ''):
        raise ValueError('追加编号只能包含字母、数字、横线和下划线，最长64字。')
    if type(additional) is not int or not 1<=additional<=200:
        raise ValueError('新增额度应为1–200的整数。')
    reason=protocol._text(reason,1000,'需要补足的关键证据与追加理由')
    root,plan,_=_plan(plan_path)
    with metadata_lock(root):
        ledger=_load(root/'budget.json')
        usage=_usage(plan,ledger)
        extensions=ledger.setdefault('extensions',{})
        old=extensions.get(request_id)
        if old:
            if old['additional']!=additional or old['reason']!=reason:
                raise ValueError('追加编号已用于另一份额度或理由。')
            return dict(extension=old,budget=usage,replayed=True)
        entry=dict(id=request_id,additional=additional,reason=reason,
                   created_at=datetime.now(timezone.utc).isoformat(),issued_before=usage['issued'],
                   base_total=plan['budget']['total'],index_sha256=plan['index_sha256'],
                   plan_sha256=_hash(root/'plan.json'))
        extensions[request_id]=entry
        usage=_usage(plan,ledger)  # Validate cumulative cap before the atomic write.
        write(root/'budget.json',ledger)
        return dict(extension=entry,budget=usage,replayed=False)


def _window_times_legacy(index,start,end,limit):
    protocol._span(dict(start=start,end=end),index['source']['duration_seconds'])
    if start>=end or end-start>120:
        raise ValueError('补证据区间须大于 0 且不超过 120 秒。')
    if start<index['range']['start'] or end>index['range']['end']:
        raise ValueError('补证据区间须位于此索引覆盖的请求范围内。')
    selected = {start,end}
    bundles=[]
    for node in index['nodes']:
        for row in [node]+node.get('motion_observations',[]):
            if row['end']<start or row['start']>end:
                continue
            frames=sorted({f['time'] for f in row['frames'] if start<=f['time']<=end})
            if not frames:
                continue
            priority=0 if row['kind']=='transient' else 1 if row['kind']=='change' else 2
            distance=abs((row['start']+row['end'])/2-(start+end)/2)
            bundles.append((priority,distance,frames))
    deferred=0
    for _,_,frames in sorted(bundles):
        if len(selected|set(frames))<=limit:
            selected.update(frames)
        else:
            deferred+=1
    return sorted(selected),deferred


def _window_choice(index,start,end,limit):
    """Rank readable interval interiors, with temporal suppression.

    A weak observation can outrank an intense primary animation. This is a
    numerical readability heuristic, not detection of a popup or UI meaning.
    """
    protocol._span(dict(start=start,end=end),index['source']['duration_seconds'])
    if start>=end or end-start>120:
        raise ValueError('补证据区间须大于 0 且不超过 120 秒。')
    if start<index['range']['start'] or end>index['range']['end']:
        raise ValueError('补证据区间须位于此索引覆盖的请求范围内。')
    selected={start,end}
    candidates={}
    rows=list(visual._candidate_rows(index,start,end))
    for record in rows:
        row=record['row']
        left,right=max(start,row['start']),min(end,row['end'])
        at=(left+right)/2
        if row['kind'] in ('context','motion','transient'):
            representative=next((f['time'] for f in row['frames']
                                 if f['role'] in ('peak','representative')),at)
            if left<=representative<=right:
                at=representative
        metrics=row.get('metrics',{})
        def number(name,default):
            value=metrics.get(name,default)
            return value if protocol._number(value) else default
        # Weak-change intervals describe how long a local change remained
        # readable. Their centre avoids repeatedly returning the onset frame.
        duration=min(3,max(.05,right-left))
        movement=min(1,max(0,number('moving_tile_fraction',.5)))
        delta=max(0,number('adjacent_global',.05))
        quality=duration*max(.05,1-movement)/(.01+delta)
        if row['kind'] in ('context','motion'):
            quality=1.0
        candidate=dict(time=at,quality=quality,id=record['id'],level=record['level'],
                       interval=[left,right],reason='interval_readability_and_time_separation')
        if at not in candidates or quality>candidates[at]['quality']:
            candidates[at]=candidate
    gap=(end-start)/max(1,limit-1)
    decisions=[]
    while candidates and len(selected)<limit:
        def rank(item):
            distance=min(abs(item['time']-t) for t in selected)
            return item['quality']*min(1,distance/gap),distance,-item['time']
        best=max(candidates.values(),key=rank)
        candidates.pop(best['time'])
        # Do not use spare slots on frame-adjacent variants of the same burst.
        if min(abs(best['time']-t) for t in selected)<gap/4:
            continue
        selected.add(best['time'])
        decisions.append(best)
    deferred=sum(not {f['time'] for f in r['row']['frames'] if start<=f['time']<=end}.issubset(selected)
                 for r in rows)
    return sorted(selected),deferred,decisions


def _window_times(index,start,end,limit):
    times,deferred,_=_window_choice(index,start,end,limit)
    return times,deferred


def _frame(video,at,*,image_width=960):
    # Seek to the requested display time; preserve the actual PTS of its frame.
    with closing(visual._decode(video,at,at,{})) as decoded:
        try:
            actual,picture=next(decoded)
        except StopIteration:
            raise ValueError(f'{at:g} 秒没有可用画面。') from None
        if image_width!=960 and actual!=at:
            raise ValueError('高清取图未复现指定的原始PTS；请使用索引或旧回执的实际时间，不替换为邻帧。')
        return actual,visual._jpeg(picture,width=image_width)


def packet(plan_path, request_id, *, phase, question, times=None, start=None, end=None, limit=6,
           image_width=960):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',request_id or ''):
        raise ValueError('请求编号只能包含字母、数字、横线和下划线，最长 64 字。')
    if phase not in ('initial','inspect','review'):
        raise ValueError('取材阶段无效。')
    question=protocol._text(question,1000,'本次需要核对的问题')
    if type(limit) is not int or not 2<=limit<=12:
        raise ValueError('单次补图上限应为 2–12。')
    if type(image_width) is not int or image_width not in (960,1920):
        raise ValueError('图片最大宽度应为960或1920，不放大原片。')
    if image_width!=960 and (phase=='initial' or times is None or not 1<=len(times)<=2):
        raise ValueError('高清取图仅用于补图/复核的1–2个明确原始PTS，不用于自动区间包。')
    root,plan,index=_plan(plan_path)
    deferred=0
    decisions=[]
    selection_version=plan.get('selection_version',1)
    if phase=='initial':
        if times is not None or start is not None or end is not None:
            raise ValueError('首轮使用计划中的代表图；定向补图请使用 inspect。')
        wanted=plan['initial_times']
    elif times is not None:
        if start is not None or end is not None or not times or len(times)>12:
            raise ValueError('指定时间点应为 1–12 个，且不能同时指定区间。')
        for at in times:
            protocol._span(dict(start=at,end=at),index['source']['duration_seconds'])
            if not index['range']['start']<=at<=index['range']['end']:
                raise ValueError('时间点不在计划范围内。')
        wanted=sorted(set(times))
    else:
        if start is None or end is None:
            raise ValueError('补图或复核须给出具体时间点或短区间。')
        if selection_version==1:
            wanted,deferred=_window_times_legacy(index,start,end,limit)
        else:
            wanted,deferred,decisions=_window_choice(index,start,end,limit)
    if not wanted:
        raise ValueError('此计划没有可发放的画面。')
    spec=dict(phase=phase,question=question,times=wanted,deferred_bundles=deferred)
    if selection_version!=1:
        spec['selection_version']=selection_version
    if image_width!=960:
        spec['image_width']=image_width
    request_path=root/'requests'/(request_id+'.json')
    with metadata_lock(root):
        ledger=_load(root/'budget.json')
        old=ledger['requests'].get(request_id)
        if old:
            if old.get('image_width',960)!=image_width or any(old.get(k)!=v for k,v in spec.items()):
                raise ValueError('请求编号已用于另一组问题或画面。')
            if request_path.is_file():
                receipt=_load(request_path)
                for frame in receipt['frames']:
                    path=Path(frame['path']).resolve()
                    if not path.is_relative_to(root/'images') or _hash(path)!=frame['sha256']:
                        raise ValueError('已发放画面校验失败，不能重用旧回执。')
                return receipt | dict(budget=_usage(plan,ledger),replayed=True)
            return dict(state=old['state'],request_id=request_id,budget=_usage(plan,ledger),
                        note='请求已经保留预算；不自动重跑，请检查工作记录。')
        usage=_usage(plan,ledger)
        if phase=='initial' and selection_version!=1 and usage['by_phase']['initial']:
            return dict(state='initial_already_issued',budget=usage,
                        note='首轮已发放；重取原回执请用原编号，进一步取材须走 inspect/review。')
        reserve=usage['review_reserved_remaining'] if phase!='review' else 0
        if len(wanted)>usage['remaining']-reserve or (phase=='initial' and
                    usage['by_phase']['initial']+len(wanted)>plan['budget']['initial']):
            return dict(state='budget_exceeded',requested=len(wanted),budget=usage,
                        note='未取图、未占用新预算。保留未明区间；不得新建计划绕过同场预算。')
        ledger['requests'][request_id]=dict(spec,state='pending')
        write(root/'budget.json',ledger)
    try:
        video=protocol._path(index['source']['session_folder'],'录像.mp4')
        indexed={f['time']:f['path'] for n in index['nodes'] for f in n['frames'] if f.get('path')}
        frames=[]
        for at in wanted:
            if at in indexed and image_width==960:
                picture=_picture(Path(plan['index']),indexed[at])
                content=picture.read_bytes(); actual=at
                origin='existing_index'
            else:
                actual,content=(_frame(video,at) if image_width==960
                                else _frame(video,at,image_width=image_width))
                origin='targeted_seek'
            digest=hashlib.sha256(content).hexdigest()
            dimensions={}
            if image_width!=960:
                import av
                with av.open(BytesIO(content),format='mjpeg') as image:
                    stream=image.streams.video[0]
                    dimensions=dict(width=stream.width,height=stream.height)
            picture=root/'images'/(digest+'.jpg')
            with metadata_lock(root):
                try:
                    with picture.open('xb') as handle: handle.write(content)
                except FileExistsError:
                    if _hash(picture)!=digest:
                        raise ValueError('已保存画面校验失败。')
            frames.append(dict(requested_time=at,time=actual,path=str(picture),sha256=digest,origin=origin,
                               **dimensions))
        _plan(plan_path)  # Revalidate after seeking, before publishing any image references.
        result=dict(state='ready',request_id=request_id,phase=phase,question=question,frames=frames,
                    max_image_width=image_width,
                    deferred_bundles=deferred,actual_image_inspection=False,
                    selection_version=selection_version,selection=decisions,
                    deferred_initial_transitions=len(plan['deferred_transitions']) if phase=='initial' else None,
                    note='只有实际查看后才能记录检查范围；本包不证明整个时间段已检查。')
        with metadata_lock(root):
            ledger=_load(root/'budget.json')
            ledger['requests'][request_id]['state']='ready'
            write(request_path,result)
            write(root/'budget.json',ledger)
            return result | dict(budget=_usage(plan,ledger),replayed=False)
    except Exception:
        with metadata_lock(root):
            ledger=_load(root/'budget.json')
            ledger['requests'][request_id]['state']='failed'
            write(root/'budget.json',ledger)
        raise
