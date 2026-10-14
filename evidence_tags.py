"""System / gameplay tags for evidence (the insight window's screen library), independent of recorded paths."""
import json
import math
from pathlib import Path

import agent_protocol as protocol
from session_metadata import metadata_lock


FILE = 'tags.json'


def _empty():
    return dict(version=1, groups=[], tags=[], activities={}, assignments={})


def read_tags(vault):
    path = Path(vault).resolve() / FILE
    # 路径 1/3：还没建立标签的资料库从空表开始，界面库显示为空。
    if not path.is_file():
        return _empty()
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    _validate(data)
    return data


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(f'{label}必须是 1～200 字的文字。')
    return value


def _cover(value, label):
    if not isinstance(value, dict) or not isinstance(value.get('session_id'), str) \
            or type(value.get('at')) not in (int, float) or not math.isfinite(value['at']) or value['at'] < 0:
        raise ValueError(f'{label}的封面必须是 {{session_id, at}}。')


def _validate(data):
    # 路径 3：agent 整份写入标签表；写坏一处，界面库和筛选都会算错，所以整份先校验。
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('tags.json 必须是 version=1 的标签表。')
    for key, kind in (('groups', list), ('tags', list), ('activities', dict), ('assignments', dict)):
        if not isinstance(data.get(key), kind):
            raise ValueError(f'tags.json 的 {key} 格式不对。')
    groups = set()
    for group in data['groups']:
        if not isinstance(group, dict) or _text(group.get('id'), '维度编号') in groups:
            raise ValueError('维度编号缺失或重复。')
        _text(group.get('name'), '维度名称')
        groups.add(group['id'])
    tags = set()
    for tag in data['tags']:
        if not isinstance(tag, dict) or _text(tag.get('id'), '标签编号') in tags:
            raise ValueError('标签编号缺失或重复。')
        _text(tag.get('name'), '标签名称')
        if tag.get('group') not in groups:
            raise ValueError('标签的维度不存在：' + tag['id'])
        if not isinstance(tag.get('keywords', []), list):
            raise ValueError('标签关键词必须是列表：' + tag['id'])
        for keyword in tag.get('keywords', []):
            _text(keyword, '关键词')
        if 'cover' in tag:
            _cover(tag['cover'], tag['id'])
        tags.add(tag['id'])
    for key, values in data['activities'].items():
        if '/' not in key or not isinstance(values, list) or not set(values) <= tags:
            raise ValueError('活动标签格式不对或引用了不存在的标签：' + str(key))
    for key, change in data['assignments'].items():
        if '/' not in key or not isinstance(change, dict) or set(change) - {'add', 'remove'}:
            raise ValueError('逐条增减格式不对：' + str(key))
        for values in change.values():
            if not isinstance(values, list) or not set(values) <= tags:
                raise ValueError('逐条增减引用了不存在的标签：' + str(key))
    return data


def write_tags(vault, data):
    """Replace the whole table after validation; covers the user set are kept unless the new table sets one."""
    _validate(data)
    with metadata_lock(vault):
        covers = {tag['id']: tag['cover'] for tag in read_tags(vault)['tags'] if 'cover' in tag}
        for tag in data['tags']:
            if 'cover' not in tag and tag['id'] in covers:
                tag['cover'] = covers[tag['id']]
        protocol._write(vault, FILE, data)
    return dict(groups=len(data['groups']), tags=len(data['tags']), activities=len(data['activities']),
                assignments=len(data['assignments']))


def instance_tags(vault, rows=None, data=None):
    """Map 'session/instance' -> sorted tag ids: activity tags ∪ keyword hits ∪ add − remove."""
    import issue_registry
    data = data or read_tags(vault)
    rows = issue_registry.query_instances(vault) if rows is None else rows
    keywords = [(tag['id'], tag.get('keywords', [])) for tag in data['tags']]
    result = {}
    for row in rows:
        key = row['session_id'] + '/' + row['instance_id']
        tags = set(data['activities'].get(row['session_id'] + '/' + row['event_id'], []))
        # 路径 2：同一玩法的界面写法不一（活动（燕语江湖）/活动/江湖弈、江湖弈/对局），按关键词都能找到。
        # 关键词只看证据所在的界面：目录里有的用正式编号（旧写法如“伙伴/萌主争锋/…”只用来对应，不再带出“伙伴”），
        # 目录里没有的用原始写法；跳转路径是“从哪儿来”，交给活动标签，不参与匹配。
        texts = [row.get('catalog_screen') or row.get('screen') or '']
        tags |= {tag for tag, words in keywords if any(word in text for word in words for text in texts)}
        change = data['assignments'].get(key, {})
        tags = (tags | set(change.get('add', []))) - set(change.get('remove', []))
        if tags:
            result[key] = sorted(tags)
    return result


def report(vault):
    """What an agent needs to review tagging: counts per tag, untagged evidence, untagged activities."""
    import issue_registry
    data = read_tags(vault)
    rows = issue_registry.query_instances(vault)
    tagged = instance_tags(vault, rows, data)
    counts = {tag['id']: 0 for tag in data['tags']}
    for tags in tagged.values():
        for tag in tags:
            counts[tag] += 1
    activities = {}
    for row in rows:
        key = row['session_id'] + '/' + row['event_id']
        if key not in data['activities']:
            activities.setdefault(key, dict(activity=key, title=row['event_title'], instances=0))['instances'] += 1
    untagged = [dict(key=row['session_id'] + '/' + row['instance_id'], screen=row.get('screen'),
                     activity=row['event_title'], statement=row['statement'][:60])
                for row in rows if row['session_id'] + '/' + row['instance_id'] not in tagged]
    return dict(tags=[dict(id=tag['id'], name=tag['name'], group=tag['group'], instances=counts[tag['id']])
                      for tag in data['tags']],
                untagged=len(untagged), untagged_sample=untagged[:200],
                activities_without_tags=sorted(activities.values(), key=lambda row: -row['instances']))


def set_cover(vault, tag_id, session_id, at):
    with metadata_lock(vault):
        data = read_tags(vault)
        tag = next((tag for tag in data['tags'] if tag['id'] == tag_id), None)
        if tag is None:
            raise ValueError('标签不存在：' + str(tag_id))
        # 路径 1：用户在证据卡上右键“设为封面”。
        tag['cover'] = dict(session_id=session_id, at=at)
        _cover(tag['cover'], tag_id)
        protocol._write(vault, FILE, data)
        return tag
