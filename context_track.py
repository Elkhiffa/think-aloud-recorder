"""Local OCR context derived only from the source video, never session revision."""
import json
import math
import re
from pathlib import Path

import agent_protocol as protocol
import game_catalog
import layout_common

TRACK = 'context-track.json'


def _source_video(folder):
    stat = (Path(folder) / '录像.mp4').stat()
    return dict(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _ocr_engine(title=False):
    # 路径 2：context-build 在没有本地 OCR 的环境中运行；安装版的 OCR 来自设置里下载的识别组件。
    from ocr_component import MISSING, ensure_importable
    ensure_importable()
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise ValueError(MISSING) from error
    if not title:
        return RapidOCR()
    # 路径 2：默认检测把短边放大到 736，约 60 像素高的标题裁图会比整屏还慢；
    # 标题区改为检测不放大，裁图先做 2 倍插值。cv2 随 rapidocr 安装。
    import cv2
    engine = RapidOCR(det_limit_type='max', det_limit_side_len=2000)
    return lambda image: engine(cv2.resize(image, None, fx=2, fy=2,
                                           interpolation=cv2.INTER_CUBIC))


def _sample_frames(path, interval, start, end):
    """Seek to interval midpoints, yielding actual video PTS, 960-wide BGR and source-size BGR."""
    import av
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_count = 2
        origin = (container.start_time or 0) / av.time_base
        stop = end if end is not None else container.duration / av.time_base
        target = start + interval / 2
        while target < stop:
            container.seek(max(0, int((target + origin) / stream.time_base)),
                           stream=stream, backward=True, any_frame=False)
            for frame in container.decode(stream):
                at = float(frame.pts * frame.time_base) - origin
                if at < target:
                    continue
                if at >= stop:
                    return
                height = round(frame.height * 960 / frame.width)
                image = frame.reformat(width=960, height=height, format='bgr24')
                # 路径 2：焦点框顶部的小三角只有约 16 像素宽，960 宽下与框线融在一起，要在原尺寸上确认。
                yield round(at, 6), image.to_ndarray(), frame.to_ndarray(format='bgr24')
                break
            else:
                return
            target += interval


def _items(result):
    items = []
    # 路径 2：空画面与低置信度 OCR 不进入供 agent 读取的情景文字。
    for box, text, confidence in result or []:
        # 路径 4/5：换环境或打包后的 rapidocr 版本可能把置信度返回为字符串。
        if float(confidence) < .6:
            continue
        x = sum(point[0] for point in box) / len(box)
        y = sum(point[1] for point in box) / len(box)
        # 路径 2：激活页签要按字框取字色和底色；读取方只用前三项，角点追加在末尾。
        corners = [[round(float(px)), round(float(py))] for px, py in box]
        items.append([round(float(x), 2), round(float(y), 2), text, corners])
    return items


def _titles(engine, image, regions):
    """OCR each title crop; x is the crop's normalized left edge."""
    height, width = image.shape[:2]
    titles = []
    for region in regions:
        x, y, w, h = region['rect']
        detect = region.get('detect')
        if detect is not None:
            left = layout_common._panel_left(image, detect['x_range'])
            # 路径 2：画面上没有贯穿的面板边界时退回目录给出的原位置。
            if left is not None:
                x = left / width
        left, top = round(x * width), round(y * height)
        result, _ = engine(image[top:top + round(h * height), left:left + round(w * width)])
        text = ' '.join(item[2] for item in _items(result))
        if text:
            titles.append(dict(region=region['id'], text=text, x=round(x, 4)))
    return titles


_DERIVED = ('tabs', 'headings', 'focus')


def _recompute(folder, cached, params, layout):
    """Re-derive layout fields from stored boxes on freshly decoded frames; None if frames drift."""
    frames = [dict(frame) for frame in cached['frames']]
    for frame in frames:
        for key in _DERIVED:
            frame.pop(key, None)
    # 路径 2：用户从目录删掉规则时只需去掉旧结果，不必解码。
    count = 0 if layout else len(frames)
    sampled = _sample_frames(folder / '录像.mp4', params['interval'], params['start'],
                             params['end']) if layout else ()
    for at, image, full in sampled:
        # 路径 4：旧版本的解码器取到的帧时刻可能不同，字框就对不上，改为整段重跑。
        if count >= len(frames) or frames[count]['t'] != at:
            return None
        frame = frames[count]
        if 'items' in frame:
            frame.update(layout_common.derive(image, full, frame['items'], layout))
        count += 1
    if count != len(frames):
        return None
    track = dict(cached, frames=frames)
    # 路径 4：M3 回填的轨道把规则记在 active_tabs 下，换成 layout。
    track.pop('active_tabs', None)
    track.pop('layout', None)
    if layout:
        track['layout'] = layout
    return track


CHECK = 'screen-check.json'


def _grab(folder, at):
    """960-wide and source-size BGR of the frame at `at`, or None past the end."""
    from contextlib import closing
    import visual_nodes
    with closing(visual_nodes._decode(Path(folder) / '录像.mp4', at, at, {})) as decoded:
        _, frame = next(decoded, (None, None))
    if frame is None:
        return None
    small = frame.reformat(width=960, height=round(frame.height * 960 / frame.width), format='bgr24')
    return small.to_ndarray(), frame.to_ndarray(format='bgr24')


def check_screens(folder, instances):
    """Compare each instance's screen id with the tabs lit at its checked frame (the first video evidence).

    A segment that sits in a detected tab row but is not the lit one is reported; segments that are not
    visible as tabs say nothing. Results are cached per moment in screen-check.json, keyed by the video
    and the catalog layout, so a corrected resubmission does not OCR again."""
    folder = Path(folder)
    moments = {}
    for instance in instances:
        at = next((row['start'] for row in instance.get('evidence', ()) if row.get('kind') == 'video'), None)
        screen = instance.get('screen')
        if at is not None and isinstance(screen, str) and '/' in screen:
            moments.setdefault(float(at), []).append(instance)
    out = dict(checked=0, warnings=[])
    if not moments:
        return out
    catalog = game_catalog.session_catalog(folder)
    layout = catalog.get('layout') if catalog is not None else None
    # 路径 4：没有版式规则的游戏不核对，提交照常。
    if not layout or 'tabs' not in layout:
        return dict(out, skipped='界面目录没有 layout.tabs，未核对页签。')
    try:
        engine = _ocr_engine()
    except ValueError as error:
        # 路径 3：安装版不带画面文字识别，agent 经本地接口提交时只说明未核对，不拦提交。
        return dict(out, skipped=f'{error}，未核对页签。')
    source = _source_video(folder)
    path = folder / CHECK
    cache = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    if cache.get('source_video') != source or cache.get('layout') != layout:
        cache = dict(source_video=source, layout=layout, frames={})
    for at, group in sorted(moments.items()):
        key = f'{at:g}'
        tabs = cache['frames'].get(key)
        if tabs is None:
            grabbed = _grab(folder, at)
            # 路径 3：核对时刻超出录像末尾（validate 只要求在录像时长内）时跳过这一刻。
            if grabbed is None:
                continue
            image, full = grabbed
            result, _ = engine(image)
            tabs = cache['frames'][key] = layout_common.derive(image, full, _items(result), layout).get('tabs', [])
        out['checked'] += 1
        for instance in group:
            parts = instance['screen'].split('/')
            every = [re.sub(r'（.*?）', '', parts[0])] + parts[1:]
            for tab in tabs:
                # 路径 3：组名常与第一个页签同名（属性/体质），模块入口与更深一段同排（装备/槽位调平）；
                # 编号里任何一段正亮在这一排里，就算对上了（M4 验收里这两类占误报的多数）。
                if any(layout_common._same_tab(segment, tab['active']) for segment in every):
                    continue
                for segment in every[:3]:
                    if any(layout_common._same_tab(segment, t) for t in tab['row']):
                        out['warnings'].append(dict(instance=instance.get('id'), at=at, screen=instance['screen'],
                                                    segment=segment, lit=tab['active'], row=tab['row']))
                        break
    protocol._write(folder, CHECK, cache)
    return out


def _track_path(folder, output=None):
    return (Path(output) if output is not None else Path(folder)) / TRACK


def build(folder, *, interval=5, title_interval=2, full_interval=10, start=0, end=None,
          output=None, rematch=False):
    """Build or reuse a track; catalog title_regions select dense title + sparse full OCR."""
    folder = Path(folder)
    path = _track_path(folder, output)
    # 路径 2：修订目录后 --rematch 仅重算界面分段，保留原抽帧范围。
    if rematch:
        track = load_track(folder, output=output)
        track['screens'] = game_catalog.match_screens(
            game_catalog.session_catalog(folder), track['frames'])
        protocol._write(path.parent, path.name, track)
        return dict(path=str(path.resolve()), frames=len(track['frames']), reused=True,
                    rematched=True, interval=track['interval'],
                    start=track.get('start', 0), end=track.get('end'))
    # 路径 2：CLI 的区间/间隔输入必须符合声明的采样范围。
    if not math.isfinite(start) or start < 0 or (end is not None and
            (not math.isfinite(end) or end <= start)):
        raise ValueError('抽帧范围需满足 0 ≤ start < end。')
    catalog = game_catalog.session_catalog(folder)
    # 路径 4：没有界面目录或目录没有 title_regions 时保持单层 version 1。
    regions = catalog.get('title_regions') if catalog is not None else None
    if regions:
        if not (math.isfinite(title_interval) and math.isfinite(full_interval)
                and 1 <= title_interval <= 10 and title_interval <= full_interval <= 60):
            raise ValueError('标题间隔须在 1–10 秒之间，整屏间隔须在标题间隔至 60 秒之间。')
        params = dict(version=2, interval=title_interval, title_interval=title_interval,
                      full_interval=full_interval, start=start, end=end, title_regions=regions)
    else:
        if not math.isfinite(interval) or not 2 <= interval <= 10:
            raise ValueError('抽帧间隔必须在 2–10 秒之间。')
        params = dict(version=1, interval=interval, start=start, end=end)
    layout = catalog.get('layout') if catalog is not None else None
    if layout:
        params['layout'] = layout
    shown = {key: value for key, value in params.items()
             if key not in ('version', 'title_regions', 'layout')}
    source = _source_video(folder)
    # 路径 2/1：相同视频及采样参数复用；转写、记录者变化不参与有效性。
    # 路径 2：用户按设计规范改了标题区坐标，旧标题文字不再对应，需要重跑。
    if path.is_file():
        cached = json.loads(path.read_text(encoding='utf-8'))
        sampled = cached['source_video'] == source and all(
            cached.get(key, 0 if key == 'start' else None) == value
            for key, value in params.items() if key != 'layout')
        if sampled and cached.get('layout') == layout and 'active_tabs' not in cached:
            return dict(path=str(path.resolve()), frames=len(cached['frames']), reused=True,
                        **shown)
        # 路径 2：用户改了目录里的版式规则 → 字框已在轨道里，只重新解码取色，不重跑 OCR。
        # 路径 4：旧轨道没有字框，只能整段重跑。
        if sampled and all(len(item) == 4 for frame in cached['frames']
                           for item in frame.get('items', ())):
            track = _recompute(folder, cached, params, layout)
            if track is not None:
                protocol._write(path.parent, path.name, track)
                return dict(path=str(path.resolve()), frames=len(track['frames']), reused=True,
                            recomputed=True, **shown)
    engine = _ocr_engine()
    title_engine = _ocr_engine(title=True) if regions else None
    frames, next_full = [], start
    for at, image, full in _sample_frames(folder / '录像.mp4', params['interval'], start, end):
        frame = dict(t=at)
        if regions:
            frame['titles'] = _titles(title_engine, image, regions)
            # 路径 2：两层模式下整屏 OCR 只在整屏间隔的格点上运行，其余帧只有标题。
            if at < next_full:
                frames.append(frame)
                continue
            while next_full <= at:
                next_full += full_interval
        result, _ = engine(image)
        frame['items'] = _items(result)
        if layout:
            frame.update(layout_common.derive(image, full, frame['items'], layout))
        frames.append(frame)
    track = dict(version=params.pop('version'), source_video=source, **params,
                 frames=frames,
                 screens=game_catalog.match_screens(catalog, frames))
    path.parent.mkdir(parents=True, exist_ok=True)
    protocol._write(path.parent, path.name, track)
    return dict(path=str(path.resolve()), frames=len(frames), reused=False, **shown)


def load_track(folder, *, output=None):
    """Read a fresh track for this session; optional output supports smoke artifacts."""
    track = json.loads(_track_path(folder, output).read_text(encoding='utf-8'))
    # 路径 2：读取曾生成的情景轨道时，原录像被替换则需重建。
    if track['source_video'] != _source_video(folder):
        raise ValueError('录像已变化，请重新运行 context-build。')
    return track


def _title(items):
    ordered = sorted(items, key=lambda item: (item[1], item[0]))
    top = [item[2] for item in ordered if item[1] < 70]
    return (''.join(top) if top else ordered[0][2] if ordered else '')[:10]


def read_track(folder, *, start=None, end=None, compact=False, output=None):
    """Return time-filtered OCR; compact merges adjacent frames, preferring title text."""
    track = load_track(folder, output=output)
    frames, previous_title, previous_tabs, group_full = [], None, None, False
    for frame in track['frames']:
        at, items = frame['t'], frame.get('items')
        if (start is not None and at < start) or (end is not None and at > end):
            continue
        titles = ' '.join(title['text'] for title in frame.get('titles', ()))
        text = '\n'.join(item[2] for item in items) if items is not None else titles
        # 没报出激活页签（只有标题区的帧、或规则保持沉默）当作未知，不当作“换了页签”。
        # 焦点不进分段输出：手柄操作时它每几秒就变。
        tabs = [tab['active'] for tab in frame.get('tabs', ())] or None
        named = frame.get('headings', {})
        headings = ([named['main']] if 'main' in named else []) + named.get('side', []) or None
        if compact:
            # 路径 2：两层轨道中只识别了标题区、且标题区无字的帧没有可读文字，不参与合并。
            if items is None and not titles:
                continue
            title = titles or _title(items)
            # 路径 2：同一标题下切换页签（商店 精选→月卡）是换了界面，不能并进一段。
            # 侧窗标题在顶部文字里，换侧窗时 title 已经不同，不必另比。
            if frames and title == previous_title and (
                    tabs is None or previous_tabs is None or tabs == previous_tabs):
                frames[-1]['end'] = at
                # 路径 2：组首只有标题时，用组内第一张整屏帧补全文字，避免画面上的反证被略去。
                if items is not None and not group_full:
                    frames[-1]['text'], group_full = text[:120], True
                if tabs and previous_tabs is None:
                    frames[-1]['tabs'] = tabs
                if headings and 'headings' not in frames[-1]:
                    frames[-1]['headings'] = headings
                previous_tabs = previous_tabs if tabs is None else tabs
                continue
            frames.append(dict(t=at, end=at, text=text[:120]))
            frames[-1].update({k: v for k, v in (('tabs', tabs), ('headings', headings)) if v})
            previous_title, previous_tabs, group_full = title, tabs, items is not None
        else:
            row = dict(t=at, text=text)
            if 'titles' in frame:
                row['titles'] = frame['titles']
            if items is not None:
                # 路径 2：字框角点只供重算页签，不塞进 agent 读取的文字。
                row['items'] = [item[:3] for item in items]
            for key in _DERIVED:
                if key in frame:
                    row[key] = frame[key]
            frames.append(row)
    layers = {key: track[key] for key in ('title_interval', 'full_interval') if key in track}
    return dict(version=track['version'], interval=track['interval'], **layers,
                source_video=track['source_video'],
                frames=frames, screens=track['screens'])


def _built_with(folder, layout):
    try:
        return json.loads((Path(folder) / TRACK).read_text(encoding='utf-8')).get('layout') == layout
    except (OSError, ValueError):
        return False


def rebuild(vault, game=None, workers=2, progress=print):
    """Rebuild every session's track with the catalog's layout rules, a few sessions at a time.

    Sessions already built with the current layout are skipped, so an interrupted run can simply be started again.
    Each session runs context-build in its own process (OCR memory is freed per session); one log per session in
    state/logs/context-rebuild/ beside this app. Writes only each session's context-track.json."""
    from concurrent.futures import ThreadPoolExecutor
    import subprocess
    import sys
    import time
    import game_catalog
    from ocr_component import MISSING, ensure_importable
    vault = Path(vault).resolve()
    game = game or vault.name
    path = game_catalog.catalog_path(vault, game)
    if not path.is_file():
        raise ValueError(f'资料库里没有这个游戏的界面目录：{path}')
    layout = json.loads(path.read_text(encoding='utf-8-sig')).get('layout')
    if layout is None:
        raise ValueError('界面目录里还没有版式规则：先在 设置 → 游戏 里启用“界面路径识别”，或运行 agent_cli.py layout-apply。')
    if not ensure_importable():
        raise ValueError(MISSING)
    app = Path(__file__).resolve().parent
    logs = app / 'state' / 'logs' / 'context-rebuild'
    logs.mkdir(parents=True, exist_ok=True)

    def one(folder):
        if _built_with(folder, layout):
            return folder.name, 'skipped', 0
        started = time.time()
        with (logs / (folder.name[:22] + '.log')).open('w', encoding='utf-8') as log:
            code = subprocess.call([sys.executable, '-B', '-X', 'utf8', str(app / 'agent_cli.py'), 'context-build', str(folder)],
                                   cwd=app, stdout=log, stderr=subprocess.STDOUT)
        return folder.name, 'ok' if code == 0 and _built_with(folder, layout) else f'failed (exit {code})', round(time.time() - started)

    sessions = sorted(path.parent for path in (vault / '场次').glob('*/录像.mp4'))
    progress(f'{len(sessions)} 场')
    rows = []
    with ThreadPoolExecutor(max(1, workers)) as pool:
        for name, state, seconds in pool.map(one, sessions):
            progress(f"{time.strftime('%H:%M')} {name[:22]} {state} {seconds // 60} min")
            rows.append(dict(session=name, state=state, seconds=seconds))
    return dict(sessions=len(rows), built=sum(row['state'] == 'ok' for row in rows),
                skipped=sum(row['state'] == 'skipped' for row in rows),
                failed=[row['session'] for row in rows if row['state'] not in ('ok', 'skipped')], logs=str(logs))
