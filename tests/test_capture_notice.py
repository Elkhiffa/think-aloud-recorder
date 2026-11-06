"""Session-level notice for keyboard/mouse capture that cannot be confirmed."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import agent_protocol as agent
import recorder
from input_capture import (BLOCK_CHECK, ELEVATED_FOREGROUND, KEYBOARD_MOUSE_NOTICE, TRIGGERS_ONLY_NOTICE,
                           InputRecorder, recover_capture)
from review_runtime import input_payload


def row(device, code, start, end=None):
    return dict(id=f'{code}{start}', device=device, code=code, label=code, kind='button', start=start, end=end or start + .1)


class CaptureNoticeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def notice(self, **fields):
        data = dict(version=1, state='complete', duration=100, timebase='video_seconds', intervals=[], gaps=[])
        data.update(fields)
        (self.folder / 'input-events.json').write_text(json.dumps(data), encoding='utf-8')
        return input_payload(self.folder, dict(media=dict(duration=100))).get('capture_notice')

    def test_old_session_with_keyboard_mouse_only_in_background_shows_notice(self):
        """触发路径：用户 → 回看窗口 → 打开旧场次 → 键鼠事件全在游戏后台 → 空白会被当成玩家没操作"""
        self.assertEqual(self.notice(recording_scope='all', window_states=[
            dict(start=0, end=50, state='foreground'), dict(start=50, end=100, state='background')],
            intervals=[row('xbox', 'A', 10), row('mouse', 'MouseLeft', 70)]), KEYBOARD_MOUSE_NOTICE)

    def test_foreground_keyboard_mouse_far_from_a_switch_proves_capture(self):
        """触发路径：用户 → 回看窗口 → 打开公司电脑的旧场次 → 前台键鼠已采到 → 不修会误报采集有问题"""
        self.assertIsNone(self.notice(recording_scope='all', window_states=[dict(start=0, end=100, state='foreground')],
                                      intervals=[row('mouse', 'MouseLeft', 50)]))

    def test_foreground_events_beside_a_switch_do_not_prove_capture(self):
        """触发路径：旧版本数据 → 回看窗口 → 打开场次 → 唯一的前台鼠标事件紧贴切窗 → 不修会把切窗残留当成采集正常"""
        self.assertEqual(self.notice(recording_scope='all', window_states=[
            dict(start=0, end=50, state='foreground'), dict(start=50, end=100, state='background')],
            intervals=[row('mouse', 'MouseMove', 49.95)]), KEYBOARD_MOUSE_NOTICE)

    def test_legacy_session_uses_focus_gaps_as_window_switches(self):
        """触发路径：旧版本数据 → 回看窗口 → 打开前台限定场次 → 键鼠只在切窗边上 → 不修会漏掉这批早期场次"""
        gap = dict(start=50, end=52, type='focus', reason='目标窗口不在前台，操作采集已暂停')
        self.assertEqual(self.notice(gaps=[gap], intervals=[row('mouse', 'MouseMove', 49.95)]), KEYBOARD_MOUSE_NOTICE)
        self.assertIsNone(self.notice(gaps=[gap], intervals=[row('mouse', 'MouseLeft', 20)]))

    def test_triggers_only_session_names_what_is_missing(self):
        """触发路径：旧版本数据 → 回看窗口 → 打开整场手柄只有 LT/RT 的场次 → 摇杆和按键也缺 → 不修提示只说键鼠，低估缺失范围"""
        self.assertEqual(self.notice(intervals=[row('xbox', 'LT', 10), row('xbox', 'RT', 20)]), TRIGGERS_ONLY_NOTICE)

    def test_session_with_a_recorded_elevation_gap_needs_no_notice(self):
        """触发路径：旧版本数据 → 回看窗口 → 打开 0.10.2 起点了“否”的场次 → 已有键鼠缺口 → 不修会重复说同一件事"""
        self.assertIsNone(self.notice(gaps=[dict(start=0, end=100, type='capture', reason=ELEVATED_FOREGROUND, device='keyboard')]))

    def test_new_recording_is_marked_and_survives_recovery(self):
        """触发路径：系统状况 → 录制中进程被结束 → 下次启动恢复场次 → 标记要保留 → 不修恢复后的新场次会被误报"""
        now = [100.]
        capture = InputRecorder(self.folder, lambda: SimpleNamespace(start=lambda callback: None, stop=lambda: None),
                                clock=lambda: now[0], flush_interval=1000, recording_scope='all', block_check=True)
        capture.start()
        capture._flush()
        capture._writer_stop.set()
        self.assertTrue(json.loads((self.folder / 'input-events.json').read_text(encoding='utf-8'))[BLOCK_CHECK])
        value = recover_capture(self.folder, 10)
        self.assertIs(value[BLOCK_CHECK], True)
        self.assertNotIn('capture_notice', input_payload(self.folder, dict(media=dict(duration=10))))

    def test_finished_new_recording_shows_no_notice_without_keyboard_mouse(self):
        """触发路径：用户 → 主窗口录制一场只用手柄 → 回看窗口打开 → 检查已做过 → 不修每场新手柄场次都会误报"""
        now = [100.]
        capture = InputRecorder(self.folder, lambda: SimpleNamespace(start=lambda callback: None, stop=lambda: None),
                                clock=lambda: now[0], flush_interval=1000, recording_scope='all', block_check=True)
        capture.start()
        capture.stop(duration=10)
        self.assertNotIn('capture_notice', input_payload(self.folder, dict(media=dict(duration=10))))

    def test_agent_evidence_and_summary_carry_the_notice(self):
        """触发路径：命令行 → agent_cli evidence 和操作汇总 → 读旧场次的操作记录 → 不修 agent 会把空白写成没操作"""
        folder = self.folder / '资料库' / '场次' / 'fixture'
        folder.mkdir(parents=True)
        recorder.write(folder / 'session.json', dict(id='fixture', game='合成体验', state='可回看', test=True,
                                                     transcription_state='ready', media=dict(duration=12),
                                                     settings=dict(record_inputs=True)))
        recorder.write(folder / '录像.whisper.json', dict(segments=[dict(start=2, end=4, text='合成原话', speaker_id=0)]))
        recorder.write(folder / 'input-events.json', dict(version=1, state='complete', duration=12, timebase='video_seconds',
                                                          intervals=[row('xbox', 'A', 3)], gaps=[]))
        (folder / '录像.mp4').write_bytes(b'Synthetic placeholder')
        agent.publish_ready(folder)
        self.assertEqual(agent.evidence(folder)['inputs']['capture_notice'], KEYBOARD_MOUSE_NOTICE)
        self.assertEqual(agent.evidence(folder, 2, 4)['inputs']['capture_notice'], KEYBOARD_MOUSE_NOTICE)
        self.assertEqual(agent.input_summary(folder, 0, 12)['capture_notice'], KEYBOARD_MOUSE_NOTICE)


if __name__ == '__main__':
    unittest.main()
