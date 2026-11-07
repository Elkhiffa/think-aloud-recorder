"""Rows for exporting sessions' judgments to a team spreadsheet (agent_cli export-rows; skill think-aloud-export).

Each judgment of a completed session becomes one flat row: what the table needs (screen path, description, bug or
not, the quote, when to take the screenshot) without the evidence and receipts of the result file. Reading is per
session, so version-acceptance sessions are included: they stay out of cross-session analysis only. Read-only.
"""
import json
from pathlib import Path

import agent_protocol as protocol
from issue_registry import screen_names
from session_metadata import session_title


def _quote(instance):
    # Path 1: the confirmed wording of a transcript correction is what the recorder means to have said.
    return ' … '.join(said.get('corrected_text') or said.get('text') or '' for said in instance.get('said') or []).strip()


def _frame_at(instance):
    """The moment to screenshot: the video evidence the agent checked, else the referred moment, else when it was said."""
    video = next((row['start'] for row in instance.get('evidence') or [] if row.get('kind') == 'video'), None)
    if video is not None:
        return video
    if instance['refers_to'].get('start') is not None:
        return instance['refers_to']['start']
    return min(said['start'] for said in instance['said'])


def export_rows(vault, sessions=None, all_sessions=False):
    vault = Path(vault).resolve()
    base = vault / '场次'
    if not base.is_dir():
        raise ValueError('资料库中没有“场次”目录。请传入资料库根目录。')
    wanted = set(sessions or [])
    if not wanted and not all_sessions:
        raise ValueError('请用 --session 指定场次编号（可重复），或用 --all 导出全部已整理的场次。')
    rows, summary, skipped, found, catalogs = [], [], [], set(), {}
    for file in sorted(base.glob('*/session.json')):
        folder = file.parent
        try:
            meta = json.loads(file.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError) as error:
            skipped.append(dict(folder=str(folder), reason=str(error)))
            continue
        ident = meta.get('id')
        if wanted and ident not in wanted:
            continue
        found.add(ident)
        if meta.get('test') and ident not in wanted:
            continue  # Synthetic fixtures are exported only when asked for by id.
        try:
            status = protocol.preprocessing_status(folder, meta, include_result=True)
        except (OSError, ValueError, TypeError) as error:
            skipped.append(dict(session_id=ident, reason=str(error)))
            continue
        result = status.get('result')
        if status.get('state') != 'complete' or not isinstance(result, dict) or 'instances' not in result:
            skipped.append(dict(session_id=ident, reason=status.get('label') or '这一场还没有整理结果。'))
            continue
        game = meta.get('game')
        if game not in catalogs:
            catalogs[game] = screen_names(vault, game)
        names = catalogs[game]
        events = {event['id']: event.get('title', '') for event in result.get('events', [])}
        activity = {}
        for row in status.get('activities') or []:
            for event_id in row['event_ids']:
                activity.setdefault(event_id, row['name'])
        bugs = status.get('bugs') or {}
        session = dict(session_id=ident, title=session_title(meta), created=meta.get('created'), folder=str(folder),
                       acceptance=meta.get('acceptance') is True, acceptance_target=meta.get('acceptance_target') or '')
        count = 0
        for instance in result['instances']:
            screen = names.get(instance['screen']) or instance['screen']
            bug = bugs.get(instance['id']) or instance.get('bug')
            clips = protocol.instance_clips(instance)
            if clips:
                from clip_export import clip_path
                clips = [dict(clip, path=str(clip_path(folder, clip['start'], clip['end']))) for clip in clips]
            rows.append(dict(session_id=ident, instance_id=instance['id'], kind=protocol.instance_type(instance),
                             problem=protocol.is_problem(instance) or bool(bug), bug=bug,
                             **{key: instance[key] for key in ('symptom', 'secondary_defect', 'evidence_source', 'valence', 'intensity', 'owner') if key in instance},
                             statement=instance['statement'], quote=_quote(instance),
                             screen=screen, screen_path=screen.split('/') if screen else [],
                             screen_context=instance.get('screen_context'), elements=instance.get('elements') or [],
                             said_start=min(said['start'] for said in instance['said']),
                             refers_start=instance['refers_to'].get('start'), refers_end=instance['refers_to'].get('end'),
                             frame_at=_frame_at(instance), **({'clips': clips} if clips else {}),
                             event_title=events.get(instance['event_id'], ''), activity=activity.get(instance['event_id'], '')))
            count += 1
        summary.append(dict(session, rows=count))
    for ident in sorted(wanted - found):
        skipped.append(dict(session_id=ident, reason='资料库里没有这一场。'))
    return dict(sessions=summary, rows=rows, skipped=skipped)
