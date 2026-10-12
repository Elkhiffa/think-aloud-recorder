"""Insight window bridge: one vault's reports and evidence, read-only except confirmed catalog names."""
import base64
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import threading

import game_catalog
import insight_report as insight


THUMB_WIDTH = 480
LARGE_WIDTH = 1600


class InsightAPI:
    def __init__(self, vault, root, open_review):
        self._vault = Path(vault).resolve()
        self._cache = Path(root) / 'state' / 'insight-thumbs'
        self._open_review = open_review
        self._ready = threading.Event()
        self._error = None

    @staticmethod
    def _call(work):
        try:
            return {'ok': True, 'data': work()}
        except Exception as error:
            return {'ok': False, 'error': str(error)[:500]}

    def ready(self, error=None):
        self._error = str(error)[:500] if error else None
        self._ready.set()
        return {'ok': True}

    def _sessions(self):
        rows = {}
        for path in sorted((self._vault / '场次').glob('*/session.json')):
            meta = json.loads(path.read_text(encoding='utf-8-sig'))
            rows[meta['id']] = (path.parent, meta)
        return rows

    def get_overview(self):
        def work():
            evidence = insight.evidence(self._vault)
            games = {meta.get('game') for _, meta in self._sessions().values() if meta.get('game')}
            return dict(vault=self._vault.name, reports=insight.list_reports(self._vault),
                        proposed=self._proposed(), games=sorted(games), **evidence)
        return self._call(work)

    def read_report(self, name):
        return self._call(lambda: insight.read_report(self._vault, name))

    def _proposed(self):
        sessions = self._sessions()
        groups = insight.proposed_screens(self._vault)
        for group in groups:
            group['games'] = sorted({sessions[row['session_id']][1].get('game', '') for row in group['instances']})
        return groups

    def list_screens(self, game):
        def work():
            if not game_catalog.catalog_path(self._vault, game).is_file():
                return []
            return [dict(id=row['id'], name=row['name'], aliases=row.get('aliases', []))
                    for row in game_catalog.load_catalog(self._vault, game)['screens']]
        return self._call(work)

    def confirm_proposed(self, request):
        def work():
            # Path 1: the user confirms one proposed name; results stay untouched.
            if not isinstance(request, dict):
                raise ValueError('确认请求无效。')
            result = game_catalog.confirm_proposed(
                self._vault, request.get('game'), request.get('proposed'), request.get('new_id') or None,
                request.get('name') or None, request.get('into') or None)
            return dict(result=result, proposed=self._proposed())
        return self._call(work)

    def update_issue(self, request):
        def work():
            # Path 1: the user confirms or retitles a candidate issue while reading its evidence.
            import issue_registry
            if not isinstance(request, dict):
                raise ValueError('议题请求无效。')
            return issue_registry.update_issue(self._vault, request.get('id'), request.get('title'), None,
                                               request.get('status'))
        return self._call(work)

    def dismiss_issue(self, ident):
        def work():
            import issue_registry
            return issue_registry.dismiss_issue(self._vault, ident)
        return self._call(work)

    def merge_issue(self, from_id, into_id):
        def work():
            import issue_registry
            return issue_registry.merge_issues(self._vault, from_id, into_id)
        return self._call(work)

    def thumbnail(self, session_id, at, large=False):
        def work():
            if type(at) not in (int, float) or not math.isfinite(at) or at < 0:
                raise ValueError('画面时间无效。')
            folder, _ = self._sessions()[session_id]
            video = folder / '录像.mp4'
            info = video.stat()
            width = LARGE_WIDTH if large else THUMB_WIDTH
            key = hashlib.sha256(json.dumps([session_id, round(at, 2), info.st_size, info.st_mtime_ns,
                                             width]).encode('utf-8')).hexdigest()
            path = self._cache / (key + '.jpg')
            if not path.is_file():
                import visual_nodes
                with closing(visual_nodes._decode(video, at, at, {})) as decoded:
                    picture = next(decoded, (None, None))[1]
                if picture is None:
                    raise ValueError('该时刻没有可用画面。')
                self._cache.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix('.tmp')
                temp.write_bytes(visual_nodes._jpeg(picture, width=width))
                temp.replace(path)
            return 'data:image/jpeg;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')
        return self._call(work)

    def open_review(self, session_id, at):
        # Path 1: each evidence time opens the session's own review window at that moment.
        if type(at) not in (int, float) or not math.isfinite(at) or at < 0:
            return {'ok': False, 'error': '回看定位时间无效。'}
        return self._open_review(session_id, at)
