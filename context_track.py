"""Local OCR context derived only from the source video, never session revision."""
import json
import math
from pathlib import Path
import re

import agent_protocol as protocol
import game_catalog

TRACK = 'context-track.json'
_UID = re.compile(r'\bID\s*[:：]\s*(\d+)', re.IGNORECASE)
_CLIENT_TIME = re.compile(r'\b\d{4}\s+\d{2}:\d{2}\b')
# 路径 2：OCR 可能把 UID、MMDD、H:MM 连成一串；最短 UID 配合合法月日时分拆开。
_JOINED = re.compile(r'\bID\s*[:：]\s*(\d+?)\s*((?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01]))'
                     r'\s*((?:[01]?\d|2[0-3]):[0-5]\d)', re.IGNORECASE)


def _source_video(folder):
    stat = (Path(folder) / '录像.mp4').stat()
    return dict(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)


def _ocr_engine():
    # 路径 2：context-build 在未安装本地 OCR 的开发环境中运行。
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as error:
        raise ValueError('OCR 依赖未安装') from error
    return RapidOCR()


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


def _watermark(items, at, height, watermark):
    # 路径 2：角落 UID/客户端时间另行摘取，frames 中仍保留全部原文。
    corners = [item for item in items
               if (item[0] <= 240 or item[0] >= 720)
               and (item[1] <= height * .2 or item[1] >= height * .8)]
    text = ' '.join(item[2] for item in sorted(corners, key=lambda item: (item[1], item[0])))
    joined = _JOINED.search(text)
    uid = joined or _UID.search(text)
    if uid is None:
        return watermark
    if watermark is None:
        watermark = dict(uid=uid.group(1), client_time=[])
    if joined is not None:
        client_time = joined.group(2) + ' ' + joined.group(3)
    else:
        client_time = _CLIENT_TIME.search(text, uid.end())
        client_time = client_time and client_time.group(0)
    if client_time:
        samples = watermark['client_time']
        if not samples or int(samples[-1]['t'] // 60) != int(at // 60):
            samples.append(dict(t=at, text=client_time))
    return watermark


def _track_path(folder, output=None):
    return (Path(output) if output is not None else Path(folder)) / TRACK


def build(folder, *, interval=5, start=0, end=None, output=None, rematch=False):
    """Build or reuse a track; output redirects derived data outside the session."""
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
    if not math.isfinite(interval) or not 2 <= interval <= 10:
        raise ValueError('抽帧间隔必须在 2–10 秒之间。')
    if not math.isfinite(start) or start < 0 or (end is not None and
            (not math.isfinite(end) or end <= start)):
        raise ValueError('抽帧范围需满足 0 ≤ start < end。')
    source = _source_video(folder)
    # 路径 2/1：相同视频及采样参数复用；转写、记录者变化不参与有效性。
    if path.is_file():
        cached = json.loads(path.read_text(encoding='utf-8'))
        if (cached['source_video'] == source and cached['interval'] == interval
                and cached.get('start', 0) == start and cached.get('end') == end):
            return dict(path=str(path.resolve()), frames=len(cached['frames']), reused=True,
                        interval=interval, start=start, end=end)
    engine = _ocr_engine()
    frames, watermark = [], None
    for at, image in _sample_frames(folder / '录像.mp4', interval, start, end):
        result, _ = engine(image)
        items = _items(result)
        frames.append(dict(t=at, items=items))
        watermark = _watermark(items, at, image.shape[0], watermark)
    track = dict(version=1, source_video=source, interval=interval, start=start, end=end,
                 watermark=watermark, frames=frames,
                 screens=game_catalog.match_screens(game_catalog.session_catalog(folder), frames))
    path.parent.mkdir(parents=True, exist_ok=True)
    protocol._write(path.parent, path.name, track)
    return dict(path=str(path.resolve()), frames=len(frames), reused=False,
                interval=interval, start=start, end=end)


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
    """Return time-filtered OCR; compact merges adjacent title prefixes."""
    track = load_track(folder, output=output)
    frames, previous_title = [], None
    for frame in track['frames']:
        at, items = frame['t'], frame['items']
        if (start is not None and at < start) or (end is not None and at > end):
            continue
        text = '\n'.join(item[2] for item in items)
        if compact:
            title = _title(items)
            if frames and title == previous_title:
                frames[-1]['end'] = at
                continue
            frames.append(dict(t=at, end=at, text=text[:120]))
            previous_title = title
        else:
            frames.append(dict(t=at, text=text, items=items))
    return dict(version=track['version'], interval=track['interval'],
                source_video=track['source_video'], watermark=track['watermark'],
                frames=frames, screens=track['screens'])
