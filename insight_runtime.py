"""Insight window bridge: one vault's reports and evidence, read-only except the user's feedback."""
import base64
from contextlib import closing
import hashlib
import json
import math
from pathlib import Path
import threading

import evidence_tags
import insight_report as insight
import user_feedback


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
            tags = evidence_tags.read_tags(self._vault)
            return dict(vault=self._vault.name, reports=insight.list_reports(self._vault),
                        feedback=user_feedback.list_feedback(self._vault)['items'],
                        tag_groups=tags['groups'], tags=tags['tags'],
                        instance_tags=evidence_tags.instance_tags(self._vault, evidence['instances'], tags), **evidence)
        return self._call(work)

    def read_report(self, name):
        return self._call(lambda: insight.read_report(self._vault, name))

    def add_feedback(self, request):
        def work():
            # Path 1: the user flags an issue or an evidence card and says how to adjust it.
            if not isinstance(request, dict):
                raise ValueError('反馈请求无效。')
            user_feedback.add_feedback(self._vault, request.get('target'), request.get('text'))
            return user_feedback.list_feedback(self._vault)['items']
        return self._call(work)

    def set_cover(self, tag_id, session_id, at):
        def work():
            # Path 1: right-click an evidence card -> use its frame as this tag's cover.
            evidence_tags.set_cover(self._vault, tag_id, session_id, at)
            return evidence_tags.read_tags(self._vault)['tags']
        return self._call(work)

    def edit_feedback(self, ident, text):
        def work():
            user_feedback.edit_feedback(self._vault, ident, text)
            return user_feedback.list_feedback(self._vault)['items']
        return self._call(work)

    def remove_feedback(self, ident):
        def work():
            user_feedback.remove_feedback(self._vault, ident)
            return user_feedback.list_feedback(self._vault)['items']
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
