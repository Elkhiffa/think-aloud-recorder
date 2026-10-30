import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock

from desk_runtime import DeskAPI


class DeskOpenReviewTests(unittest.TestCase):
    def desk(self):
        desk = object.__new__(DeskAPI)
        desk._service = MagicMock()
        desk._service.review_at.return_value = {'ok': True, 'data': {'ready': True}}
        desk._insight = MagicMock()
        return desk

    def test_desk_rows_open_review_on_their_tab(self):
        """触发路径：资料库详情里点问题（进「问题」）或体验事件（进「体验事件」并展开）；洞察卡片仍只带时间。"""
        desk = self.desk()
        self.assertTrue(desk.open_review('s1', 30.5, 'events', 'e2')['ok'])
        desk._service.review_at.assert_called_once_with('s1', 30.5, dict(tab='events', event='e2'))
        desk.open_review('s1', 12, 'problems', '')
        self.assertEqual(desk._service.review_at.call_args.args[2], dict(tab='problems', event=''))
        desk.open_review('s1', 5)
        desk._insight.open_review.assert_called_once_with('s1', 5)

    def test_invalid_tab_or_time_never_opens_a_window(self):
        desk = self.desk()
        for args in (('s1', 1, 'inputs', ''), ('s1', 1, 'events', None), ('s1', -1, 'events', 'e1'),
                     ('s1', float('nan'), 'problems', ''), ('s1', '3', 'problems', ''), ('s1', 1, 'events', 'x' * 201)):
            self.assertFalse(desk.open_review(*args)['ok'], args)
        desk._service.review_at.assert_not_called()


class DeskInsightLinkTests(unittest.TestCase):
    def desk(self, folder):
        desk = object.__new__(DeskAPI)
        desk._service = MagicMock()
        desk.vault, desk._root = Path(folder), Path(folder)
        return desk

    def test_a_judgment_links_only_to_issues_that_still_cite_this_result(self):
        """触发路径：场次库详情读取一场的整理结果，每条判断旁边列出洞察里仍然引用它的议题。"""
        with tempfile.TemporaryDirectory() as folder:
            vault = Path(folder)
            issue = lambda ident, title: dict(id=ident, title=title, status='confirmed', description='')
            (vault / 'issues.json').write_text(json.dumps(dict(version=1, issues=[issue('TA-01', '目标明确仍有摩擦'), issue('TA-02', '退层')])), encoding='utf-8')
            link = lambda issue_id, instance, digest='d1', session='s1', role='support': dict(
                issue=issue_id, session_id=session, instance_id=instance, result_sha256=digest, role=role)
            (vault / 'issue-links.json').write_text(json.dumps(dict(version=1, links=[
                link('TA-01', 'i1'), link('TA-02', 'i1', role='counter'), link('TA-01', 'i2', digest='old'),
                link('TA-01', 'i3', session='s2'), link('TA-09', 'i1')])), encoding='utf-8')
            result = dict(session_id='s1', instances=[dict(id='i1'), dict(id='i2')])
            self.assertEqual(self.desk(folder)._instance_issues(result, 'd1'), {'i1': [
                dict(id='TA-01', title='目标明确仍有摩擦', role='support'), dict(id='TA-02', title='退层', role='counter')]})

    def test_a_library_without_insight_work_shows_no_links(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.desk(folder)._instance_issues(dict(session_id='s1', instances=[dict(id='i1')]), 'd1'), {})

    def test_the_link_opens_insight_through_the_service(self):
        """触发路径：场次库里点判断上的「洞察：…」链接。"""
        with tempfile.TemporaryDirectory() as folder:
            desk = self.desk(folder)
            desk.show_in_insight('s1', 'i1', 'TA-01')
            desk._service.show_in_insight.assert_called_once_with('s1', 'i1', 'TA-01')
            self.assertEqual(desk.take_focus(), {'ok': True, 'data': None})
            desk.focus = ('s1', 'i1', 'TA-01')
            self.assertEqual(desk.take_focus(), {'ok': True, 'data': ['s1', 'i1', 'TA-01']})
            self.assertEqual(desk.take_focus()['data'], None, 'taken once')


class DeskLayoutTests(unittest.TestCase):
    def test_column_split_is_kept_per_window_and_rejects_bad_values(self):
        """触发路径：拖动场次库或洞察窗口的分隔条，松手后保存；下次打开读取。"""
        with tempfile.TemporaryDirectory() as folder:
            desk = object.__new__(DeskAPI)
            desk._root = Path(folder)
            self.assertEqual(desk.get_layout(), {'ok': True, 'data': {}})
            self.assertTrue(desk.save_layout('sessions', .6)['ok'])
            self.assertTrue(desk.save_layout('insight', .45)['ok'])
            for key, ratio in (('review', .5), ('sessions', 1.2), ('insight', float('nan')), ('sessions', '0.5'), ('sessions', True)):
                self.assertFalse(desk.save_layout(key, ratio)['ok'], (key, ratio))
            self.assertEqual(desk.get_layout()['data'], {'sessions': .6, 'insight': .45})
            (Path(folder) / 'state' / 'desk-layout.json').write_text('{"sessions": 3, "insight": 0.5}', encoding='utf-8')
            self.assertEqual(desk.get_layout()['data'], {'insight': .5})


if __name__ == '__main__':
    unittest.main()
