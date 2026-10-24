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


if __name__ == '__main__':
    unittest.main()
