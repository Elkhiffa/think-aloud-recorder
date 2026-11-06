"""A short recording clip with the operation record under it, as a GIF for a team table's screenshot column (agent_cli clip).

Some problems only show as "pressed this, then that happened"; a single screenshot cannot carry them, and QA and planners
have no session to replay. The band follows the review timeline: fixed cells for direction, pointing and d-pad, then keys in
order; what is held is lit, then fades over two seconds. The GIF has no sound: the recording's only playable track mixes the game with the recorder's voice, and quotes
stay out of the table. Text is drawn with Windows GDI because the packaged runtime has no imaging library and its ffmpeg
has no drawtext filter. Reads the session only.
"""
import ctypes
from ctypes import wintypes
import math
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

import av
import numpy as np

import agent_protocol as protocol

MIN_SECONDS, MAX_SECONDS = protocol.CLIP_SECONDS
CLIP_FOLDER = '证据动图'
CLIP_NAME = re.compile(r'^\d+\.\d{2}-\d+\.\d{2}\.gif$')
FPS = 10
RETENTION = 2
# The review timeline's columns. A stick or pointer reports dozens of samples a second, so a chip per flick drowns the few
# presses that carry the meaning: direction, pointing and d-pad each hold one cell showing the current direction.
HEADINGS = (('direction', '方向'), ('pointing', '指向'), ('dpad', '十字键'))
KEY_NAMES = {'ControlLeft': 'Ctrl', 'ControlRight': 'Ctrl', 'ShiftLeft': 'Shift', 'ShiftRight': 'Shift', 'AltLeft': 'Alt', 'AltRight': 'Alt',
             'WinLeft': 'Win', 'WinRight': 'Win', 'Space': '空格', 'Backspace': '退格', 'Escape': 'Esc'}
AXES = {'W': (0, -1), 'A': (-1, 0), 'S': (0, 1), 'D': (1, 0), 'Up': (0, -1), 'Down': (0, 1), 'Left': (-1, 0), 'Right': (1, 0)}
ARROWS = {(0, -1): '↑', (1, -1): '↗', (1, 0): '→', (1, 1): '↘', (0, 1): '↓', (-1, 1): '↙', (-1, 0): '←', (-1, -1): '↖'}
NOISE, STRONG = 0.18, 0.3


def input_channel(row):
    """Same split as inputChannel in ui/review.js."""
    code = str(row.get('code') or '')
    if code.lower().startswith('dpad'):
        return 'dpad'
    if code == 'LeftStick' or (row.get('device') == 'keyboard' and code.replace('Key', '') in ('W', 'A', 'S', 'D')):
        return 'direction'
    return 'pointing' if code in ('MouseMove', 'RightStick') else 'keys'


def _axis(row):
    code = str(row.get('code') or '').replace('Key', '')
    return AXES.get(re.sub('^[Dd][Pp]ad', '', code))


def _value(row):
    return row['value'] if row.get('value') is not None else 1


def _flicks(rows, gap=0.12):
    flicks = []
    for row in sorted(rows, key=lambda item: item['start']):
        if flicks and row['start'] - flicks[-1]['end'] <= gap:
            flicks[-1]['samples'].append(row)
            flicks[-1]['end'] = max(flicks[-1]['end'], row['end'])
        else:
            flicks.append(dict(start=row['start'], end=row['end'], samples=[row]))
    return [flick for flick in flicks if max(_value(row) for row in flick['samples']) >= NOISE]


def _direction_at(flick, t):
    """The latest strong sample: a stick passes through the opposite direction on its way back to centre, weakly."""
    samples = [row for row in flick['samples'] if row['start'] <= t] or flick['samples'][:1]
    active = [row for row in samples if t < row['end'] and _axis(row)]
    if active:  # Keys and d-pad buttons combine into diagonals while held together.
        x, y = (sum(_axis(row)[i] for row in active) for i in (0, 1))
        if (x, y) in ARROWS:
            return ARROWS[(x, y)]
    strong = [row for row in samples if _value(row) >= STRONG and (row.get('direction') or _axis(row))]
    row = strong[-1] if strong else samples[-1]
    return row.get('direction') or ARROWS.get(_axis(row)) or ''


def fixed_cell(flicks, t):
    """(direction, strength) for one fixed cell at t, or None while idle."""
    started = [flick for flick in flicks if flick['start'] <= t]
    if not started:
        return None
    strength = chip_strength(started[-1], t)
    return (_direction_at(started[-1], t), strength) if strength > 0 else None


def key_chips(rows, gap=0.12):
    """Presses in order; an analog trigger's samples count as one press."""
    chips = []
    for flick_rows in _group_by_control(rows):
        for flick in _flicks(flick_rows, gap):
            first = flick['samples'][0]
            code = first.get('code')
            chips.append(dict(start=flick['start'], end=flick['end'], text=KEY_NAMES.get(code, first.get('label') or code)))
    return sorted(chips, key=lambda chip: chip['start'])


def _group_by_control(rows):
    groups = {}
    for row in rows:
        groups.setdefault((row.get('device'), row.get('code')), []).append(row)
    return groups.values()


def operation_tracks(intervals, start, end):
    rows = [row for row in intervals if row['end'] >= start and row['start'] <= end]
    return dict({name: _flicks([row for row in rows if input_channel(row) == name], 0.65 if name == 'dpad' else 0.12) for name, _ in HEADINGS},
                keys=key_chips([row for row in rows if input_channel(row) == 'keys']))


def chip_strength(chip, t):
    """Same curve as the review page's inputHighlight: full while held, then 0.7 fading to nothing over two seconds."""
    if t < chip['start']:
        return 0
    return 1 if t <= chip['end'] else max(0, 1 - (t - chip['end']) / RETENTION) * .7


class _Text:
    """Cached glyph masks from GDI, as 0–1 float arrays."""

    def __init__(self, pixels):
        self.gdi, self.cache = ctypes.WinDLL('gdi32'), {}
        gdi = self.gdi
        gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi.CreateCompatibleDC.restype = wintypes.HDC
        gdi.CreateFontW.restype = wintypes.HFONT
        gdi.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wintypes.DWORD] * 8 + [wintypes.LPCWSTR]
        gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        gdi.SelectObject.restype = wintypes.HGDIOBJ
        gdi.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        gdi.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi.GetTextExtentPoint32W.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.SIZE)]
        gdi.TextOutW.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.LPCWSTR, ctypes.c_int]
        gdi.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
        gdi.CreateDIBSection.restype = wintypes.HBITMAP
        gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        gdi.DeleteDC.argtypes = [wintypes.HDC]
        self.dc = gdi.CreateCompatibleDC(None)
        self.font = gdi.CreateFontW(-pixels, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 4, 0, 'Microsoft YaHei')
        gdi.SelectObject(self.dc, self.font)
        gdi.SetTextColor(self.dc, 0xFFFFFF)
        gdi.SetBkMode(self.dc, 1)

    def mask(self, text):
        if text in self.cache:
            return self.cache[text]
        size = wintypes.SIZE()
        self.gdi.GetTextExtentPoint32W(self.dc, text, len(text), ctypes.byref(size))
        width, height = max(1, size.cx), max(1, size.cy)
        header = (ctypes.c_uint32 * 10)(40, width, ctypes.c_uint32(-height).value, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bitmap = self.gdi.CreateDIBSection(self.dc, header, 0, ctypes.byref(bits), None, 0)
        previous = self.gdi.SelectObject(self.dc, bitmap)
        self.gdi.TextOutW(self.dc, 0, 0, text, len(text))
        data = np.ctypeslib.as_array(ctypes.cast(bits, ctypes.POINTER(ctypes.c_uint8)), (height, width, 4))[:, :, 1].astype(np.float32) / 255
        self.gdi.SelectObject(self.dc, previous)
        self.gdi.DeleteObject(bitmap)
        self.cache[text] = data
        return data

    def close(self):
        self.gdi.DeleteObject(self.font)
        self.gdi.DeleteDC(self.dc)


def _paint(canvas, mask, x, y, colour):
    height, width = canvas.shape[:2]
    h, w = min(mask.shape[0], height - y), min(mask.shape[1], width - x)
    if h <= 0 or w <= 0:
        return
    alpha = mask[:h, :w, None]
    canvas[y:y + h, x:x + w] = canvas[y:y + h, x:x + w] * (1 - alpha) + np.array(colour, dtype=np.float32) * alpha


def _band(width, height, tracks, t, clip_start, text, small):
    canvas = np.full((height, width, 3), (24, 22, 20), dtype=np.float32)
    pad, gap, x = height // 5, height // 8, height // 3
    muted = (150, 142, 130)
    top, bottom = pad, height - pad
    cell = bottom - top
    for name, heading in HEADINGS:
        if name == 'dpad' and not tracks['dpad']:  # The timeline also drops this column when the clip has no d-pad.
            continue
        mask = small.mask(heading)
        _paint(canvas, mask, x, (height - mask.shape[0]) // 2, muted)
        x += mask.shape[1] + gap
        state = fixed_cell(tracks[name], t)
        canvas[top:bottom, x:x + cell] = (44, 41, 38)
        if state:
            direction, strength = state
            held = strength == 1
            level = 40 + 215 * strength
            canvas[top:bottom, x:x + cell] = (236, 190, 90) if held else (level / 3,) * 3
            if direction:
                arrow = text.mask(direction)
                _paint(canvas, arrow, x + max(0, (cell - arrow.shape[1]) // 2), top + max(0, (cell - arrow.shape[0]) // 2), (24, 22, 20) if held else (level,) * 3)
        x += cell + pad
    title = small.mask('按键')
    _paint(canvas, title, x, (height - title.shape[0]) // 2, muted)
    x += title.shape[1] + gap
    clock = small.mask(f'{t - clip_start:4.1f}s')
    limit = width - clock.shape[1] - pad * 2
    _paint(canvas, clock, width - clock.shape[1] - pad, (height - clock.shape[0]) // 2, muted)
    visible = [(chip, chip_strength(chip, t)) for chip in tracks['keys']]
    visible = [row for row in visible if row[1] > 0]
    # Newest at the right end; the oldest drop off rather than running under the clock.
    fitted, used = [], 0
    for chip, strength in reversed(visible):
        mask = text.mask(chip['text'])
        cost = mask.shape[1] + pad * 2 + gap
        if used + cost > limit - x:
            break
        fitted.append((chip, strength, mask))
        used += cost
    for chip, strength, mask in reversed(fitted):
        w = mask.shape[1] + pad * 2
        held = strength == 1
        level = 40 + 215 * strength
        canvas[top:bottom, x:x + w] = (236, 190, 90) if held else (level / 3,) * 3
        _paint(canvas, mask, x + pad, (height - mask.shape[0]) // 2, (24, 22, 20) if held else (level,) * 3)
        x += w + gap
    return canvas.astype(np.uint8)


def _half(canvas):
    """Average 2x2 blocks: dropping every other pixel turns the band's text and the game's small print into noise."""
    a = canvas.astype(np.uint16)
    return ((a[::2, ::2] + a[1::2, ::2] + a[::2, 1::2] + a[1::2, 1::2]) // 4).astype(np.uint8)


def _sheet_frames(frames):
    """Contact sheet tiles: at most 16, evenly spaced, so an agent that cannot watch a GIF can see what it shows."""
    step = max(1, math.ceil(len(frames) / 16))
    tiles = frames[::step][:16]
    rows = [np.concatenate(tiles[i:i + 2] + ([np.zeros_like(tiles[0])] if len(tiles[i:i + 2]) == 1 else []), axis=1) for i in range(0, len(tiles), 2)]
    return np.concatenate(rows, axis=0), len(tiles)


def clip_path(folder, start, end):
    """Named by its span, so resubmitting the same span reuses the file."""
    return Path(folder) / CLIP_FOLDER / f'{start:.2f}-{end:.2f}.gif'


def build_clips(folder, result=None):
    """Make the clips a submitted result marks, reuse those already there, and clear only this folder's own clips that a
    re-organized result no longer cites. A clip that fails is reported: the judgment still stands on its other evidence."""
    if result is None:
        result = protocol.validate_result(folder, protocol._load(folder, protocol.RESULT, protocol.MAX_RESULT))
    began = time.monotonic()
    spans = protocol.clip_spans(result)
    wanted = {clip_path(folder, start, end).name for start, end in spans}
    made, reused, failed, removed = 0, 0, [], 0
    for start, end in spans:
        target = clip_path(folder, start, end)
        if target.is_file():
            reused += 1
            continue
        try:
            _render(folder, start, end, target)
            made += 1
        except (OSError, ValueError, av.error.FFmpegError, subprocess.SubprocessError) as error:
            failed.append(dict(start=start, end=end, error=str(error)))
    stored = Path(folder) / CLIP_FOLDER
    if stored.is_dir():
        for file in stored.iterdir():
            if CLIP_NAME.match(file.name) and file.name not in wanted:
                file.unlink()
                removed += 1
    return dict(folder=CLIP_FOLDER, made=made, reused=reused, removed=removed, failed=failed, seconds=round(time.monotonic() - began, 1))


def make_clip(folder, start, end, output, width=960, sheet=None):
    """A clip in the agent's own work folder, to check what a span shows before citing it."""
    if not isinstance(width, int) or not 480 <= width <= 1280:
        raise ValueError('动图宽度需在 480–1280 之间。')
    if not MIN_SECONDS <= end - start <= MAX_SECONDS:
        raise ValueError(f'片段长度需在 {MIN_SECONDS}–{MAX_SECONDS} 秒之间：只截这次操作和它的结果。')
    session = Path(folder).resolve()
    targets = [Path(output).resolve()] + ([Path(sheet).resolve()] if sheet else [])
    if targets[0].suffix.lower() != '.gif' or (sheet and targets[1].suffix.lower() != '.jpg') or any(path.is_relative_to(session) for path in targets):
        raise ValueError('动图需保存为场次以外的 .gif，拼图为 .jpg。')
    if any(path.exists() for path in targets):
        raise ValueError('输出文件已存在，请使用新的文件名。')
    return _render(folder, start, end, targets[0], width, targets[1] if sheet else None)


def _render(folder, start, end, output, width=960, sheet=None):
    meta, material, revision, _ = protocol._ready(folder)
    protocol._span(dict(start=start, end=end), material['duration'])
    width = width // 2 * 2
    inputs = protocol._normalized_inputs(folder, meta, material['duration'])
    tracks = operation_tracks(inputs.get('intervals', []), start, end)
    from recorder import FFMPEG, HIDDEN
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.stem + '.' + uuid.uuid4().hex + '.gif')
    text, small, kept, process = None, None, [], None
    try:
        with av.open(str(protocol._path(folder, '录像.mp4'))) as container:
            stream = container.streams.video[0]
            origin = (container.start_time or 0) / av.time_base
            height = int(stream.height * width / stream.width) // 2 * 2
            band = max(44, width // 18) // 2 * 2
            text, small = _Text(band * 2 // 5), _Text(band * 3 // 10)
            size = f'{width}x{height + band}'
            process = subprocess.Popen([str(FFMPEG), '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', size, '-r', str(FPS), '-i', '-',
                                        '-vf', 'split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle',
                                        '-loop', '0', '-y', str(tmp)], stdin=subprocess.PIPE, creationflags=HIDDEN)
            container.seek(int((start + origin) / stream.time_base), stream=stream, backward=True)
            due, count = start, 0
            for frame in container.decode(stream):
                t = float(frame.pts * stream.time_base) - origin
                if t < due:
                    continue
                if t > end:
                    break
                picture = frame.reformat(width=width, height=height, format='rgb24').to_ndarray()
                canvas = np.concatenate([picture, _band(width, band, tracks, t, start, text, small)], axis=0)
                process.stdin.write(canvas.tobytes())
                if sheet:
                    kept.append(_half(canvas))
                count += 1
                due += 1 / FPS
        process.stdin.close()
        if process.wait(timeout=120) or not tmp.is_file() or not count:
            raise ValueError('无法生成动图，请检查录像和这一段时间。')
        if protocol._ready(folder)[2] != revision:
            raise ValueError('生成期间素材已更新，请重试。')
        result = dict(session_id=meta['id'], revision=revision, start=start, end=end, frames=count, keys=len(tracks['keys']))
        if sheet:
            picture, tiles = _sheet_frames(kept)
            run = subprocess.run([str(FFMPEG), '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{picture.shape[1]}x{picture.shape[0]}', '-i', '-',
                                  '-frames:v', '1', '-q:v', '3', '-update', '1', '-y', str(sheet)], input=picture.tobytes(), capture_output=True, timeout=60, creationflags=HIDDEN)
            if run.returncode or not Path(sheet).is_file():
                raise ValueError('无法生成拼图。')
            result.update(sheet=str(sheet), sheet_tiles=tiles)
        # Windows rename fails if the destination appeared during encoding.
        os.rename(tmp, output)
        return dict(result, path=str(output), bytes=output.stat().st_size)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
        for item in (text, small):
            if item is not None:
                item.close()
        tmp.unlink(missing_ok=True)
