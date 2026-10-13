"""Vault insight data: agent-written reports, their citations, issue evidence and review queues."""
import json
from pathlib import Path
import re

import agent_protocol as protocol
import issue_registry as issues


REPORTS = '洞察'
MAX_REPORT = 1024 * 1024
# 报告引用：[0924 i72](i:<场次 id>/i72#TA-04.5) 指向实例，可选写明出自哪个子议题；[TA-04.5](issue:TA-04.5) 指向议题。
CITATION = re.compile(r'\[([^\]\n]{1,80})\]\((i|issue):([^)\s#]+)(?:#([^)\s]+))?\)')
# 记录者报缺陷的说法：明说 bug、归到程序本身、跑测常用的表现词。逐字稿里很少用于设计评价。
BUG_WORD = re.compile('bug|cocos|引擎|报错|闪退|重叠|裁切|适配|歪了|偏了|偶现|不显示|没显示', re.IGNORECASE)


def _report_path(vault, name):
    # 路径 1/2：洞察窗口和命令行只读取报告目录下的直接 .md 文件。
    folder = (Path(vault).resolve() / REPORTS)
    path = (folder / str(name)).resolve()
    if path.parent != folder or path.suffix.lower() != '.md' or not path.is_file():
        raise ValueError('报告不存在：' + str(name))
    if path.stat().st_size > MAX_REPORT:
        raise ValueError('报告超过 1 MB。')
    return path


def list_reports(vault):
    folder = Path(vault).resolve() / REPORTS
    rows = [dict(name=path.name, modified=path.stat().st_mtime, bytes=path.stat().st_size)
            for path in folder.glob('*.md') if path.is_file()] if folder.is_dir() else []
    return sorted(rows, key=lambda row: -row['modified'])


def citations(text):
    rows = []
    for match in CITATION.finditer(text):
        label, kind, target, issue = match.groups()
        row = dict(label=label, start=match.start(), end=match.end())
        if kind == 'issue':
            row.update(kind='issue', issue=target)
        else:
            session_id, _, instance_id = target.rpartition('/')
            row.update(kind='instance', session_id=session_id, instance_id=instance_id, issue=issue)
        rows.append(row)
    return rows


def read_report(vault, name):
    """Report text plus every citation resolved against the current vault."""
    text = _report_path(vault, name).read_text(encoding='utf-8-sig')
    known = {row['id'] for row in issues.read_registry(vault)['issues']}
    sessions = issues._complete_results(vault)
    rows = citations(text)
    for row in rows:
        if row['kind'] == 'issue':
            row['resolved'] = row['issue'] in known
        else:
            found = sessions.get(row['session_id'])
            row['resolved'] = (found is not None and row['instance_id'] in found[1]
                               and (row['issue'] is None or row['issue'] in known))
    return dict(name=Path(name).name, text=text, citations=rows)


def validate_report(vault, name):
    report = read_report(vault, name)
    unresolved = [{key: row[key] for key in ('label', 'kind', 'issue', 'session_id', 'instance_id') if key in row}
                  for row in report['citations'] if not row['resolved']]
    return dict(name=report['name'], citations=len(report['citations']), unresolved=unresolved)


def session_labels(session_ids):
    """Short labels: 0924, or 0924·1531 when the same day has several sessions."""
    days = {}
    for ident in session_ids:
        days.setdefault(ident[4:8], []).append(ident)
    return {ident: day if len(group) == 1 else f'{day}·{ident[9:13]}'
            for day, group in days.items() for ident in group}


def bug_hits(vault):
    """Recorder utterances naming a bug or the implementation, matched to instances by transcript reference."""
    from speaker_roles import speaker_payload, valid_speaker
    vault = Path(vault).resolve()
    sessions = issues._complete_results(vault)
    bug_links = {(link['session_id'], link['instance_id']) for link in issues.read_links(vault)['links']
                 if link['issue'].partition('.')[0] == issues.BUG and issues._active(link, sessions)}
    rows = []
    for path in sorted((vault / '场次').glob('*/session.json')):
        folder = path.parent
        if not (folder / '录像.whisper.json').is_file():
            continue
        meta = json.loads(path.read_text(encoding='utf-8-sig'))
        segments = protocol._transcript_rows(folder)
        # 路径 1：多人场次只认记录者本人的原话；没有说话人标注时整段都是记录者。
        recorder = speaker_payload(folder, meta, segments).get('selected_id')
        result = sessions.get(meta['id'], (None, set(), meta, {}))[3]
        quoted = {}
        for instance in result.get('instances', []):
            for said in instance['said']:
                quoted.setdefault(said['ref'], []).append(instance)
        for index, segment in enumerate(segments):
            text = segment.get('text') or ''
            if not BUG_WORD.search(text):
                continue
            speaker = segment.get('speaker_id')
            if recorder is not None and valid_speaker(speaker) and speaker != recorder:
                continue
            ref = f't{index + 1:06d}'
            matches = quoted.get(ref, [])
            linked = [row['id'] for row in matches if issues.BUG in row['issue_tags']
                      or any(tag.partition('.')[0] == issues.BUG for tag in row['issue_tags'])
                      or (meta['id'], row['id']) in bug_links]
            rows.append(dict(session_id=meta['id'], ref=ref, start=segment['start'], end=segment['end'],
                             text=text, instances=[row['id'] for row in matches], bug_instances=linked,
                             state='linked' if linked else 'instance' if matches else 'raw'))
    return rows


def evidence(vault):
    """Issue -> sub-issue -> support / counter instance rows for the insight view."""
    registry = issues.read_registry(vault)['issues']
    rows = issues.query_instances(vault)
    by_issue = {row['id']: dict(row, support=[], counter=[], children=[]) for row in registry}
    for row in rows:
        for link in row['issue_links']:
            target = by_issue.get(link['issue'])
            if target is not None:
                target['support' if link['role'] == 'support' else 'counter'].append(
                    dict(session_id=row['session_id'], instance_id=row['instance_id'], reason=link['reason']))
        linked = {link['issue'] for link in row['issue_links']}
        # 单场次整理时直接写在实例上的标签（目前只有 BUG）没有对应理由，也算支持证据。
        for tag in row['issue_tags']:
            if tag not in linked and tag in by_issue:
                by_issue[tag]['support'].append(dict(session_id=row['session_id'], instance_id=row['instance_id'],
                                                     reason=''))
    tree = []
    for row in registry:
        node = by_issue[row['id']]
        if row.get('parent'):
            by_issue[row['parent']]['children'].append(node)
        else:
            tree.append(node)
    instances = {(row['session_id'], row['instance_id']): row for row in rows}
    hits = [row for row in bug_hits(vault) if row['state'] != 'linked']
    return dict(issues=tree, instances=list(instances.values()), bug_unorganized=hits,
                session_labels=session_labels(sorted({row['session_id'] for row in rows}
                                                     | {row['session_id'] for row in hits})))


def proposed_screens(vault):
    """Proposed screen names not yet in the catalog, grouped by name with a loose family key."""
    groups = {}
    for row in issues.query_instances(vault):
        if not row.get('screen_proposed') or row['catalog_screen'] is not None:
            continue
        group = groups.setdefault(row['screen'], dict(name=row['screen'], instances=[]))
        group['instances'].append(dict(session_id=row['session_id'], instance_id=row['instance_id'],
                                       refers_start=row['refers_start'], said_start=row['said_start'],
                                       frame_at=row['frame_at'],
                                       statement=row['statement'], route=row.get('route', [])))
    for group in groups.values():
        # 名称相近（最后一级相同，去掉括号注释后）的提议放在一起，便于发现同一界面的不同写法。
        group['family'] = re.sub(r'[（(].*?[）)]', '', group['name'].rpartition('/')[2]).strip()
    return sorted(groups.values(), key=lambda group: (group['family'], group['name']))
