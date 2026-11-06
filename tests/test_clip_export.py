"""clip: a recording clip with the operation record, for problems a screenshot cannot show (skill think-aloud-export)."""
import unittest
from unittest.mock import patch

import agent_protocol as agent
from clip_export import CLIP_FOLDER, build_clips, chip_strength, clip_path, fixed_cell, input_channel, make_clip, operation_tracks
from insight_runtime import InsightAPI
from issue_registry import query_instances
from tests import test_judgment_instances as judgment


def stick(start, end, direction, value, code='LeftStick'):
    return dict(start=start, end=end, device='xbox', code=code, label=code, kind='axis', direction=direction, value=value)


def press(start, end, code='A', device='xbox'):
    return dict(start=start, end=end, device=device, code=code, label=code, kind='button')


class ClipExportTests(unittest.TestCase):
    def test_controls_fall_into_the_review_timeline_columns(self):
        """触发路径：同一个操作在回看时间轴和动图里要出现在同一类位置，看过回看页的人不用重新认。"""
        self.assertEqual(input_channel(stick(0, 1, '→', 1)), 'direction')
        self.assertEqual(input_channel(press(0, 1, 'KeyW', 'keyboard')), 'direction')
        self.assertEqual(input_channel(stick(0, 1, '→', 1, 'RightStick')), 'pointing')
        self.assertEqual(input_channel(dict(start=0, end=1, device='mouse', code='MouseMove', kind='motion')), 'pointing')
        self.assertEqual(input_channel(press(0, 1, 'DpadUp')), 'dpad')
        self.assertEqual(input_channel(press(0, 1, 'A')), 'keys')
        self.assertEqual(input_channel(press(0, 1, 'W')), 'keys')  # Only a keyboard's W moves; a controller has no W.

    def test_high_frequency_sticks_never_add_to_the_key_row(self):
        """触发路径：走焦问题里摇杆一秒几十条采样 → 只占自己那一格，按键行只留语义集中的按键。"""
        rows = [stick(10 + i / 30, 10 + (i + 1) / 30, '→', .9) for i in range(30)] + [press(10.5, 10.6)]
        tracks = operation_tracks(rows, 9, 12)
        self.assertEqual(len(tracks['direction']), 1)
        self.assertEqual([chip['text'] for chip in tracks['keys']], ['A'])

    def test_a_cell_shows_the_current_direction_not_the_way_back_to_centre(self):
        """触发路径：向右推再松开 → 回中时会经过弱的反方向采样，格子要一直显示“→”，松开后淡出。"""
        rows = [stick(10, 10.05, '→', .4), stick(10.05, 10.1, '→', .9), stick(10.1, 10.15, '←', .2)]
        flicks = operation_tracks(rows, 9, 11)['direction']
        self.assertEqual(fixed_cell(flicks, 10.12), ('→', 1))
        direction, strength = fixed_cell(flicks, 11)
        self.assertEqual(direction, '→')
        self.assertLess(strength, 1)
        self.assertIsNone(fixed_cell(flicks, 13))
        self.assertIsNone(fixed_cell(flicks, 9))

    def test_turning_the_stick_changes_the_same_cell(self):
        """触发路径：推着摇杆从右转到下 → 同一格换方向，不新增一格。"""
        rows = [stick(10, 10.5, '→', .9), stick(10.5, 11, '↓', .9)]
        flicks = operation_tracks(rows, 9, 12)['direction']
        self.assertEqual(len(flicks), 1)
        self.assertEqual(fixed_cell(flicks, 10.2)[0], '→')
        self.assertEqual(fixed_cell(flicks, 10.7)[0], '↓')

    def test_wasd_held_together_shows_a_diagonal(self):
        """触发路径：键鼠场次按住 W 和 D 走路 → 方向格显示“↗”，和回看页把两键合成一个方向一致。"""
        rows = [press(10, 11, 'KeyW', 'keyboard'), press(10.2, 11, 'KeyD', 'keyboard')]
        flicks = operation_tracks(rows, 9, 12)['direction']
        self.assertEqual(fixed_cell(flicks, 10.5)[0], '↗')

    def test_drift_stays_out_of_its_cell(self):
        """触发路径：摇杆轻微漂移 → 不算操作，方向格保持空闲。"""
        self.assertEqual(operation_tracks([stick(10, 10.1, '↓', .1, 'RightStick')], 9, 11)['pointing'], [])

    def test_keys_are_in_order_and_outside_the_clip_are_left_out(self):
        """触发路径：片段从第 10 秒开始，先按 B 再按 A → 按键依序排列，片段之前按的不出现。"""
        rows = [press(5, 5.1, 'X'), press(11, 11.1, 'A'), press(10.5, 10.6, 'B')]
        self.assertEqual([chip['text'] for chip in operation_tracks(rows, 10, 12)['keys']], ['B', 'A'])

    def test_repeated_presses_stay_separate(self):
        """触发路径：连按十次确认才看到反馈 → 要看得出按了很多次，不能并成一个长按。"""
        rows = [press(10 + i, 10.1 + i) for i in range(3)]
        self.assertEqual(len(operation_tracks(rows, 9, 14)['keys']), 3)

    def test_a_held_control_is_lit_then_times_out_like_the_review_page(self):
        """触发路径：看动图时要分清正在按和刚按过 → 按住时全亮，松开后两秒内淡出，和回看页一致。"""
        chip = dict(start=10, end=11)
        self.assertEqual(chip_strength(chip, 9), 0)
        self.assertEqual(chip_strength(chip, 10.5), 1)
        self.assertAlmostEqual(chip_strength(chip, 12), .35)
        self.assertEqual(chip_strength(chip, 13), 0)

    def test_length_and_width_are_checked_before_touching_the_session(self):
        """触发路径：agent 想把一整段流程都截进去 → 明确拒绝并说明只截这次操作和结果，动图太长没人看。"""
        with self.assertRaisesRegex(ValueError, '2–30'):
            make_clip('不存在的场次', 0, 60, 'x.gif')
        with self.assertRaisesRegex(ValueError, '480'):
            make_clip('不存在的场次', 0, 5, 'x.gif', width=200)


class StoredClipTests(unittest.TestCase):
    setUp = judgment.JudgmentInstanceTests.setUp
    candidate = judgment.JudgmentInstanceTests.candidate

    def marked(self, *spans):
        candidate = self.candidate()
        candidate['instances'][0]['evidence'] = [dict(kind='video', start=start, end=end, clip=True, observation='按下后焦点跳走。') for start, end in spans]
        return candidate

    def submit(self, candidate):
        job = agent.claim(self.folder, 'synthetic-v2-worker')
        return agent.submit(self.folder, job['token'], candidate)

    def test_a_marked_span_survives_validation_and_old_results_are_untouched(self):
        """触发路径：agent 给走焦问题的画面证据标 clip → 校验后保留且幂等；旧结果没有这个字段，校验结果不变。"""
        validated = agent.validate_result(self.folder, self.marked((2, 6)))
        self.assertEqual(validated['instances'][0]['evidence'][0]['clip'], True)
        self.assertEqual(agent.validate_result(self.folder, validated), validated)
        self.assertEqual(agent.clip_spans(validated), [(2, 6)])
        self.assertNotIn('clip', agent.validate_result(self.folder, self.candidate())['instances'][0]['evidence'][0])

    def test_a_clip_must_be_short_and_few(self):
        """触发路径：agent 想把一整段流程或很多段都做成动图 → 明确拒绝，动图只放这次操作和它的结果。"""
        for spans, message in (([(1, 1.5)], '2–30'), ([(2, 6), (3, 7), (4, 8)], '最多 2 段')):
            with self.assertRaisesRegex(ValueError, message):
                agent.validate_result(self.folder, self.marked(*spans))
        candidate = self.marked((2, 6))
        candidate['instances'][0]['evidence'][0]['clip'] = 'yes'
        with self.assertRaisesRegex(ValueError, 'clip'):
            agent.validate_result(self.folder, candidate)

    def test_submit_makes_the_clips_and_keeps_the_material_revision(self):
        """触发路径：提交带动图标记的结果 → 场次文件夹里有动图，回执写明数量，素材版本不变、结果继续有效。"""
        def render(folder, start, end, output, *args):
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(b'GIF')
        with patch('clip_export._render', render):
            summary = self.submit(self.marked((2, 6)))
        self.assertEqual((summary['clips']['made'], summary['clips']['failed']), (1, []))
        self.assertTrue(clip_path(self.folder, 2, 6).is_file())
        self.assertEqual(agent._ready(self.folder)[2], self.manifest['revision'])
        self.assertEqual(agent.preprocessing_status(self.folder)['state'], 'complete')

    def test_a_result_without_clips_gets_no_folder(self):
        """触发路径：一场没有依赖操作的问题 → 提交不碰录像解码，也不多建文件夹。"""
        summary = self.submit(self.candidate())
        self.assertNotIn('clips', summary)
        self.assertFalse((self.folder / CLIP_FOLDER).exists())

    def test_a_failed_clip_does_not_undo_the_submission(self):
        """触发路径：录像这一段解码失败 → 判断已提交，回执列出失败的时间段，之后可用 clips-build 补。"""
        def render(*args):
            raise ValueError('解码失败')
        with patch('clip_export._render', render):
            summary = self.submit(self.marked((2, 6)))
        self.assertEqual(summary['state'], 'complete')
        self.assertEqual(summary['clips']['failed'], [dict(start=2, end=6, error='解码失败')])

    def test_the_insight_bridge_reads_a_stored_clip_and_remakes_a_missing_one(self):
        """触发路径：洞察里点开带动图的论据 → 读场次里存好的文件；只复制了部分文件的场次，现做一个再显示。"""
        api = InsightAPI(self.vault, self.vault / 'app', None)
        def render(folder, start, end, output, *args):
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(b'GIF')
        with patch('clip_export._render', render) as _:
            made = api.clip('fixture', 2, 6)
        self.assertEqual(made, dict(ok=True, data='data:image/gif;base64,R0lG'))
        with patch('clip_export._render', side_effect=AssertionError('stored file is reused')):
            self.assertEqual(api.clip('fixture', 2, 6)['data'], made['data'])
        for start, end in ((float('nan'), 6), (2, 100), (6, 2)):
            self.assertFalse(api.clip('fixture', start, end)['ok'])

    def test_the_cited_clips_reach_the_views(self):
        """触发路径：提交后在洞察和场次库看这条判断 → 两边都拿到时间段，没有动图的判断不多这个字段。"""
        with patch('clip_export._render', lambda *args: None):
            self.submit(self.marked((2, 6)))
        rows = query_instances(self.vault)
        self.assertEqual(rows[0]['clips'], [dict(start=2, end=6)])
        result = agent.validate_result(self.folder, self.candidate())
        self.assertEqual(agent.instance_clips(result['instances'][0]), [])

    def test_rebuild_reuses_clears_only_its_own_stale_clips(self):
        """触发路径：重新整理后时间段变了 → 同一段复用，不再引用的动图清掉，文件夹里别的文件一律不动。"""
        def render(folder, start, end, output, *args):
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(b'GIF')
        stored = self.folder / CLIP_FOLDER
        stored.mkdir()
        clip_path(self.folder, 2, 6).write_bytes(b'GIF')
        clip_path(self.folder, 8, 12).write_bytes(b'GIF')
        (stored / '我的备注.gif').write_bytes(b'GIF')
        result = agent.validate_result(self.folder, self.marked((2, 6), (3, 7)))
        with patch('clip_export._render', render):
            summary = build_clips(self.folder, result)
        self.assertEqual((summary['made'], summary['reused'], summary['removed']), (1, 1, 1))
        self.assertFalse(clip_path(self.folder, 8, 12).exists())
        self.assertTrue((stored / '我的备注.gif').exists())


if __name__ == '__main__':
    unittest.main()
