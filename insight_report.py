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
# 报告里紧跟实例引用的“原话”，要和该实例的转写原文一致；附录“转写修正”表（| 原文 | 改成 | 依据 | 引用 |）登记过的改字算一致。
QUOTE = re.compile(r'“([^“”\n]{1,300})”')
QUOTE_REACH = 60
FIX_HEADING = re.compile(r'^#{1,4}[^\n]*转写修正[^\n]*$', re.MULTILINE)
NOT_WORD = re.compile(r'[\s，。！？、：；,.!?:;“”‘’「」…—\-·]')
# 记录者报缺陷的说法：明说 bug、归到程序本身、跑测常用的表现词。逐字稿里很少用于设计评价。
BUG_WORD = re.compile('bug|cocos|引擎|报错|闪退|重叠|裁切|适配|拉伸|歪了|偏了|偶现|不显示|没显示|超框|看不全|悬空|标错', re.IGNORECASE)


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


def _read(vault, name):
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
    return dict(name=Path(name).name, text=text, citations=rows), sessions


def read_report(vault, name):
    """Report text plus every citation resolved against the current vault."""
    return _read(vault, name)[0]


def _corrections(text):
    """附录“转写修正”表里登记的（原文, 改成）。表从标题下开始，到下一个标题为止。"""
    heading = FIX_HEADING.search(text)
    rows = []
    for line in text[heading.end():].splitlines() if heading else []:
        line = line.strip()
        if line.startswith('#'):
            break
        cells = [cell.strip() for cell in line.strip('|').split('|')] if line.startswith('|') else []
        if len(cells) >= 2 and cells[0] and cells[0] != '原文' and not set(cells[0]) <= set('-: '):
            rows.append((cells[0], cells[1]))
    return rows


def _said_text(sessions, row):
    """The transcript wording and, where the user confirmed transcript corrections, the corrected wording."""
    result = sessions[row['session_id']][3]
    instance = next(item for item in result.get('instances', []) if item['id'] == row['instance_id'])
    return (''.join(said.get('text') or '' for said in instance['said']),
            ''.join(said.get('corrected_text') or said.get('text') or '' for said in instance['said']))


def _quote_matches(quote, said, fixes):
    # 路径 1：引号可以用省略号节选；标点和空白不比，只比字。用户确认过的转写修正（资料库 transcript-corrections.json）
    # 和附录里登记的改字都算一致。
    raw, confirmed = said
    parts = [NOT_WORD.sub('', part) for part in re.split(r'…+|\.{3,}', quote)]
    parts = [part for part in parts if part]
    fixed = raw
    for original, corrected in fixes:
        fixed = fixed.replace(original, corrected)
    return bool(parts) and any(all(part in NOT_WORD.sub('', text) for part in parts) for text in (raw, confirmed, fixed))


def _cited_after(text, end, rows):
    """引号后面同一行、隔着别的引号也算，最近的一串连写实例引用。"""
    gap = ''
    for row in rows:
        if row['start'] < end or row['kind'] != 'instance':
            continue
        gap = QUOTE.sub('', text[end:row['start']])
        if '\n' in text[end:row['start']] or len(gap) > QUOTE_REACH:
            return []
        group, stop = [], row['start']
        for item in rows:
            if item['kind'] == 'instance' and item['start'] >= stop and len(text[stop:item['start']].strip(' 、，')) == 0:
                group.append(item)
                stop = item['end']
        return [item for item in group if item['resolved']]
    return []


def _unverified_quotes(text, rows, sessions):
    """实例引用前面的“原话”（连写的几段都算）里，和转写原文对不上、也没在转写修正表里登记的。"""
    fixes = _corrections(text)
    checked, problems = 0, []
    for match in QUOTE.finditer(text):
        cited = _cited_after(text, match.end(), rows)
        if not cited:
            continue
        checked += 1
        if not any(_quote_matches(match.group(1), _said_text(sessions, row), fixes) for row in cited):
            problems.append(dict(quote=match.group(1)[:60], label=cited[0]['label'],
                                 session_id=cited[0]['session_id'], instance_id=cited[0]['instance_id']))
    return checked, problems


def validate_report(vault, name):
    report, sessions = _read(vault, name)
    unresolved = [{key: row[key] for key in ('label', 'kind', 'issue', 'session_id', 'instance_id') if key in row}
                  for row in report['citations'] if not row['resolved']]
    checked, quotes = _unverified_quotes(report['text'], report['citations'], sessions)
    # 路径 2：#后写的议题要真挂着这条证据，否则洞察窗口会退到这条证据的任意一张卡片。
    linked = {(link['issue'], link['session_id'], link['instance_id'])
              for link in issues.read_links(vault)['links'] if issues._active(link, sessions)}
    linked |= {(tag, sid, item['id']) for sid, found in sessions.items()
               for item in found[3].get('instances', []) for tag in item.get('issue_tags', [])}
    anchors = [dict(label=row['label'], issue=row['issue'], session_id=row['session_id'],
                    instance_id=row['instance_id'])
               for row in report['citations'] if row['kind'] == 'instance' and row['resolved'] and row['issue']
               and (row['issue'], row['session_id'], row['instance_id']) not in linked]
    return dict(name=report['name'], citations=len(report['citations']), unresolved=unresolved,
                quotes_checked=checked, quotes_unverified=quotes, anchors_unlinked=anchors)


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
