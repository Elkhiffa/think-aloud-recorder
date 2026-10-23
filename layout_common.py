"""Screen-layout recognition shared by every game: text boxes, tab rows and columns, tab-name matching,
levels, and the recognizer registry. What a lit tab, a title or a focus frame looks like is game-specific and
lives in one module per game (layout_<name>.py), chosen by catalog `layout.recognizer`."""
import importlib
import re

import numpy as np

# Recognizer modules shipped with the recorder. A catalog can only name one of these: library files never
# bring code with them.
RECOGNIZERS = {'yanyun': 'layout_yanyun'}

# Panel edge: brightness step across 3 px, averaged over 9 rows, must exceed 2.5
# grey levels in the same direction on at least 60% of rows.
_EDGE_SPAN, _EDGE_ROWS, _EDGE_STEP, _EDGE_COVER = 3, 9, 2.5, .6
# Tab rows (measured 2026-10 on 21 16:9 + 5 1920x804 燕云 sessions): short texts whose centres differ < 0.45 text
# heights, heights within 1.35x, gaps up to 7 heights, pitch within 1.5x; minimum text height 8/1080.
_TAB_CHARS, _ROW_DY, _ROW_HEIGHTS, _ROW_GAP, _ROW_PITCH, _TAB_MIN_H = 6, .45, 1.35, 7, 1.5, 8 / 1080
_TAB_NOISE = {'返回', '说明'}


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
                   y0=min(ys), y1=max(ys), cy=(min(ys) + max(ys)) / 2, h=max(ys) - min(ys))
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


def _tab_columns(items, min_height):
    """Short texts stacked in one column (left-aligned or centred under icons), >= 2 of them."""
    boxes = [b for b in _text_boxes(items) if _tab_text(b['text']) and b['h'] > min_height]
    columns, used = [], set()
    for anchor in sorted(boxes, key=lambda b: b['cy']):
        if anchor['i'] in used:
            continue
        h = anchor['h']
        same = sorted((b for b in boxes if b['i'] not in used
                       and (abs(b['cx'] - anchor['cx']) < .9 * max(b['h'], h)
                            or abs(b['x0'] - anchor['x0']) < .5 * max(b['h'], h))
                       and max(b['h'], h) / min(b['h'], h) < _ROW_HEIGHTS), key=lambda b: b['cy'])
        start = same.index(anchor)
        end = start
        # 路径 2：图文页签的字之间隔着一个图标（约 2 个字高），列表项之间隔一行底条。
        while end + 1 < len(same) and -.3 * h < same[end + 1]['y0'] - same[end]['y1'] <= _ROW_GAP * h:
            end += 1
        members = same[start:end + 1]
        if len(members) >= 2:
            used |= {b['i'] for b in members}
            columns.append(members)
    return columns


def _text_boxes(items):
    boxes = []
    for index, item in enumerate(items):
        if len(item) < 4:
            continue
        xs, ys = [point[0] for point in item[3]], [point[1] for point in item[3]]
        boxes.append(dict(i=index, text=item[2], t=re.sub(r'\s', '', item[2]), x0=min(xs), x1=max(xs),
                          y0=min(ys), y1=max(ys), cx=(min(xs) + max(xs)) / 2, cy=(min(ys) + max(ys)) / 2,
                          h=max(ys) - min(ys)))
    return boxes


def _same_tab(text, tab):
    """OCR spelling of a confirmed tab: equal, one wrong character (装备宝理), or one extra leading
    character (an icon read as a glyph)."""
    if text == tab:
        return True
    if len(text) == len(tab) >= 3 and sum(a != b for a, b in zip(text, tab)) == 1:
        return True
    return len(text) == len(tab) + 1 and text[1:] == tab


def _crop(image, x0, y0, x1, y1):
    """Slice clamped to the picture; None when nothing is left. A focus frame on the leftmost icon or the
    top row reaches past the edge, and a negative index would wrap around (E3: 20260929-162827)."""
    height, width = image.shape[:2]
    x0, x1 = max(0, int(x0)), min(width, int(x1))
    y0, y1 = max(0, int(y0)), min(height, int(y1))
    return image[y0:y1, x0:x1] if x1 > x0 and y1 > y0 else None


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


def recognizer(layout):
    """The recognizer module a catalog layout names."""
    return importlib.import_module(RECOGNIZERS[layout['recognizer']])


def validate(layout):
    # 路径 2：用户手填目录后运行 catalog-validate；未知的识别方法要报错，而不是静默不识别。
    if not isinstance(layout, dict) or layout.get('recognizer') not in RECOGNIZERS:
        raise ValueError('layout.recognizer 必须是记录器自带的识别方法之一：' + '、'.join(RECOGNIZERS))
    recognizer(layout).validate(layout)


def derive(image, full, items, layout):
    """Tabs, headings and focus of one full-OCR frame, with tab levels from the layout."""
    out = recognizer(layout).derive(image, full, items, layout)
    tabs = out.pop('tabs', [])
    if tabs:
        # 层级按版式（用户 2026-10-23）：顶部页签和纯图标页签是一级；其余按从左到右、从上到下依次是下一级
        # （二级纵列在左、三级在它右侧顶部；二级横排在上、三级在它下方）。不看界面编号里第几段。
        first = [tab for tab in tabs if tab['kind'] in ('top', 'icon')]
        rest = sorted((tab for tab in tabs if tab['kind'] not in ('top', 'icon')),
                      key=lambda tab: (tab['_x'], tab['_y']))
        for tab in first:
            tab['level'] = 1
        for number, tab in enumerate(rest, 2 if first else 1):
            tab['level'] = number
        out = dict(tabs=[{k: v for k, v in tab.items() if not k.startswith('_')} for tab in first + rest], **out)
    return out
