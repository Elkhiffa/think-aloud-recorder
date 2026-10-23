"""燕云十六声 screen-layout recognizer. Rules from the game's design spec and E1 (2026-10):
active tabs are gold text with a glow; second-level tabs show the selection as the strongest icon backdrop or
a dark list bar; the page title sits at a fixed left margin, side-window titles at the top of a full-height
panel; the gamepad focus is a gold outline with a small downward triangle centred on its top edge.
Numbers (colours, bands, names, confirmed tab groups) come from the catalog `layout`; this module holds how
those things look."""
import re

import numpy as np

from layout_common import (_TAB_MIN_H, _crop, _game_rows, _ink, _panel_left, _same_tab, _tab_columns,
                           _tab_rows, _text_boxes)
from game_catalog import _fraction, _text, _texts

_BUMPERS = {'LB', 'RB', 'Q', 'E', 'LT', 'RT'}


def _gold(bgr, rules):
    import cv2
    colour = np.asarray(bgr, np.float32).reshape(1, 1, 3) / 255
    b = float(cv2.cvtColor(colour, cv2.COLOR_BGR2Lab)[0, 0, 2])
    high, low = float(colour.max()), float(colour.min())
    return b >= rules['gold']['min_b'] and (high - low) / max(high, 1e-6) >= rules['gold']['min_s']


def _active_tabs(image, lab, rows, rules, top, span):
    """Top and horizontal-text tab rows with exactly one gold tab; anything else stays silent."""
    tabs = []
    for members in rows:
        y = (sum(box['cy'] for box in members) / len(members) - top) / span
        texts = [box['text'] for box in members]
        if y < rules['top_max_y']:
            kind = 'top'
        elif any(low <= y <= high for low, high in rules['text_bands']):
            kind = 'text'
        else:
            # 路径 2：带外的金色字多是按钮、角标和卡片标题（2026-10 随机 80 帧里带外 16 排全是）。
            continue
        inks = [_ink(image, lab, box) for box in members]
        gold = [index for index, ink in enumerate(inks) if ink is not None and _gold(ink, rules)]
        # 路径 2：两个金色（商店“和鸣”推广字）或没有金色时不报，宁缺勿错。
        if len(gold) == 1:
            tabs.append(dict(kind=kind, active=texts[gold[0]], row=texts, _x=members[0]['x0'],
                             _y=members[0]['y0'], _ids={box['i'] for box in members}))
    return tabs


def _headings(image, lab, items, rules, gold, top, span, in_rows):
    """Page title (left, fixed margin) and side-window titles (top of a full-height right panel)."""
    width = image.shape[1]
    within = lambda value, band: band[0] <= value <= band[1]
    boxes = _text_boxes(items)
    main, side = None, []
    for b in boxes:
        t = b['t']
        if (b['i'] in in_rows or not 2 <= len(t) <= 10 or re.search(r'\d', t)
                or not re.search(r'[一-鿿]', t)):
            continue
        y, h = (b['cy'] - top) / span, b['h'] / span
        left = b['cx'] < width / 2
        margin = (b['x0'] if left else width - b['x1']) / span
        if 'main' in rules and left and within(margin, rules['main']['margin']) and within(
                y, rules['main']['y']) and within(h, rules['main']['height']):
            kind = 'main'
        elif 'side' in rules and within(y, rules['side']['y']) and h >= rules['side']['min_height']:
            kind = 'side'
            # 路径 2：侧窗标题左侧有一条贯穿画面高度的面板边缘；浮窗里的物品名、作者署名没有。
            low, high = (b['x0'] - .1 * span) / width, (b['x0'] + .01 * span) / width
            if high <= max(low, 0) or _panel_left(image, [max(0.0, low), min(1.0, high)]) is None:
                continue
        else:
            continue
        # 路径 2：金字是亮着的页签（装备、月卡）；正下方紧贴一行字的是角色卡（名字 + 角色编号）；
        # 左边紧挨 LB / Q 的是识别粘成一个字的页签排（LB 单人多人）。
        ink = _ink(image, lab, b) if gold else None
        if ink is not None and _gold(ink, gold):
            continue
        if any(o is not b and 0 <= o['y0'] - b['y1'] < .6 * b['h']
               and min(o['x1'], b['x1']) - max(o['x0'], b['x0']) > 0 for o in boxes):
            continue
        if any(o['t'].upper() in _BUMPERS and abs(o['cy'] - b['cy']) < .6 * b['h']
               and 0 <= b['x0'] - o['x1'] < 3 * b['h'] for o in boxes):
            continue
        if kind == 'main':
            main = b if main is None or b['h'] > main['h'] else main
        else:
            side.append(b)
    names = rules.get('icon_tabs', ())
    # 路径 2：背包标题左侧的图标常被识别成一个字（淄培养、简培养）；已知名称允许开头多一个字。
    fix = lambda t: t[1:] if t not in names and t[1:] in names else t
    out = {}
    if main is not None:
        out['main'] = main['t']
    if side:
        out['side'] = [fix(b['t']) for b in sorted(side, key=lambda b: b['x0'])]
    return out


def _focus_mask(image, rules, min_v):
    import cv2
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    low, high = rules['hue'][0] / 2, rules['hue'][1] / 2          # OpenCV hue is 0-180
    return ((hsv[..., 0] >= low) & (hsv[..., 0] <= high) & (hsv[..., 1] >= rules['min_s'] * 255)
            & (hsv[..., 2] >= min_v * 255)).astype(np.uint8)


def _focus_rings(image, rules, min_v):
    """Hollow gold outlines on the 960-wide frame: (x, y, w, h)."""
    import cv2
    # 路径 2：960 宽下焦点框四角会断开 1–2 像素（拾音券），先补上。
    mask = cv2.morphologyEx(_focus_mask(image, rules, min_v), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    rings = []
    for i in range(1, count):
        x, y, w, h, area = stats[i]
        # 路径 2：焦点是细线框；发光的灯笼是厚实的亮块（平均线宽 = 面积 ÷ 周长）。
        if min(w, h) < 10 or max(w, h) > 20 * min(w, h) or area / (2 * (w + h)) > 3.5:
            continue
        points = cv2.findNonZero((labels[y:y + h, x:x + w] == i).astype(np.uint8))
        hull = cv2.contourArea(cv2.convexHull(points))
        # 凸包占满框而像素很少 = 空心框；比找内孔更能容忍缺口（博物志的暗金圆环底部是断开的）。
        if hull >= .5 * w * h and area <= .35 * hull:
            rings.append((int(x), int(y), int(w), int(h)))
    return rings


def _focus_triangle(full, box, scale, rules, min_v):
    """Share (0-10) of the gold near the top edge that sits in the centre: the downward triangle.
    Big frames carry it above the edge line, small icon frames draw it down into the frame."""
    x, y, w, h = [v * scale for v in box]
    unit = full.shape[0] / 1080
    crop = _crop(full, x, y - 6, x + w, y + .2 * h + 6)
    if crop is None:
        return 0.0
    band = _focus_mask(crop, rules, min_v)
    cover = band.mean(axis=1)
    edge = next((r for r, v in enumerate(cover) if v >= .5), None)
    if edge is None:
        return 0.0
    end = edge
    while end < len(cover) and cover[end] >= .5:
        end += 1
    width = band.shape[1]
    lo = int(.15 * width)
    best = 0.0
    for part, offset in ((band[:edge], 0), (band[end:end + int(12 * unit), lo:width - lo], lo)):
        pixels = np.argwhere(part)
        if len(pixels) < 3:
            continue
        xs = pixels[:, 1] + offset
        # 小三角宽约 16 像素（1080p）；比这宽的金色（灯笼的圆顶）不是。去掉两端 5% 的角落余光。
        if np.percentile(xs, 95) - np.percentile(xs, 5) > max(.3 * width, 24 * unit):
            continue
        best = max(best, float((np.abs(xs - width / 2) <= .2 * width).mean() * 10))
    return best


def _focus_narrowing(full, box, scale, rules, min_v):
    """Rows near the top centre whose gold width keeps shrinking: a downward triangle on a round frame,
    whose own arc widens going down."""
    x, y, w, h = [v * scale for v in box]
    unit = full.shape[0] / 1080
    half = max(14 * unit, .15 * w)
    cx = x + w / 2
    crop = _crop(full, cx - half, y - 6 * unit, cx + half, y + min(.3 * h, 40 * unit))
    if crop is None:
        return 0
    widths = _focus_mask(crop, rules, min_v).sum(axis=1)
    best = 0
    for start in range(len(widths)):
        if not 4 * unit <= widths[start] <= 2 * half * .95:
            continue
        end = start
        while end + 1 < len(widths) and 0 < widths[end + 1] <= widths[end]:
            end += 1
        if end - start + 1 >= 3 and widths[end] <= .4 * widths[start]:
            best = max(best, end - start + 1)
    return best


def _focus(image, full, items, rules):
    """The gamepad focus frame (gold outline + small downward triangle), or None (keyboard and mouse)."""
    scale = full.shape[1] / image.shape[1]
    bright, dim = rules['levels'][0], rules['levels'][-1]
    found, seen = [], []
    for min_v in rules['levels']:
        for box in _focus_rings(image, rules, min_v):
            # 同一个框在两档亮度下都会找到：只按先找到的那一档判。
            if any(abs(box[0] - b[0]) < 4 and abs(box[1] - b[1]) < 4 for b in seen):
                continue
            seen.append(box)
            w, h = box[2], box[3]
            # 暗金三角只在更低亮度下才显出来（博物志圆形焦点），多看一档。
            probe = (min_v, min(dim, .24))
            if min_v == bright:
                # 路径 2：亮框要有居中的小三角；短边 < 16 像素的是江湖弈棋子。
                score = max(_focus_triangle(full, box, scale, rules, v) for v in probe)
                ok = score >= 8 and min(w, h) >= 16
            else:
                # 路径 2：暗框只收接近正圆、有倒三角的（圆形焦点）；放开暗方框会收进奖励卡和场景道具。
                score = max(_focus_narrowing(full, box, scale, rules, v) for v in probe)
                ok = .85 <= w / h <= 1.15 and score >= 3
            if ok:
                found.append((box, score))
    if not found:
        return None
    (x, y, w, h), _ = max(found, key=lambda pair: pair[0][2] * pair[0][3])
    inside = [item[2] for item in items if x <= item[0] <= x + w and y <= item[1] <= y + h + .3 * h]
    focus = dict(box=[x, y, x + w, y + h])
    if inside:
        focus['text'] = ' '.join(inside)[:40]
    return focus


def _region_l(lab, x0, y0, x1, y1):
    height, width = lab.shape[:2]
    x0, x1 = max(0, int(x0)), min(width, int(x1))
    y0, y1 = max(0, int(y0)), min(height, int(y1))
    return float(np.median(lab[y0:y1, x0:x1, 0])) if x1 > x0 and y1 > y0 else None


def _selected(image, lab, members, gold, focus):
    """Index of the selected member of a confirmed tab group, or None.

    Order (2026-10 on 71 labelled left columns: 49 right, 6 wrong, 16 silent): a focus frame around the
    icon square above the label; else exactly one gold label; else the strongest backdrop, either the icon
    square (read at its four inner corners: the glyph fills the centre) or the list bar beside the label,
    when it leads the runner-up by 1.5x (spec: the selected tab has the strongest backdrop)."""
    import cv2
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV) if focus else None
    framed, golds, strength = [], [], []
    for index, b in enumerate(members):
        h, cx = b['h'], b['cx']
        s = 2.0 * h
        sq = (cx - s / 2, b['y0'] - .25 * h - s, cx + s / 2, b['y0'] - .25 * h)
        c, inset = .18 * s, .12 * s
        corners = [v for v in (
            _region_l(lab, sq[0] + inset, sq[1] + inset, sq[0] + inset + c, sq[1] + inset + c),
            _region_l(lab, sq[2] - inset - c, sq[1] + inset, sq[2] - inset, sq[1] + inset + c),
            _region_l(lab, sq[0] + inset, sq[3] - inset - c, sq[0] + inset + c, sq[3] - inset),
            _region_l(lab, sq[2] - inset - c, sq[3] - inset - c, sq[2] - inset, sq[3] - inset)) if v is not None]
        p = .2 * s
        ring = [v for v in (
            _region_l(lab, sq[0] - .15 * s - p, sq[1] - .15 * s - p, sq[2] + .15 * s + p, sq[1] - .15 * s),
            _region_l(lab, sq[0] - .15 * s - p, sq[3] + .15 * s, sq[2] + .15 * s + p, sq[3] + .15 * s + p),
            _region_l(lab, sq[0] - .15 * s - p, sq[1] - .15 * s, sq[0] - .15 * s, sq[3] + .15 * s),
            _region_l(lab, sq[2] + .15 * s, sq[1] - .15 * s, sq[2] + .15 * s + p, sq[3] + .15 * s)) if v is not None]
        icon = abs(float(np.median(corners)) - float(np.median(ring))) if corners and ring else 0.0
        side = [v for v in (_region_l(lab, b['x0'] - 1.2 * h, b['y0'], b['x0'] - .3 * h, b['y1']),
                            _region_l(lab, b['x1'] + .3 * h, b['y0'], b['x1'] + 1.2 * h, b['y1'])) if v is not None]
        around = [v for v in (_region_l(lab, b['x0'] - h, b['y0'] - 1.4 * h, b['x1'] + h, b['y0'] - .7 * h),
                              _region_l(lab, b['x0'] - h, b['y1'] + .7 * h, b['x1'] + h, b['y1'] + 1.4 * h)) if v is not None]
        bar = abs(float(np.median(side)) - float(np.median(around))) if side and around else 0.0
        strength.append(max(icon, bar))
        if focus is not None:
            band = []
            for a, t, z, d in ((sq[0] - .12 * s, sq[1] - .12 * s, sq[2] + .12 * s, sq[1] + .08 * s),
                               (sq[0] - .12 * s, sq[3] - .08 * s, sq[2] + .12 * s, sq[3] + .12 * s),
                               (sq[0] - .12 * s, sq[1], sq[0] + .08 * s, sq[3]),
                               (sq[2] - .08 * s, sq[1], sq[2] + .12 * s, sq[3])):
                a, z = max(0, int(a)), min(image.shape[1], int(z))
                t, d = max(0, int(t)), min(image.shape[0], int(d))
                if z > a and d > t:
                    band.append(hsv[t:d, a:z].reshape(-1, 3))
            band = np.vstack(band) if band else np.zeros((1, 3), np.uint8)
            hit = ((band[:, 0] >= focus['hue'][0] / 2) & (band[:, 0] <= focus['hue'][1] / 2)
                   & (band[:, 1] >= focus['min_s'] * 255) & (band[:, 2] >= focus['levels'][0] * 255))
            if hit.mean() >= .15:
                framed.append(index)
        ink = _ink(image, lab, b) if gold else None
        if ink is not None and _gold(ink, gold):
            golds.append(index)
    if len(framed) == 1:
        return framed[0]
    if len(golds) == 1:
        return golds[0]
    order = sorted(range(len(strength)), key=lambda i: -strength[i])
    if len(order) > 1 and strength[order[0]] >= 1.5 * max(strength[order[1]], 1.0):
        return order[0]
    return None


def _groups(image, lab, items, rules, focus, span, taken):
    """Columns and rows whose labels belong to a user-confirmed tab group, with the selected one."""
    found = []
    candidates = _tab_columns(items, _TAB_MIN_H * span) + _tab_rows(items, _TAB_MIN_H * span)
    for members in candidates:
        if {b['i'] for b in members} & taken:
            continue
        for group in rules.get('groups', ()):
            spelled = [next((tab for tab in group['tabs'] if _same_tab(re.sub(r'\s', '', b['text']), tab)), None)
                       for b in members]
            order = [group['tabs'].index(t) for t in spelled if t is not None]
            # 路径 2：主菜单图标格里的“商店”“任务”会碰上“奖励/任务/商店/限时商店”：要求顺序与确认的
            # 一致，四个以上的组至少对上三个（2026-10 新抽 300 帧里唯一的误报）。
            if len(order) < (3 if len(group['tabs']) >= 4 else 2) or order != sorted(order):
                continue
            # 路径 2：同列里混进的非页签字（价格、按键提示）不参与判选中。
            inside = [(b, t) for b, t in zip(members, spelled) if t is not None]
            pick = _selected(image, lab, [b for b, _ in inside], rules, focus)
            if pick is not None:
                found.append(dict(kind='group', active=inside[pick][1], row=[t for _, t in inside],
                                  _x=min(b['x0'] for b, _ in inside), _y=min(b['y0'] for b, _ in inside)))
            taken |= {b['i'] for b in members}
            break
    return found


def _band(value):
    return isinstance(value, list) and len(value) == 2 and all(map(_fraction, value)) and value[0] < value[1]


def _tab_rules(rules):
    gold = rules.get('gold')
    if (not isinstance(gold, dict) or type(gold.get('min_b')) not in (int, float)
            or not _fraction(gold.get('min_s'))):
        raise ValueError('layout.tabs.gold 须含数值 min_b 与 0–1 的 min_s。')
    if not _fraction(rules.get('top_max_y')) or rules['top_max_y'] <= 0:
        raise ValueError('layout.tabs.top_max_y 必须是 (0, 1] 的高度比例。')
    bands = rules.get('text_bands')
    if not isinstance(bands, list) or not all(map(_band, bands)):
        raise ValueError('layout.tabs.text_bands 必须是 0–1 递增区间的数组。')
    groups = rules.get('groups', [])
    if not isinstance(groups, list):
        raise ValueError('layout.tabs.groups 必须是数组。')
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError('layout.tabs.groups 的每项必须是对象。')
        _text(group.get('screen'), 'layout.tabs.groups screen')
        _texts(group.get('tabs'), 'layout.tabs.groups tabs')
        if len(group['tabs']) < 2:
            raise ValueError('layout.tabs.groups tabs 至少要有两个页签文字。')


def _heading_rules(rules):
    main, side = rules.get('main'), rules.get('side')
    if main is not None and (not isinstance(main, dict)
                             or not all(_band(main.get(key)) for key in ('margin', 'y', 'height'))):
        raise ValueError('layout.headings.main 须含 0–1 递增区间 margin、y、height。')
    if side is not None and (not isinstance(side, dict) or not _band(side.get('y'))
                             or not _fraction(side.get('min_height'))):
        raise ValueError('layout.headings.side 须含 0–1 递增区间 y 与 0–1 的 min_height。')
    _texts(rules.get('icon_tabs', []), 'layout.headings.icon_tabs')


def _focus_rules(rules):
    hue = rules.get('hue')
    if (not isinstance(hue, list) or len(hue) != 2 or not all(type(v) in (int, float) for v in hue)
            or not 0 <= hue[0] < hue[1] <= 360 or not _fraction(rules.get('min_s'))
            or not isinstance(rules.get('levels'), list) or not rules['levels']
            or not all(map(_fraction, rules['levels']))):
        raise ValueError('layout.focus 须含色相区间 hue（度）、0–1 的 min_s 与亮度档 levels。')


def validate(layout):
    # 路径 2：用户按本游戏的视觉规范手填版式规则。高度按游戏画面高度归一化，横向距离也以画面高度为单位：
    # 燕云在 PC 上高度按比例、宽度按到较近边缘的固定边距适配，带鱼屏与 16:9 同一套数值。
    unknown = set(layout) - {'recognizer', 'tabs', 'headings', 'focus'}
    if unknown:
        raise ValueError('layout 不认识的键：' + '、'.join(sorted(unknown)))
    for key, check in (('tabs', _tab_rules), ('headings', _heading_rules), ('focus', _focus_rules)):
        if key in layout:
            if not isinstance(layout[key], dict):
                raise ValueError(f'layout.{key} 必须是对象。')
            check(layout[key])


def derive(image, full, items, layout):
    """Tabs (with _x/_y for layout_common to order levels), headings and focus of one full-OCR frame."""
    import cv2
    top, bottom = _game_rows(image)
    span = bottom - top
    lab = cv2.cvtColor(image.astype(np.float32) / 255, cv2.COLOR_BGR2Lab)
    rows = _tab_rows(items, _TAB_MIN_H * span)
    out = {}
    tab_rules = layout.get('tabs')
    tabs = _active_tabs(image, lab, rows, tab_rules, top, span) if tab_rules else []
    if 'headings' in layout:
        in_rows = {box['i'] for members in rows for box in members}
        headings = _headings(image, lab, items, layout['headings'], tab_rules, top, span, in_rows)
        if headings:
            out['headings'] = headings
        # 路径 2：背包亮着的图标页签就是侧窗标题（用户 2026-10-23 给的规格）。
        for name in headings.get('side', ()):
            if name in layout['headings'].get('icon_tabs', ()):
                tabs.insert(0, dict(kind='icon', active=name, row=[name]))
    if tab_rules and tab_rules.get('groups'):
        taken = set().union(*(tab.get('_ids', set()) for tab in tabs))
        tabs += _groups(image, lab, items, tab_rules, layout.get('focus'), span, taken)
    if tabs:
        out['tabs'] = tabs
    if 'focus' in layout:
        focus = _focus(image, full, items, layout['focus'])
        if focus:
            out['focus'] = focus
    return out