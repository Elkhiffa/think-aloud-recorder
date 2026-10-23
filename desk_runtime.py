"""Bridge for the desk window (资料台): the 场次 tab and the 洞察 tab of the current game.

The insight half is the existing InsightAPI, bound to the game's library. The session half reads
the recorder's own session list and delegates every action back to DesktopService, so recording
locks, background jobs and close guards stay in one place. The desk follows the main window's
current game: `rebind` swaps the library without recreating the window.
"""
import json
from pathlib import Path

from insight_runtime import InsightAPI

PROBLEM_KINDS = ('confusion', 'obstacle', 'cost', 'negative')
DESK_METHODS = ('ready', 'get_overview', 'read_report', 'add_feedback', 'set_cover', 'edit_feedback', 'remove_feedback',
                'thumbnail', 'open_review', 'desk_state', 'session_detail', 'review_session', 'rename_session',
                'process_session', 'package_session', 'open_folder', 'open_raw', 'recover_cloud_task')


def _ok(data=None):
    return {'ok': True, 'data': data}


def _error(error):
    return {'ok': False, 'error': str(error)[:2000]}


class DeskAPI:
    def __init__(self, service, vault, root, initial_tab='sessions'):
        self._service = service
        self._root = Path(root)
        self.tab = initial_tab
        self.rebind(vault)

    def rebind(self, vault):
        self.vault = Path(vault).resolve()
        previous = getattr(self, '_insight', None)
        self._insight = InsightAPI(self.vault, self._root, self._service.review_at)
        if previous is not None and previous._ready.is_set():
            self._insight._ready.set()

    # ---- 洞察 tab: the existing insight bridge, always for the current library ----
    @property
    def _ready(self):
        return self._insight._ready

    @property
    def _error(self):
        return self._insight._error

    def ready(self, error=None):
        return self._insight.ready(error)

    def get_overview(self):
        return self._insight.get_overview()

    def read_report(self, name):
        return self._insight.read_report(name)

    def add_feedback(self, request):
        return self._insight.add_feedback(request)

    def set_cover(self, tag_id, session_id, at):
        return self._insight.set_cover(tag_id, session_id, at)

    def edit_feedback(self, ident, text):
        return self._insight.edit_feedback(ident, text)

    def remove_feedback(self, ident):
        return self._insight.remove_feedback(ident)

    def thumbnail(self, session_id, at, large=False):
        return self._insight.thumbnail(session_id, at, large)

    def open_review(self, session_id, at):
        return self._insight.open_review(session_id, at)

    # ---- 场次 tab ----
    def desk_state(self):
        """The same session rows as the main window, plus which tab to show and the game name."""
        state = self._service.get_state()
        if not state.get('ok'):
            return state
        data = state['data']
        presets = {row['id']: row['name'] for row in data.get('presets', [])}
        return _ok(dict(tab=self.tab, game=presets.get(data.get('active_preset_id')) or data['config'].get('game', ''),
                        sessions=data.get('sessions', []), background_jobs=data.get('background_jobs', []),
                        busy=bool(data.get('activity', {}).get('busy')), recording=data.get('activity', {}).get('kind') == 'recording',
                        insight=data.get('insight'), app_dir=data.get('app_dir')))

    def session_detail(self, ident):
        """Quotes grouped by problem kind, the activities, and which insights cite this session."""
        try:
            from agent_protocol import preprocessing_status
            import recorder
            session = self._service._session(ident)
            meta = recorder.read(session.path / 'session.json')
            status = preprocessing_status(session.path, meta, include_result=True)
            result = status.get('result') or {}
            quotes = {kind: [] for kind in PROBLEM_KINDS}
            for item in result.get('instances', []):
                if item.get('kind') in quotes:
                    said = (item.get('said') or [{}])[0]
                    quotes[item['kind']].append(dict(instance=item.get('id'), text=said.get('text', ''), at=said.get('start'),
                                                     statement=item.get('statement', ''), screen=item.get('screen') or '',
                                                     confidence=item.get('confidence')))
            events = [dict(title=row.get('title', ''), start=row.get('start'), end=row.get('end')) for row in result.get('events', [])]
            return _ok(dict(id=ident, state=status.get('state'), label=status.get('label', ''), kinds=status.get('kinds') or {},
                            quotes=quotes, events=events, insights=self._session_insights(meta.get('id', ident))))
        except Exception as error:
            return _error(error)

    def _session_insights(self, session_id):
        try:
            issues = json.loads((self.vault / 'issues.json').read_text(encoding='utf-8-sig'))['issues']
            links = json.loads((self.vault / 'issue-links.json').read_text(encoding='utf-8-sig'))['links']
        except (OSError, ValueError, KeyError, TypeError):
            return []
        rows = {row['id']: row for row in issues if isinstance(row, dict) and row.get('id')}

        def top(ident):
            seen = set()
            while rows.get(ident, {}).get('parent') and ident not in seen:
                seen.add(ident)
                ident = rows[ident]['parent']
            return ident
        counts = {}
        for link in links:
            if isinstance(link, dict) and link.get('session_id') == session_id and link.get('issue') in rows:
                key = top(link['issue'])
                counts[key] = counts.get(key, 0) + 1
        return [dict(id=key, title=rows[key].get('title', key), count=count)
                for key, count in sorted(counts.items(), key=lambda item: -item[1])]

    def review_session(self, ident):
        return self._service.open_review(ident)

    def rename_session(self, ident, name):
        return self._service.rename_session(ident, name)

    def process_session(self, ident):
        return self._service.process_session(ident)

    def package_session(self, ident):
        return self._service.package_session(ident)

    def open_folder(self, ident=None):
        return self._service.open_folder(ident)

    def open_raw(self, ident):
        return self._service.open_raw(ident)

    def recover_cloud_task(self, ident, task_id):
        return self._service.recover_cloud_task(ident, task_id)
