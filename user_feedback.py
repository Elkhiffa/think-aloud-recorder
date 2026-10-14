"""User feedback on agent-built issues and evidence; the next cross-session run resolves it."""
from datetime import datetime
import json
from pathlib import Path
import uuid

import agent_protocol as protocol
from session_metadata import metadata_lock


FILE = 'feedback.json'
STATUSES = ('open', 'resolved')


def read_feedback(vault):
    path = Path(vault).resolve() / FILE
    # 路径 1/3：还没留过反馈的资料库从空表开始。
    if not path.is_file():
        return dict(version=1, items=[])
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('items'), list):
        raise ValueError('feedback.json 必须是 version=1 的反馈表。')
    return data


def _text(value, label, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label}必须是 1～{limit} 字的文字。')
    return value.strip()


def _target(vault, value):
    import issue_registry as issues
    if not isinstance(value, dict):
        raise ValueError('反馈必须指向一个议题或一条证据。')
    known = {row['id'] for row in issues.read_registry(vault)['issues']}
    # 路径 1：洞察窗口里点议题或证据卡上的“有问题”。
    if value.get('kind') == 'issue':
        if value.get('id') not in known:
            raise ValueError('议题不存在：' + str(value.get('id')))
        return dict(kind='issue', id=value['id'])
    if value.get('kind') == 'instance':
        session_id, instance_id, issue = value.get('session_id'), value.get('instance_id'), value.get('issue')
        if not isinstance(session_id, str) or not isinstance(instance_id, str):
            raise ValueError('证据反馈需要场次和实例编号。')
        if issue is not None and issue not in known:
            raise ValueError('议题不存在：' + str(issue))
        target = dict(kind='instance', session_id=session_id, instance_id=instance_id)
        if issue is not None:
            target['issue'] = issue
        return target
    raise ValueError('反馈对象必须是议题或证据。')


def _find(data, ident):
    item = next((item for item in data['items'] if item['id'] == ident), None)
    if item is None:
        raise ValueError('没有这条反馈：' + str(ident))
    return item


def add_feedback(vault, target, text):
    with metadata_lock(vault):
        data = read_feedback(vault)
        item = dict(id=uuid.uuid4().hex[:12], created=datetime.now().astimezone().isoformat(timespec='seconds'),
                    target=_target(vault, target), text=_text(text, '反馈'), status='open')
        data['items'].append(item)
        protocol._write(vault, FILE, data)
        return item


def edit_feedback(vault, ident, text):
    with metadata_lock(vault):
        data = read_feedback(vault)
        item = _find(data, ident)
        item['text'] = _text(text, '反馈')
        protocol._write(vault, FILE, data)
        return item


def remove_feedback(vault, ident):
    with metadata_lock(vault):
        data = read_feedback(vault)
        _find(data, ident)
        data['items'] = [item for item in data['items'] if item['id'] != ident]
        protocol._write(vault, FILE, data)
        return dict(id=ident, removed=1)


def resolve_feedback(vault, ident, note):
    with metadata_lock(vault):
        data = read_feedback(vault)
        item = _find(data, ident)
        # 路径 3：跨场次 agent 按反馈调整后写明改了什么，用户在“反馈”页看到处理结果。
        item.update(status='resolved', resolution=_text(note, '处理说明'),
                    resolved=datetime.now().astimezone().isoformat(timespec='seconds'))
        protocol._write(vault, FILE, data)
        return item


def list_feedback(vault, open_only=False):
    data = read_feedback(vault)
    if open_only:
        data['items'] = [item for item in data['items'] if item['status'] == 'open']
    return data
