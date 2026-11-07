"""place_videos: operation clips go into a team table as file cards, one verified cell at a time."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'skills/think-aloud-export/scripts/place_videos.py'
spec = importlib.util.spec_from_file_location('place_videos', path)
place = importlib.util.module_from_spec(spec)
spec.loader.exec_module(place)


def card(row, col, name):
    return dict(row=row, col=col, cellType='attachment', value={'richText': [{'text': name, 'style': {'e': {'type': 'attachment', 'attachment': {'id': 'x', 'name': name, 'type': 6, 'size': 1}}}}]})


class PlaceVideosTests(unittest.TestCase):
    def test_names_stay_readable_when_the_cell_cuts_them(self):
        """触发路径：单元格不能换行，文件名按列宽截断 → 固定部分在前且不超过 10 字，编号被截也看得出是什么。"""
        self.assertEqual(place.video_name(3), '操作记录录屏03.mp4')
        self.assertLessEqual(len(place.video_name(3).removesuffix('.mp4')), 10)

    def test_numbers_follow_the_table_and_occupied_cells_are_left_alone(self):
        """触发路径：验收表只有一个截图列，视频放备注列，有一行备注已写了字 → 不覆盖，列出来；编号仍按表里的顺序。"""
        jobs = [dict(row=2, col=5, file='a.mp4'), dict(row=3, col=5, file='b.mp4'), dict(row=4, col=5, file='c.mp4')]
        ready, skipped, done = place.plan(jobs, [dict(row=3, col=5, value='备注文字'), dict(row=4, col=5, value='')])
        self.assertEqual([i['name'] for i in ready], ['操作记录录屏01.mp4', '操作记录录屏03.mp4'])
        self.assertEqual([i['name'] for i in skipped], ['操作记录录屏02.mp4'])
        self.assertEqual(done, [])

    def test_a_rerun_keeps_what_is_already_placed(self):
        """触发路径：放到一半接口出错，修好后重跑同一份清单 → 已放好的不重传，编号不变，只放剩下的。"""
        jobs = [dict(row=2, col=5, file='a.mp4'), dict(row=3, col=5, file='b.mp4')]
        ready, skipped, done = place.plan(jobs, [card(2, 5, '操作记录录屏01.mp4')])
        self.assertEqual(([i['name'] for i in done], [i['name'] for i in ready], skipped), (['操作记录录屏01.mp4'], ['操作记录录屏02.mp4'], []))

    def test_a_card_is_told_from_other_cells_by_its_name(self):
        """触发路径：每放一个就回读 → 只认这张文件卡片，文字和超链接单元格不算放上了。"""
        self.assertEqual(place.attachment_name(card(1, 1, '操作记录录屏01.mp4')), '操作记录录屏01.mp4')
        self.assertIsNone(place.attachment_name(dict(row=1, col=1, value='操作记录录屏01.mp4')))
        self.assertIsNone(place.attachment_name(None))

    def test_each_round_selects_the_cell_by_keyboard_and_only_opens_the_sheet_once(self):
        """触发路径：表很长、屏幕坐标不可靠 → 用 Ctrl+Home 加方向键选格；连放多个时不重复打开页面，也不碰会弹系统窗口的附件按钮。"""
        first = place.script('https://x', dict(row=2, col=1), r'D:\v\a.mp4', True)
        later = place.script('https://x', dict(row=2, col=1), r'D:\v\a.mp4', False)
        self.assertIn('i < 2', first)
        self.assertIn('Input.dispatchDragEvent', first)
        self.assertIn('page.goto', first)
        self.assertNotIn('page.goto', later)
        self.assertIn(r'D:\\v\\a.mp4', first)


if __name__ == '__main__':
    unittest.main()
