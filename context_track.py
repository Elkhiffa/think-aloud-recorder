"""Local OCR context derived only from the source video, never session revision."""
import json
import math
import re
from pathlib import Path

import numpy as np

import agent_protocol as protocol
import game_catalog

TRACK = 'context-track.json'
# Panel edge: brightness step across 3 px, averaged over 9 rows, must exceed 2.5
# grey levels in the same direction on at least 60% of rows.
_EDGE_SPAN, _EDGE_ROWS, _EDGE_STEP, _EDGE_COVER = 3, 9, 2.5, .6
# Tab rows (measured 2026-10 on 21 16:9 + 5 1920x804 sessions): short texts whose centres differ < 0.45 text heights,
# heights within 1.35x, gaps up to 7 heights, pitch within 1.5x; minimum text height 8/1080.
_TAB_CHARS, _ROW_DY, _ROW_HEIGHTS, _ROW_GAP, _ROW_PITCH, _TAB_MIN_H = 6, .45, 1.35, 7, 1.5, 8 / 1080
_TAB_NOISE = {'返回', '说明'}


def _source_video(folder):
    stat = (Path(folder) / '录像.mp4').stat()
    return dict(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _ocr_engine(title=False):
    # 路径 2：context-build 在未安装本地 OCR 的开发环境中运行。
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise ValueError('OCR 依赖未安装') from error
    if not title:
        return RapidOCR()
    # 路径 2：默认检测把短边放大到 736，约 60 像素高的标题裁图会比整屏还慢；
    # 标题区改为检测不放大，裁图先做 2 倍插值。cv2 随 rapidocr 安装。
    import cv2
    engine = RapidOCR(det_limit_type='max', det_limit_side_len=2000)
    return lambda image: engine(cv2.resize(image, None, fx=2, fy=2,
                                           interpolation=cv2.INTER_CUBIC))


def _sample_frames(path, interval, start, end):
    """Seek to interval midpoints, yielding actual video PTS and 960-wide BGR."""
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
                yield round(at, 6), image.to_ndarray()
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


def _game_rows(image):
    """Top and bottom of the game picture, skipping letterbox rows."""
    rows = image.mean(axis=(1, 2))
    lit = np.flatnonzero(rows >= 6)
    return (int(lit[0]), int(lit[-1]) + 1) if len(lit) else (0, image.shape[0])


def _tab_text(text):
    text = re.sub(r'\s', '', text)
    # 路径 2：按键提示（Q、RB）、数字和返回键会与页签同排对齐，不是页签。
    return (0 < len(text) <= _TAB_CHARS and text not in _TAB_NOISE
            and not re.fullmatch(r'[A-Za-z0-9]{1,2}', text)
            and not re.fullmatch(r'[\d\W_xX×]+', text))


def _tab_rows(items, min_height):
    boxes = []
    for index, item in enumerate(items):
        if len(item) < 4 or not _tab_text(item[2]):
            continue
        xs, ys = [point[0] for point in item[3]], [point[1] for point in item[3]]
        box = dict(i=index, text=item[2], x0=min(xs), x1=max(xs), cx=(min(xs) + max(xs)) / 2,
                   cy=(min(ys) + max(ys)) / 2, h=max(ys) - min(ys))
        if box['h'] > min_height:
            boxes.append(box)
    rows = {}
    for anchor in boxes:
        same = sorted((box for box in boxes
                       if abs(box['cy'] - anchor['cy']) < _ROW_DY * max(box['h'], anchor['h'])
                       and max(box['h'], anchor['h']) / min(box['h'], anchor['h']) < _ROW_HEIGHTS),
                      key=lambda box: box['cx'])
        start = end = same.index(anchor)
        close = lambda a, b: -.3 * anchor['h'] < b['x0'] - a['x1'] <= _ROW_GAP * anchor['h']
        while end + 1 < len(same) and close(same[end], same[end + 1]):
            end += 1
        while start > 0 and close(same[start - 1], same[start]):
            start -= 1
        members, at = same[start:end + 1], same.index(anchor) - start
        if len(members) >= 3:
            # 节距不规律处截断：从 anchor 两侧最近的节距出发。
            pitches = [b['cx'] - a['cx'] for a, b in zip(members, members[1:])]
            ref = pitches[min(at, len(pitches) - 1)]
            low, high = at, at
            while high < len(pitches) and 1 / _ROW_PITCH <= pitches[high] / ref <= _ROW_PITCH:
                high += 1
            while low > 0 and 1 / _ROW_PITCH <= pitches[low - 1] / ref <= _ROW_PITCH:
                low -= 1
            members = members[low:high + 1]
        if len(members) >= 2:
            rows[tuple(box['i'] for box in members)] = members
    # 一个字框只归属最长的那一排。
    out, used = [], set()
    for ids, members in sorted(rows.items(), key=lambda pair: -len(pair[0])):
        if not used & set(ids):
            used |= set(ids)
            out.append(members)
    return out


def _ink(image, lab, box):
    """Median text colour of one box: pixels farthest from the surrounding ring's colour."""
    height, width = image.shape[:2]
    h = max(3.0, box['h'])
    y0, y1 = box['cy'] - box['h'] / 2, box['cy'] + box['h'] / 2
    clip = lambda left, top, right, bottom: (max(0, int(round(left))), max(0, int(round(top))),
                                             min(width, int(round(right))), min(height, int(round(bottom))))
    ox0, oy0, ox1, oy1 = clip(box['x0'] - .5 * h, y0 - .5 * h, box['x1'] + .5 * h, y1 + .5 * h)
    ring = np.ones((oy1 - oy0, ox1 - ox0), bool)
    ix0, iy0, ix1, iy1 = clip(box['x0'] - .1 * h, y0 - .1 * h, box['x1'] + .1 * h, y1 + .1 * h)
    ring[iy0 - oy0:iy1 - oy0, ix0 - ox0:ix1 - ox0] = False
    bx0, by0, bx1, by1 = clip(box['x0'], y0, box['x1'], y1)
    if not ring.any() or bx1 <= bx0 or by1 <= by0:
        return None
    background = np.median(lab[oy0:oy1, ox0:ox1][ring], axis=0)
    distance = np.sqrt(((lab[by0:by1, bx0:bx1] - background) ** 2).sum(axis=2))
    chosen = distance >= max(8.0, float(np.percentile(distance, 75)))
    if chosen.sum() < 10:
        chosen = distance >= np.percentile(distance, 85)
    return np.median(image[by0:by1, bx0:bx1][chosen].reshape(-1, 3), axis=0)


def _gold(bgr, rules):
    import cv2
    colour = np.asarray(bgr, np.float32).reshape(1, 1, 3) / 255
    b = float(cv2.cvtColor(colour, cv2.COLOR_BGR2Lab)[0, 0, 2])
    high, low = float(colour.max()), float(colour.min())
    return b >= rules['gold']['min_b'] and (high - low) / max(high, 1e-6) >= rules['gold']['min_s']


def _active_tabs(image, items, rules):
    """Top and horizontal-text tab rows with exactly one gold tab; anything else stays silent."""
    import cv2
    top, bottom = _game_rows(image)
    span = bottom - top
    lab = None
    tabs = []
    for members in _tab_rows(items, _TAB_MIN_H * span):
        y = (sum(box['cy'] for box in members) / len(members) - top) / span
        texts = [box['text'] for box in members]
        if y < rules['top_max_y']:
            kind = 'top'
        elif any(low <= y <= high for low, high in rules['text_bands']) or any(
                len(set(texts) & set(row['tabs'])) >= 2 for row in rules.get('text_rows', ())):
            kind = 'text'
        else:
            # 路径 2：带外的金色字多是按钮、角标和卡片标题（2026-10 随机 80 帧里带外 16 排全是）。
            continue
        if lab is None:
            lab = cv2.cvtColor(image.astype(np.float32) / 255, cv2.COLOR_BGR2Lab)
        inks = [_ink(image, lab, box) for box in members]
        gold = [index for index, ink in enumerate(inks) if ink is not None and _gold(ink, rules)]
        # 路径 2：两个金色（商店“和鸣”推广字）或没有金色时不报，宁缺勿错。
        if len(gold) == 1:
            tabs.append(dict(kind=kind, active=texts[gold[0]], row=texts))
    return tabs


def _panel_left(image, x_range):
    """Return the column where a same-direction step spans the most rows, or None."""
    # 路径 2：不同页面的右侧面板宽度不同。面板多为半透明暗底，夜景下与场景只差几级灰度；
    # 道具格、浮窗的竖线更强却不贯穿全高。因此比较跳变覆盖的行数，而不是梯度大小。
    gray = image.mean(axis=2)
    total = np.cumsum(gray[:, _EDGE_SPAN:] - gray[:, :-_EDGE_SPAN], axis=0)
    step = (total[_EDGE_ROWS:] - total[:-_EDGE_ROWS]) / _EDGE_ROWS
    cover = np.maximum((step > _EDGE_STEP).mean(axis=0), (step < -_EDGE_STEP).mean(axis=0))
    width = image.shape[1]
    low = max(0, int(x_range[0] * width) - _EDGE_SPAN)
    high = int(x_range[1] * width) - _EDGE_SPAN
    column = low + int(cover[low:high].argmax())
    return column + _EDGE_SPAN if cover[column] >= _EDGE_COVER else None


def _titles(engine, image, regions):
    """OCR each title crop; x is the crop's normalized left edge."""
    height, width = image.shape[:2]
    titles = []
    for region in regions:
        x, y, w, h = region['rect']
        detect = region.get('detect')
        if detect is not None:
            left = _panel_left(image, detect['x_range'])
            # 路径 2：画面上没有贯穿的面板边界时退回目录给出的原位置。
            if left is not None:
                x = left / width
        left, top = round(x * width), round(y * height)
        result, _ = engine(image[top:top + round(h * height), left:left + round(w * width)])
        text = ' '.join(item[2] for item in _items(result))
        if text:
            titles.append(dict(region=region['id'], text=text, x=round(x, 4)))
    return titles


def _retab(folder, cached, params, rules):
    """Recompute frame tabs from stored boxes on freshly decoded frames; None if frames drift."""
    frames = [dict(frame) for frame in cached['frames']]
    for frame in frames:
        frame.pop('tabs', None)
    # 路径 2：用户从目录删掉规则时只需去掉旧结果，不必解码。
    count = 0 if rules else len(frames)
    sampled = _sample_frames(folder / '录像.mp4', params['interval'], params['start'],
                             params['end']) if rules else ()
    for at, image in sampled:
        # 路径 4：旧版本的解码器取到的帧时刻可能不同，字框就对不上，改为整段重跑。
        if count >= len(frames) or frames[count]['t'] != at:
            return None
        frame = frames[count]
        if 'items' in frame:
            tabs = _active_tabs(image, frame['items'], rules)
            if tabs:
                frame['tabs'] = tabs
        count += 1
    if count != len(frames):
        return None
    track = dict(cached, frames=frames)
    track.pop('active_tabs', None)
    if rules:
        track['active_tabs'] = rules
    return track


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
    rules = catalog.get('active_tabs') if catalog is not None else None
    if rules:
        params['active_tabs'] = rules
    shown = {key: value for key, value in params.items()
             if key not in ('version', 'title_regions', 'active_tabs')}
    source = _source_video(folder)
    # 路径 2/1：相同视频及采样参数复用；转写、记录者变化不参与有效性。
    # 路径 2：用户按设计规范改了标题区坐标，旧标题文字不再对应，需要重跑。
    if path.is_file():
        cached = json.loads(path.read_text(encoding='utf-8'))
        sampled = cached['source_video'] == source and all(
            cached.get(key, 0 if key == 'start' else None) == value
            for key, value in params.items() if key != 'active_tabs')
        if sampled and cached.get('active_tabs') == rules:
            return dict(path=str(path.resolve()), frames=len(cached['frames']), reused=True,
                        **shown)
        # 路径 2：用户改了目录里的激活页签规则 → 字框已在轨道里，只重新解码取色，不重跑 OCR。
        # 路径 4：旧轨道没有字框，只能整段重跑。
        if sampled and all(len(item) == 4 for frame in cached['frames']
                           for item in frame.get('items', ())):
            track = _retab(folder, cached, params, rules)
            if track is not None:
                protocol._write(path.parent, path.name, track)
                return dict(path=str(path.resolve()), frames=len(track['frames']), reused=True,
                            retabbed=True, **shown)
    engine = _ocr_engine()
    title_engine = _ocr_engine(title=True) if regions else None
    frames, next_full = [], start
    for at, image in _sample_frames(folder / '录像.mp4', params['interval'], start, end):
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
        if rules:
            tabs = _active_tabs(image, frame['items'], rules)
            if tabs:
                frame['tabs'] = tabs
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
        # 没报出激活页签（只有标题的帧、或规则保持沉默）当作未知，不当作“换了页签”。
        tabs = [tab['active'] for tab in frame.get('tabs', ())] or None
        if compact:
            # 路径 2：两层轨道中只识别了标题区、且标题区无字的帧没有可读文字，不参与合并。
            if items is None and not titles:
                continue
            title = titles or _title(items)
            # 路径 2：同一标题下切换页签（商店 精选→月卡）是换了界面，不能并进一段。
            if frames and title == previous_title and (
                    tabs is None or previous_tabs is None or tabs == previous_tabs):
                frames[-1]['end'] = at
                # 路径 2：组首只有标题时，用组内第一张整屏帧补全文字，避免画面上的反证被略去。
                if items is not None and not group_full:
                    frames[-1]['text'], group_full = text[:120], True
                if tabs and previous_tabs is None:
                    frames[-1]['tabs'] = tabs
                previous_tabs = previous_tabs if tabs is None else tabs
                continue
            frames.append(dict(t=at, end=at, text=text[:120]))
            if tabs:
                frames[-1]['tabs'] = tabs
            previous_title, previous_tabs, group_full = title, tabs, items is not None
        else:
            row = dict(t=at, text=text)
            if 'titles' in frame:
                row['titles'] = frame['titles']
            if items is not None:
                # 路径 2：字框角点只供重算页签，不塞进 agent 读取的文字。
                row['items'] = [item[:3] for item in items]
            if 'tabs' in frame:
                row['tabs'] = frame['tabs']
            frames.append(row)
    layers = {key: track[key] for key in ('title_interval', 'full_interval') if key in track}
    return dict(version=track['version'], interval=track['interval'], **layers,
                source_video=track['source_video'],
                frames=frames, screens=track['screens'])
