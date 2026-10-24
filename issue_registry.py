"""Library issue labels and read-only cross-session judgment queries."""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import uuid

import agent_protocol as protocol
from session_metadata import metadata_lock


FILE = 'issues.json'
LINKS = 'issue-links.json'
BUG = 'BUG'
ROLES = ('support', 'counter')
DEPTH = 3  # 洞察 → 议题 → 子议题


def _bug_issue():
    return dict(id=BUG, title='Bug', status='confirmed',
                description='记录者在原话里明确说是 bug 的问题。候选按关键词定位，跨场次分析时分组为子议题。')


def _base(value):
    return value == BUG or value.startswith('TA-') and len(value) > 3 or re.fullmatch(r'N-\d{3}', value)


def _identifier(value):
    # 路径 2/3：命令行及外部 agent 只能引用用户 TA 标签、三位 N 候选标签、固定的 BUG，
    # 以及它们下级的编号（最多再接两段 .n）。
    if isinstance(value, str):
        base, dot, rest = value.partition('.')
        if _base(base) and (not dot or re.fullmatch(r'\d{1,3}(\.\d{1,3})?', rest)):
            return value
    raise ValueError('议题 id 必须是 TA- 开头的用户编号、N- 加三位数字、BUG，或它们后接一到两段 .n 的下级编号。')


def _depth(rows, ident):
    """Levels from the top down to this issue (top = 1); rejects cycles."""
    parents = {row['id']: row.get('parent') for row in rows}
    seen, current = set(), ident
    while current is not None:
        if current in seen:
            raise ValueError('议题层级成环：' + ident)
        seen.add(current)
        current = parents.get(current)
    return len(seen)


def _height(rows, ident):
    """Levels from this issue down to its deepest descendant (leaf = 1)."""
    children = [row['id'] for row in rows if row.get('parent') == ident]
    return 1 + max((_height(rows, child) for child in children), default=0)


def descendants(rows, ident):
    found, frontier = set(), {ident}
    while frontier:
        frontier = {row['id'] for row in rows if row.get('parent') in frontier} - found
        found |= frontier
    return found


def _title(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('议题标题必须是非空字符串。')
    return value.strip()


def _status(value):
    if value not in ('candidate', 'confirmed'):
        raise ValueError('议题状态必须是 candidate 或 confirmed。')
    return value


def read_registry(vault):
    path = Path(vault).resolve() / FILE
    # 路径 2/3：尚未创建议题的资料库从空表开始，未知引用仍由协议拒绝。
    if not path.is_file():
        return dict(version=1, issues=[])
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('issues'), list):
        raise ValueError('issues.json 必须是 version=1 的议题目录。')
    identifiers = set()
    for row in data['issues']:
        if not isinstance(row, dict):
            raise ValueError('议题必须是对象。')
        ident = _identifier(row.get('id'))
        if ident in identifiers:
            raise ValueError('议题 id 重复：' + ident)
        identifiers.add(ident)
        _title(row.get('title'))
        _status(row.get('status'))
        if not isinstance(row.get('description'), str):
            raise ValueError('议题 description 必须是字符串。')
        parent = row.get('parent')
        if parent is not None and (not isinstance(parent, str) or ident == BUG):
            raise ValueError('议题 parent 必须是上级编号，BUG 不能有上级：' + ident)
    # 路径 2/3：洞察 → 议题 → 子议题最多三层；编号是工作代号，挪动层级后前缀不必等于上级。
    for row in data['issues']:
        if row.get('parent') and row['parent'] not in identifiers:
            raise ValueError('议题的上级不存在：' + row['id'])
        if _depth(data['issues'], row['id']) > DEPTH:
            raise ValueError('议题最多三层：' + row['id'])
    # 路径 3：BUG 是固定议题，单场次整理可直接引用，未写入过的资料库也能读到它。
    if BUG not in identifiers:
        data['issues'].append(_bug_issue())
    return data


def read_links(vault):
    path = Path(vault).resolve() / LINKS
    # 路径 2/3：尚未建立议题对应表的资料库从空表开始。
    if not path.is_file():
        return dict(version=1, links=[])
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('links'), list):
        raise ValueError('issue-links.json 必须是 version=1 的议题对应表。')
    return data


def _complete_results(vault):
    """Map session id -> (result digest, instance ids, instances) for complete sessions."""
    sessions = {}
    for path in sorted((Path(vault).resolve() / '场次').glob('*/session.json')):
        meta = json.loads(path.read_text(encoding='utf-8-sig'))
        state = protocol.preprocessing_status(path.parent, include_result=True)
        if state['state'] != 'complete':
            continue
        instances = state['result'].get('instances', [])
        digest = protocol._file_hash(protocol._path(path.parent, protocol.RESULT))
        sessions[meta['id']] = (digest, {row['id'] for row in instances}, meta, state['result'])
    return sessions


def _active(link, sessions):
    # 路径 1：重新整理后实例编号会变；只认绑定当时结果摘要的对应，旧对应保留但不再生效。
    found = sessions.get(link['session_id'])
    return found is not None and found[0] == link['result_sha256'] and link['instance_id'] in found[1]


def list_issues(vault):
    data = read_registry(vault)
    links = read_links(vault)['links']
    sessions = _complete_results(vault) if links else {}
    for row in data['issues']:
        mine = [link for link in links if link['issue'] == row['id']]
        active = sum(_active(link, sessions) for link in mine)
        row['links_active'], row['links_stale'] = active, len(mine) - active
    return data


def link_instances(vault, rows):
    """Add or update issue -> instance links; every row is checked before anything is written."""
    if not isinstance(rows, list) or not rows:
        raise ValueError('至少需要一条议题对应。')
    with metadata_lock(vault):
        known = {row['id'] for row in read_registry(vault)['issues']}
        data = read_links(vault)
        sessions = _complete_results(vault)
        index = {(link['issue'], link['session_id'], link['instance_id']): link for link in data['links']}
        added = 0
        for row in rows:
            # 路径 3：跨场次分析 agent 批量提交对应；未知议题或实例会让查询永远找不到。
            if not isinstance(row, dict):
                raise ValueError('议题对应必须是对象。')
            issue, session_id, instance_id = row.get('issue'), row.get('session_id'), row.get('instance_id')
            if issue not in known:
                raise ValueError('议题不存在：' + str(issue))
            if session_id not in sessions or instance_id not in sessions[session_id][1]:
                raise ValueError(f'实例不存在或场次未完成整理：{session_id}/{instance_id}')
            reason = row.get('reason', '')
            if not isinstance(reason, str) or len(reason) > 1000:
                raise ValueError('归类理由必须是不超过 1000 字的字符串。')
            # 路径 3：反例要和支持证据分开存，洞察界面按角色分栏。
            role = row.get('role', 'support')
            if role not in ROLES:
                raise ValueError('证据角色必须是 support 或 counter。')
            key = (issue, session_id, instance_id)
            added += key not in index
            index[key] = dict(issue=issue, session_id=session_id, instance_id=instance_id,
                              result_sha256=sessions[session_id][0], reason=reason.strip(), role=role)
        data['links'] = list(index.values())
        protocol._write(vault, LINKS, data)
        return dict(added=added, updated=len(rows) - added, total=len(data['links']))


def unlink_instance(vault, issue, session_id, instance_id):
    return unlink_instances(vault, [dict(issue=issue, session_id=session_id, instance_id=instance_id)])


def unlink_instances(vault, rows):
    """Remove issue -> instance links; every row must name an existing link before anything is written."""
    if not isinstance(rows, list) or not rows:
        raise ValueError('至少需要一条要撤下的议题对应。')
    with metadata_lock(vault):
        data = read_links(vault)
        present = {(link['issue'], link['session_id'], link['instance_id']) for link in data['links']}
        drop = set()
        for row in rows:
            # 路径 3：按简报写回议题树时，一次撤下一批不属于本议题的证据；任何一条对不上都不写。
            if not isinstance(row, dict):
                raise ValueError('要撤下的议题对应必须是对象。')
            key = (row.get('issue'), row.get('session_id'), row.get('instance_id'))
            if key not in present:
                raise ValueError('没有这条议题对应：' + '/'.join(map(str, key)))
            drop.add(key)
        data['links'] = [link for link in data['links'] if (link['issue'], link['session_id'], link['instance_id']) not in drop]
        protocol._write(vault, LINKS, data)
        return dict(removed=len(drop), total=len(data['links']))


def _find(data, ident):
    row = next((row for row in data['issues'] if row['id'] == ident), None)
    if row is None:
        raise ValueError('议题不存在：' + str(ident))
    return row


def add_issue(vault, title, ident=None, status='candidate', parent=None):
    with metadata_lock(vault):
        data = read_registry(vault)
        if parent is not None:
            # 路径 3：跨场次分析把洞察或议题下的具体模式写成下级，编号接在上级后面。
            _find(data, parent)
            if _depth(data['issues'], parent) >= DEPTH:
                raise ValueError('议题最多三层，子议题下不能再建下级。')
            if ident is None:
                # 挪动过层级的编号仍占用前缀，按编号而不是按现在的上级找下一个序号。
                pattern = re.compile(re.escape(parent) + r'\.(\d{1,3})')
                numbers = [int(match.group(1)) for row in data['issues'] if (match := pattern.fullmatch(row['id']))]
                ident = f'{parent}.{max(numbers, default=0) + 1}'
            if _identifier(ident).rpartition('.')[0] != parent:
                raise ValueError('新建下级的编号必须是上级编号加 .n。')
        elif ident is None:
            numbers = [int(row['id'][2:]) for row in data['issues'] if re.fullmatch(r'N-\d{3}', row['id'])]
            number = max(numbers, default=0) + 1
            if number > 999:
                raise ValueError('三位 N- 候选编号已用完。')
            ident = f'N-{number:03d}'
        elif '.' in _identifier(ident):
            raise ValueError('新建子议题请指定父议题。')
        _status(status)
        if parent is None and ident.startswith('N-') and status != 'candidate':
            raise ValueError('新建 N- 议题只能是 candidate；确认已有议题请使用 issues-update。')
        if any(row['id'] == ident for row in data['issues']):
            raise ValueError('议题 id 重复：' + ident)
        row = dict(id=ident, title=_title(title), description='', status=status)
        if parent is not None:
            row['parent'] = parent
        data['issues'].append(row)
        protocol._write(vault, FILE, data)
        return row


def move_issue(vault, ident, parent=None):
    """Put an existing issue under another parent (or back on top); codes, links and results stay."""
    with metadata_lock(vault):
        data = read_registry(vault)
        row = _find(data, ident)
        # 路径 1/3：重组洞察时把议题挪到别的洞察或新的中间议题下，证据跟着编号走。
        if ident == BUG:
            raise ValueError('BUG 是固定议题，不能挪动。')
        if parent is not None:
            _find(data, parent)
            if parent == ident or parent in descendants(data['issues'], ident):
                raise ValueError('不能把议题挪到它自己或它的下级下面。')
            if _depth(data['issues'], parent) + _height(data['issues'], ident) > DEPTH:
                raise ValueError('挪过去会超过三层。')
            row['parent'] = parent
        else:
            row.pop('parent', None)
        protocol._write(vault, FILE, data)
        return row


def update_issue(vault, ident, title=None, description=None, status=None):
    return update_issues(vault, [dict(id=ident, title=title, description=description, status=status)])[0]


def update_issues(vault, rows):
    """Change titles, descriptions or statuses; every row is checked before anything is written."""
    if not isinstance(rows, list) or not rows:
        raise ValueError('至少需要一条议题修改。')
    with metadata_lock(vault):
        data = read_registry(vault)
        changed = []
        for change in rows:
            # 路径 3：写回议题树时一次改一批子议题的长说明，从 UTF-8 文件读入，不经命令行参数。
            if not isinstance(change, dict):
                raise ValueError('议题修改必须是对象。')
            ident, title, description, status = (change.get(key) for key in ('id', 'title', 'description', 'status'))
            row = _find(data, ident)
            if ident == BUG and (title is not None or status is not None):
                raise ValueError('BUG 是固定议题，只能修改说明。')
            if title is not None:
                row['title'] = _title(title)
            if description is not None:
                if not isinstance(description, str):
                    raise ValueError('议题 description 必须是字符串。')
                row['description'] = description
            if status is not None:
                row['status'] = _status(status)
            changed.append(row)
        protocol._write(vault, FILE, data)
        return changed


def dismiss_issue(vault, ident):
    """Remove a rejected candidate and its links; confirmed issues are only ever merged."""
    vault = Path(vault).resolve()
    with metadata_lock(vault):
        data = read_registry(vault)
        row = _find(data, ident)
        # 路径 1/2：用户看过证据后判断候选不成立（如“这不是 bug”），驳回它。
        if row['status'] != 'candidate' or ident == BUG:
            raise ValueError('只能驳回候选议题。')
        if any(other.get('parent') == ident for other in data['issues']):
            raise ValueError('该议题下还有子议题，请先处理子议题。')
        for path in (vault / '场次').glob('*/' + protocol.RESULT):
            raw = protocol._load(path.parent, protocol.RESULT, protocol.MAX_RESULT)
            if any(ident in row.get('issue_tags', []) for row in raw.get('instances', [])):
                raise ValueError('有场次结果直接带着这个标签，请改用合并。')
        links = read_links(vault)
        kept = [link for link in links['links'] if link['issue'] != ident]
        removed = len(links['links']) - len(kept)
        if removed:
            links['links'] = kept
            protocol._write(vault, LINKS, links)
        data['issues'] = [other for other in data['issues'] if other['id'] != ident]
        protocol._write(vault, FILE, data)
        return dict(id=ident, links_removed=removed)


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')


def merge_issues(vault, from_id, into_id):
    """Back up original bytes and append calibration bindings before replacement."""
    import event_edits
    vault = Path(vault).resolve()
    with metadata_lock(vault), ExitStack() as locks:
        data = read_registry(vault)
        _find(data, from_id)
        _find(data, into_id)
        if from_id == into_id:
            raise ValueError('不能把议题合并到自身。')
        if BUG in (from_id, into_id):
            raise ValueError('BUG 是固定议题，不能合并。')
        if any(row.get('parent') == from_id for row in data['issues']):
            raise ValueError('该议题下还有子议题，请先合并或移走子议题。')
        plans = []
        for path in sorted((vault / '场次').glob('*/' + protocol.RESULT)):
            folder = path.parent
            locks.enter_context(metadata_lock(folder))
            raw = protocol._load(folder, protocol.RESULT, protocol.MAX_RESULT)
            matches = [row for row in raw.get('instances', []) if from_id in row.get('issue_tags', [])]
            if not matches:
                continue
            result = deepcopy(raw)
            for row in result['instances']:
                row['issue_tags'] = list(dict.fromkeys(
                    into_id if tag == from_id else tag for tag in row['issue_tags']))
            # 路径 1+2+4：合并旧结果时保留旁车中的分析快照，避免 SHA 改变后丢失。
            context = protocol._analysis_context(folder, raw)
            if context is not None:
                result['analysis_context'] = context
            old_digest = protocol._file_hash(path)
            new_digest = hashlib.sha256(_encoded(result)).hexdigest()
            corrections = event_edits._read(folder)
            copied = [dict(row, id=uuid.uuid4().hex, base_result_sha256=new_digest)
                      for row in corrections['history'] if row['base_result_sha256'] == old_digest]
            corrections['history'].extend(copied)
            # 路径 1+2：有人工校准的结果合并标签，追加绑定且保留原历史。
            # 整批预检容量后才写入，复用现有校准历史的 2000 条 / 4 MiB 上限。
            if copied and (len(corrections['history']) > 2000 or len(_encoded(corrections)) > event_edits.MAX_BYTES):
                raise ValueError('合并后手动校准历史超过容量上限；议题与场次尚未修改。')
            if len(_encoded(result)) > protocol.MAX_RESULT:
                raise ValueError('合并后的结果超过 2 MB；议题与场次尚未修改。')
            plans.append(dict(folder=folder, result=result, corrections=corrections, old=old_digest,
                              new=new_digest, copied=len(copied), instances=len(matches)))
        backups = []
        for plan in plans:
            folder = plan['folder']
            backups.append(protocol._backup_result(folder))
            if plan['copied']:
                protocol._write(folder, event_edits.FILE, plan['corrections'])
            protocol._write(folder, protocol.RESULT, plan['result'])
        # 路径 2：合并议题时对应表里的引用一起改到目标议题，重复的对应只保留一条；
        # 被改写的结果换了摘要，同场次其他议题的对应也要跟着换绑，否则全部失效。
        digests = {plan['old']: plan['new'] for plan in plans}
        links = read_links(vault)
        merged = {}
        for link in links['links']:
            link = dict(link, issue=into_id if link['issue'] == from_id else link['issue'],
                        result_sha256=digests.get(link['result_sha256'], link['result_sha256']))
            merged.setdefault((link['issue'], link['session_id'], link['instance_id']), link)
        if links['links']:
            links['links'] = list(merged.values())
            protocol._write(vault, LINKS, links)
        data['issues'] = [row for row in data['issues'] if row['id'] != from_id]
        protocol._write(vault, FILE, data)
        return dict(from_id=from_id, into_id=into_id, sessions=len(plans),
                    instances=sum(plan['instances'] for plan in plans), backups=backups,
                    corrections_migrated=sum(plan['copied'] for plan in plans))


def screen_names(vault, game):
    """Catalog id or alias -> catalog id; confirmed proposals resolve without rewriting results."""
    import game_catalog
    names = {}
    if game and game_catalog.catalog_path(vault, game).is_file():
        screens = game_catalog.load_catalog(vault, game)['screens']
        for row in screens:
            for name in row.get('aliases', []):
                names.setdefault(name, row['id'])
        names.update((row['id'], row['id']) for row in screens)
    return names


def query_instances(vault, issue=None, screen=None, element=None, kind=None, session=None, bug=None):
    rows = []
    requested = set(issue or [])
    # 路径 2/3：查洞察或议题时一并带出它下面所有层级。
    registry = read_registry(vault)['issues']
    for ident in list(requested):
        requested |= descendants(registry, ident)
    sessions = _complete_results(vault)
    linked = {}
    for link in read_links(vault)['links']:
        if _active(link, sessions):
            linked.setdefault((link['session_id'], link['instance_id']), []).append(
                dict(issue=link['issue'], reason=link['reason'], role=link.get('role', 'support')))
    catalogs = {}
    for session_id, (_, _, meta, result) in sessions.items():
        if session is not None and session_id != session:
            continue
        titles = {event['id']: event['title'] for event in result['events']}
        game = meta.get('game')
        if game not in catalogs:
            catalogs[game] = screen_names(vault, game)
        names = catalogs[game]
        for instance in result.get('instances', []):
            links = linked.get((session_id, instance['id']), [])
            tags = list(dict.fromkeys(instance['issue_tags'] + [link['issue'] for link in links]))
            if requested and not requested.intersection(tags):
                continue
            catalog_screen = names.get(instance['screen'])
            # 路径 2：按界面查询时，别名（含已确认的提议名）与正式编号等价。
            if screen is not None and instance['screen'] != screen and (
                    catalog_screen is None or catalog_screen != names.get(screen)):
                continue
            if element is not None and element not in instance['elements']:
                continue
            if kind is not None and instance['kind'] != kind:
                continue
            # 路径 3：跨场次整理按单场标的 bug 取候选（any = 明说和疑似都要）。
            if bug is not None and (not instance.get('bug') if bug == 'any' else instance.get('bug') != bug):
                continue
            row = dict(session_id=meta['id'], instance_id=instance['id'],
                       said_start=min(said['start'] for said in instance['said']),
                       refers_start=instance['refers_to']['start'], refers_end=instance['refers_to']['end'],
                       screen=instance['screen'], elements=instance['elements'], kind=instance['kind'],
                       statement=instance['statement'], issue_tags=tags, issue_links=links,
                       event_id=instance['event_id'], event_title=titles.get(instance['event_id'], ''),
                       refers_basis=instance['refers_to']['basis'], catalog_screen=catalog_screen,
                       # 画面证据里 agent 核对过的时刻，比所指区间的起点更能代表界面本身。
                       frame_at=next((row['start'] for row in instance['evidence'] if row['kind'] == 'video'), None),
                       **{key: instance[key] for key in ('route', 'screen_proposed', 'screen_context', 'compare_to', 'bug')
                          if key in instance})
            rows.append((str(meta.get('created') or meta['id']), row))
    # 指向本场之前的实例没有本场所指时间，按说出口的时间排序。
    rows.sort(key=lambda item: (item[0], item[1]['refers_start'] if item[1]['refers_start'] is not None
                                else item[1]['said_start']))
    return [row for _, row in rows]
