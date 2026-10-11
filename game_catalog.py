"""Local, deterministic screen catalog validation and OCR text matching."""
import json
from pathlib import Path


SOURCES = ('manual', 'ocr_cluster', 'engine')


def catalog_path(vault, game):
    # 路径 2：catalog 命令以游戏名定位资料库中的单游戏目录。
    if not isinstance(game, str) or not game.strip() or game in ('.', '..') or '/' in game or '\\' in game or ':' in game:
        raise ValueError('游戏名必须是单个目录名称。')
    return Path(vault).resolve() / 'game-assets' / game / 'catalog.json'


def _text(value, label):
    # 路径 2：用户手工编辑目录后通过 catalog-validate 检查格式。
    if not isinstance(value, str) or not value.strip():
        raise ValueError(label + ' 必须是非空字符串。')


def _texts(value, label):
    if not isinstance(value, list):
        raise ValueError(label + ' 必须是字符串数组。')
    for text in value:
        _text(text, label)


def _optional_fields(item, label):
    if 'source' in item and item['source'] not in SOURCES:
        raise ValueError(label + ' source 必须是 manual、ocr_cluster 或 engine。')
    if 'engine_id' in item:
        _text(item['engine_id'], label + ' engine_id')
    if 'aliases' in item:
        _texts(item['aliases'], label + ' aliases')


def _fraction(value):
    return type(value) in (int, float) and 0 <= value <= 1


def _title_regions(regions):
    # 路径 2：用户按设计规范手填标题区坐标；像素坐标或越界会让裁图为空或切到别处。
    if not isinstance(regions, list) or not regions:
        raise ValueError('title_regions 必须是非空数组。')
    ids = set()
    for region in regions:
        if not isinstance(region, dict):
            raise ValueError('title region 必须是对象。')
        _text(region.get('id'), 'title region id')
        if region['id'] in ids:
            raise ValueError('title region id 重复：' + region['id'])
        ids.add(region['id'])
        rect = region.get('rect')
        if (not isinstance(rect, list) or len(rect) != 4 or not all(map(_fraction, rect))
                or rect[2] <= 0 or rect[3] <= 0 or rect[0] + rect[2] > 1 or rect[1] + rect[3] > 1):
            raise ValueError('title region rect 必须是 0–1 的归一化 [x,y,w,h]，且不超出画面。')
        if 'detect' in region:
            detect = region['detect']
            span = detect.get('x_range') if isinstance(detect, dict) else None
            if (not isinstance(detect, dict) or detect.get('type') != 'vertical_edge'
                    or not isinstance(span, list) or len(span) != 2
                    or not all(map(_fraction, span)) or span[0] >= span[1]):
                raise ValueError('title region detect 须为 vertical_edge，x_range 为 0–1 的递增区间。')


def validate_catalog(data):
    """Validate the v1 format, with globally unique element IDs."""
    # 路径 2：catalog-validate 检查手工目录，避免无效或重复 ID 的引用。
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('界面目录 version 必须是 1。')
    _text(data.get('game'), 'game')
    if 'title_regions' in data:
        _title_regions(data['title_regions'])
    if not isinstance(data.get('screens'), list):
        raise ValueError('screens 必须是数组。')
    screen_ids, element_ids = set(), set()
    for screen in data['screens']:
        if not isinstance(screen, dict):
            raise ValueError('screen 必须是对象。')
        _text(screen.get('id'), 'screen id')
        _text(screen.get('name'), 'screen name')
        if screen['id'] in screen_ids:
            raise ValueError('screen id 重复：' + screen['id'])
        screen_ids.add(screen['id'])
        if screen.get('source') not in SOURCES:
            raise ValueError('screen source 必须是 manual、ocr_cluster 或 engine。')
        _optional_fields(screen, 'screen')
        rule = screen.get('match')
        if not isinstance(rule, dict):
            raise ValueError('screen match 必须是对象。')
        for field in ('all_of', 'any_of', 'none_of'):
            _texts(rule.get(field), 'match ' + field)
        if 'title_any_of' in rule:
            _texts(rule['title_any_of'], 'match title_any_of')
        if not isinstance(screen.get('elements'), list):
            raise ValueError('screen elements 必须是数组。')
        for element in screen['elements']:
            if not isinstance(element, dict):
                raise ValueError('element 必须是对象。')
            _text(element.get('id'), 'element id')
            _text(element.get('name'), 'element name')
            if element['id'] in element_ids:
                raise ValueError('element id 重复：' + element['id'])
            element_ids.add(element['id'])
            _optional_fields(element, 'element')
            if 'notes' in element and not isinstance(element['notes'], str):
                raise ValueError('element notes 必须是字符串。')
    return data


def load_catalog(vault, game):
    data = json.loads(catalog_path(vault, game).read_text(encoding='utf-8-sig'))
    validate_catalog(data)
    if data['game'] != game:
        raise ValueError('目录 game 与选择的游戏不一致。')
    return data


def session_catalog(folder):
    folder = Path(folder).resolve()
    meta = json.loads((folder / 'session.json').read_text(encoding='utf-8-sig'))
    game = meta.get('game')
    # 路径 2：context-build 可在尚未创建界面目录的场次运行。
    if not game or not catalog_path(folder.parent.parent, game).is_file():
        return None
    return load_catalog(folder.parent.parent, game)


def validate(vault, game):
    data = load_catalog(vault, game)
    return dict(path=str(catalog_path(vault, game)), game=data['game'],
                screens=len(data['screens']),
                elements=sum(len(screen['elements']) for screen in data['screens']))


def match_frame(catalog, frame):
    """Return the best matching screen, retaining catalog order for ties."""
    titles = ' '.join(title['text'] for title in frame.get('titles', ()))
    # 路径 2：两层轨道先按标题区文字定位界面，命中词数多者优先，并列按目录先后。
    if titles:
        best, best_score = None, 0
        for screen in catalog['screens']:
            score = sum(word in titles for word in screen['match'].get('title_any_of', ()))
            if score > best_score:
                best, best_score = screen, score
        if best is not None:
            return best
    if 'items' not in frame:
        return None
    text = ' '.join(item[2] for item in frame['items'])
    best, best_score = None, -1
    for screen in catalog['screens']:
        rule = screen['match']
        if not all(word in text for word in rule['all_of']):
            continue
        any_hits = sum(word in text for word in rule['any_of'])
        if rule['any_of'] and not any_hits:
            continue
        if any(word in text for word in rule['none_of']):
            continue
        score = len(rule['all_of']) + any_hits
        if score > best_score:
            best, best_score = screen, score
    return best


def match_screens(catalog, frames):
    """Merge adjacent observations; end is the last observed frame time."""
    spans = []
    for frame in frames:
        screen = match_frame(catalog, frame) if catalog is not None else None
        # 路径 2：只识别了标题区的帧若标题未命中，没有整屏文字可判断，不延长也不打断分段。
        if screen is None and 'items' not in frame:
            continue
        ident = screen['id'] if screen is not None else None
        if spans and spans[-1]['screen'] == ident:
            spans[-1]['end'] = frame['t']
            continue
        span = dict(start=frame['t'], end=frame['t'], screen=ident, source='ocr')
        if screen is not None and 'engine_id' in screen:
            span['engine_id'] = screen['engine_id']
        spans.append(span)
    return spans


def suggest(folder, top=30):
    """Count title-area text without assigning names or editing the catalog."""
    from context_track import load_track
    track = load_track(folder)
    counts = {}
    for frame in track['frames']:
        # 路径 2：两层轨道直接统计标题区文字，供用户填写 title_any_of。
        if 'titles' in frame:
            title = ' '.join(row['text'] for row in frame['titles'])
        else:
            title = ' '.join(item[2] for item in frame['items'] if item[1] < 70).strip()
        if not title:
            continue
        row = counts.setdefault(title, dict(text=title, count=0, samples=[]))
        row['count'] += 1
        if len(row['samples']) < 5:
            row['samples'].append(frame['t'])
    return dict(titles=sorted(counts.values(), key=lambda row: -row['count'])[:top])


def hotwords(vault, game, output):
    catalog = load_catalog(vault, game)
    words = {}
    for screen in catalog['screens']:
        for item in (screen, *screen['elements']):
            for text in (item['name'], *item.get('aliases', [])):
                words.setdefault(text.strip(), None)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(''.join(word + '\n' for word in words), encoding='utf-8')
    return dict(path=str(output), game=game, count=len(words))
