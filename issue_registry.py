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


def _identifier(value):
    # 路径 2/3：命令行及外部 agent 只能引用用户 TA 标签或三位 N 候选标签。
    if not isinstance(value, str) or not (value.startswith('TA-') and len(value) > 3 or re.fullmatch(r'N-\d{3}', value)):
        raise ValueError('议题 id 必须是 TA- 开头的用户编号或 N- 加三位数字。')
    return value


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
    return data


def list_issues(vault):
    return read_registry(vault)


def _find(data, ident):
    row = next((row for row in data['issues'] if row['id'] == ident), None)
    if row is None:
        raise ValueError('议题不存在：' + str(ident))
    return row


def add_issue(vault, title, ident=None, status='candidate'):
    with metadata_lock(vault):
        data = read_registry(vault)
        if ident is None:
            numbers = [int(row['id'][2:]) for row in data['issues'] if row['id'].startswith('N-')]
            number = max(numbers, default=0) + 1
            if number > 999:
                raise ValueError('三位 N- 候选编号已用完。')
            ident = f'N-{number:03d}'
        _identifier(ident)
        _status(status)
        if ident.startswith('N-') and status != 'candidate':
            raise ValueError('新建 N- 议题只能是 candidate；确认已有议题请使用 issues-update。')
        if any(row['id'] == ident for row in data['issues']):
            raise ValueError('议题 id 重复：' + ident)
        row = dict(id=ident, title=_title(title), description='', status=status)
        data['issues'].append(row)
        protocol._write(vault, FILE, data)
        return row


def update_issue(vault, ident, title=None, description=None, status=None):
    with metadata_lock(vault):
        data = read_registry(vault)
        row = _find(data, ident)
        if title is not None:
            row['title'] = _title(title)
        if description is not None:
            if not isinstance(description, str):
                raise ValueError('议题 description 必须是字符串。')
            row['description'] = description
        if status is not None:
            row['status'] = _status(status)
        protocol._write(vault, FILE, data)
        return row


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
            plans.append(dict(folder=folder, result=result, corrections=corrections,
                              copied=len(copied), instances=len(matches)))
        backups = []
        for plan in plans:
            folder = plan['folder']
            backups.append(protocol._backup_result(folder))
            if plan['copied']:
                protocol._write(folder, event_edits.FILE, plan['corrections'])
            protocol._write(folder, protocol.RESULT, plan['result'])
        data['issues'] = [row for row in data['issues'] if row['id'] != from_id]
        protocol._write(vault, FILE, data)
        return dict(from_id=from_id, into_id=into_id, sessions=len(plans),
                    instances=sum(plan['instances'] for plan in plans), backups=backups,
                    corrections_migrated=sum(plan['copied'] for plan in plans))


def query_instances(vault, issue=None, screen=None, element=None, kind=None, session=None):
    rows = []
    requested = set(issue or [])
    for path in sorted((Path(vault).resolve() / '场次').glob('*/session.json')):
        meta = json.loads(path.read_text(encoding='utf-8-sig'))
        if session is not None and meta.get('id') != session:
            continue
        state = protocol.preprocessing_status(path.parent, include_result=True)
        if state['state'] != 'complete':
            continue
        for instance in state['result'].get('instances', []):
            if requested and not requested.intersection(instance['issue_tags']):
                continue
            if screen is not None and instance['screen'] != screen:
                continue
            if element is not None and element not in instance['elements']:
                continue
            if kind is not None and instance['kind'] != kind:
                continue
            row = dict(session_id=meta['id'], instance_id=instance['id'],
                       said_start=min(said['start'] for said in instance['said']),
                       refers_start=instance['refers_to']['start'], refers_end=instance['refers_to']['end'],
                       screen=instance['screen'], elements=instance['elements'], kind=instance['kind'],
                       statement=instance['statement'], issue_tags=instance['issue_tags'])
            rows.append((str(meta.get('created') or meta['id']), row))
    rows.sort(key=lambda item: (item[0], item[1]['refers_start']))
    return [row for _, row in rows]
