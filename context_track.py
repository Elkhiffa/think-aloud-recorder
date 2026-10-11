"""Local OCR context derived only from the source video, never session revision."""
import json
import math
from pathlib import Path

import numpy as np

import agent_protocol as protocol
import game_catalog

TRACK = 'context-track.json'
# Panel edge: brightness step across 3 px, averaged over 9 rows, must exceed 2.5
# grey levels in the same direction on at least 60% of rows.
_EDGE_SPAN, _EDGE_ROWS, _EDGE_STEP, _EDGE_COVER = 3, 9, 2.5, .6


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
        items.append([round(float(x), 2), round(float(y), 2), text])
    return items


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
    shown = {key: value for key, value in params.items() if key not in ('version', 'title_regions')}
    source = _source_video(folder)
    # 路径 2/1：相同视频及采样参数复用；转写、记录者变化不参与有效性。
    # 路径 2：用户按设计规范改了标题区坐标，旧标题文字不再对应，需要重跑。
    if path.is_file():
        cached = json.loads(path.read_text(encoding='utf-8'))
        if cached['source_video'] == source and all(
                cached.get(key, 0 if key == 'start' else None) == value
                for key, value in params.items()):
            return dict(path=str(path.resolve()), frames=len(cached['frames']), reused=True,
                        **shown)
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
    frames, previous_title, group_full = [], None, False
    for frame in track['frames']:
        at, items = frame['t'], frame.get('items')
        if (start is not None and at < start) or (end is not None and at > end):
            continue
        titles = ' '.join(title['text'] for title in frame.get('titles', ()))
        text = '\n'.join(item[2] for item in items) if items is not None else titles
        if compact:
            # 路径 2：两层轨道中只识别了标题区、且标题区无字的帧没有可读文字，不参与合并。
            if items is None and not titles:
                continue
            title = titles or _title(items)
            if frames and title == previous_title:
                frames[-1]['end'] = at
                # 路径 2：组首只有标题时，用组内第一张整屏帧补全文字，避免画面上的反证被略去。
                if items is not None and not group_full:
                    frames[-1]['text'], group_full = text[:120], True
                continue
            frames.append(dict(t=at, end=at, text=text[:120]))
            previous_title, group_full = title, items is not None
        else:
            row = dict(t=at, text=text)
            if 'titles' in frame:
                row['titles'] = frame['titles']
            if items is not None:
                row['items'] = items
            frames.append(row)
    layers = {key: track[key] for key in ('title_interval', 'full_interval') if key in track}
    return dict(version=track['version'], interval=track['interval'], **layers,
                source_video=track['source_video'],
                frames=frames, screens=track['screens'])
