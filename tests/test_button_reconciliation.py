"""Missed releases are repaired using physical-state observations, not a cap."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from input_capture import InputRecorder
from input_capture_windows import ButtonStateReconciler, WindowsInputSource
from review_runtime import input_payload


class ReconciliationTests(unittest.TestCase):
    def down(self, tracker, at=100., code='MouseLeft', device='mouse'):
        tracker.observe(dict(type='button', timestamp=at, device=device, code=code, down=True))

    def test_missed_release_cannot_reach_end_of_hour_long_recording(self):
        tracker = ButtonStateReconciler()
        self.down(tracker)
        self.assertEqual(tracker.sample(100.1, lambda vk: True), [])
        self.assertEqual(tracker.sample(100.2, lambda vk: False), [])
        events = tracker.sample(100.3, lambda vk: False)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['timestamp'], 100.1)
        self.assertEqual(events[0]['end_reason'], 'release_unobserved')
        self.assertEqual(tracker.sample(4430.99, lambda vk: False), [])
        self.assertEqual(tracker.finish(6089), [])

    def test_genuine_hold_longer_than_reported_bug_is_not_clipped(self):
        """触发路径：用户 → 操作录制 → 实际按住鼠标或 F4 → 长时间未松开 → 不能按键名或时长误删。"""
        for device, code in (('mouse', 'MouseLeft'), ('keyboard', 'F4')):
            with self.subTest(device=device, code=code):
                tracker = ButtonStateReconciler()
                self.down(tracker, device=device, code=code)
                for at in range(101, 6000):
                    self.assertEqual(tracker.sample(at, lambda vk: True), [])
                tracker.observe(dict(type='button', timestamp=6000., device=device, code=code, down=False))
                self.assertEqual(tracker.finish(6010), [])

    def test_one_false_sample_does_not_split_a_hold(self):
        tracker = ButtonStateReconciler()
        self.down(tracker)
        self.assertEqual(tracker.sample(100.1, lambda vk: False), [])
        self.assertEqual(tracker.sample(100.2, lambda vk: True), [])
        self.assertEqual(tracker.sample(100.3, lambda vk: False), [])
        self.assertEqual(tracker.sample(100.31, lambda vk: False), [])
        events = tracker.sample(100.4, lambda vk: False)
        self.assertEqual(events[0]['timestamp'], 100.2)

    def test_stop_does_not_extend_last_confirmed_state_to_recording_end(self):
        tracker = ButtonStateReconciler()
        self.down(tracker)
        tracker.sample(100.1, lambda vk: True)
        events = tracker.finish(150.)
        self.assertEqual(events[0]['timestamp'], 100.1)
        self.assertEqual(events[0]['end_reason'], 'recording_end')
        self.assertEqual(tracker.finish(151.), [])

    def test_unknown_is_not_release_and_controls_remain_independent(self):
        tracker = ButtonStateReconciler()
        self.down(tracker)
        self.down(tracker, code='W', device='keyboard')
        events = tracker.sample(101., lambda vk: None if vk == 1 else True)
        self.assertEqual([(e['code'], e['timestamp'], e['end_reason']) for e in events],
                         [('MouseLeft', 100., 'state_unavailable')])
        self.assertIn(('keyboard', 'W'), tracker.active)

    def test_background_capture_reconciles_but_queued_raw_messages_take_priority(self):
        source = WindowsInputSource(None, None, clock=lambda: 101., capture_all=True)
        source._capture_started = 100.
        source._foreground = lambda: False
        calls = []
        source._button_probe = SimpleNamespace(available=lambda: calls.append(1) or True, raised_foreground=lambda: False)
        source.user = SimpleNamespace(GetAsyncKeyState=lambda vk: 0)
        self.down(source._buttons)
        source._reconcile_buttons(queue_drained=False)
        self.assertEqual(calls, [])
        source._reconcile_buttons()
        self.assertEqual(calls, [1])
        source.clock = lambda: 101.2
        source._reconcile_buttons()
        self.assertEqual(source._pending[0]['code'], 'MouseLeft')

    def test_collector_persists_uncertainty_and_original_raw_release_precision(self):
        clock = SimpleNamespace(value=100.)
        class Source:
            def start(self, callback): self.callback = callback
            def stop(self): pass
        source = Source()
        with TemporaryDirectory() as folder:
            recorder = InputRecorder(folder, lambda: source, clock=lambda: clock.value,
                                     recording_scope='all', flush_interval=60)
            recorder.start(origin=100.)
            try:
                tracker = ButtonStateReconciler()
                down = dict(type='button', timestamp=101., device='mouse', code='MouseLeft', down=True)
                tracker.observe(down)
                source.callback(down)
                tracker.sample(101.1, lambda vk: True)
                tracker.sample(101.2, lambda vk: False)
                for event in tracker.sample(101.3, lambda vk: False): source.callback(event)
                for at, held in ((102., True), (102.017, False)):
                    source.callback(dict(down, timestamp=at, down=held))
                clock.value = 6090.
                result = recorder.stop()
                self.assertEqual([(r['start'], r['end']) for r in result['intervals']], [(1., 1.1), (2., 2.017)])
                projected = input_payload(folder, {'media': {'duration': 5990.}})
                self.assertEqual(projected['intervals'][0]['end_reason'], 'release_unobserved')
                self.assertNotIn('end_reason', projected['intervals'][1])
            finally:
                recorder.stop()


class StartupStateTests(unittest.TestCase):
    def source(self):
        clock = SimpleNamespace(value=100.)
        source = WindowsInputSource(None, None, clock=lambda: clock.value, capture_all=True)
        source._capture_started = 100.
        source.user = SimpleNamespace(GetAsyncKeyState=Mock(side_effect=lambda vk: 0x8000 if vk == 0x73 else 0))
        source._button_probe = SimpleNamespace(available=lambda: True, raised_foreground=lambda: False)
        source._controllers = SimpleNamespace(resume=Mock())
        return source, clock

    def test_startup_stale_state_does_not_create_a_session_long_press(self):
        """触发路径：用户 → 开始录制 → Windows 遗留 F4 按住状态 → 没有按下事件 → 不应虚构整场长按。"""
        source, clock = self.source()
        source._resume_due = 100.
        source._resume_if_stable()
        for at in (100.1, 200., 628.7):
            clock.value = at
            source._reconcile_buttons()
        source._pending.extend(source._buttons.finish(628.8))
        self.assertEqual(source._pending, [])
        source.user.GetAsyncKeyState.assert_not_called()
        source._controllers.resume.assert_called_once_with()

    def test_restored_access_does_not_invent_keys_after_a_gap(self):
        """触发路径：系统 → 录制时键鼠状态暂不可读 → 恢复权限且 F4 状态滞留 → 不应补出新的按下。"""
        source, clock = self.source()
        source._emit(dict(type='button', device='keyboard', code='W', down=True, timestamp=100.))
        source._button_probe.available = lambda: False
        clock.value = 100.1
        source._reconcile_buttons()
        source._button_probe.available = lambda: True
        clock.value = 100.2
        source._reconcile_buttons()
        self.assertEqual([(e['code'], e['down']) for e in source._pending], [('W', True), ('W', False)])
        self.assertEqual(source._pending[-1]['end_reason'], 'state_unavailable')
        source.user.GetAsyncKeyState.assert_not_called()

    def test_real_raw_f4_and_mouse_transitions_are_still_recorded(self):
        """触发路径：用户 → 录制中真实按下并松开 F4、鼠标 → Raw Input → 保留实际键位与准确起止。"""
        import ctypes as C
        from input_capture_windows import RawInput
        source, clock = self.source()
        raw = RawInput()
        def get_raw(_handle, _command, buffer, size, _header_size):
            size._obj.value = C.sizeof(raw)
            if buffer is None:
                return 0
            C.memmove(buffer, C.byref(raw), C.sizeof(raw))
            return C.sizeof(raw)
        source.user.GetRawInputData = get_raw
        source._stamp = lambda: clock.value
        for at, device, down in ((101., 'keyboard', True), (101.125, 'keyboard', False),
                                 (102., 'mouse', True), (102.25, 'mouse', False)):
            clock.value = at
            raw = RawInput()
            raw.header.size = C.sizeof(raw)
            if device == 'keyboard':
                raw.header.type = 1
                raw.data.keyboard.vkey = 0x73
                raw.data.keyboard.flags = 0 if down else 1
            else:
                raw.header.type = 0
                raw.data.mouse.flags = 1 if down else 2
            source._raw(1)
        self.assertEqual([(e['code'], e['down'], e['timestamp']) for e in source._pending],
                         [('F4', True, 101.), ('F4', False, 101.125),
                          ('MouseLeft', True, 102.), ('MouseLeft', False, 102.25)])
        self.assertTrue(all('resumed' not in e for e in source._pending))
        self.assertEqual(source._buttons.finish(6000.), [])


class HistoricalCorrectionTests(unittest.TestCase):
    def test_exact_correction_preserves_source_and_other_long_holds(self):
        with TemporaryDirectory() as folder:
            folder = Path(folder)
            rows = [dict(id='i1', device='mouse', code='MouseLeft', kind='button', start=10., end=4340.99),
                    dict(id='i2', device='keyboard', code='W', kind='button', start=12., end=5000.)]
            raw = json.dumps(dict(version=1, state='complete', timebase='video_seconds', duration=6000., intervals=rows, gaps=[])).encode()
            (folder / 'input-events.json').write_bytes(raw)
            correction = dict(version=1, source_sha256=hashlib.sha256(raw).hexdigest(),
                              excluded=[dict(rows[0], reason='User confirmed phantom hold')])
            path = folder / 'input-events.corrections.json'
            path.write_text(json.dumps(correction), encoding='utf-8')
            result = input_payload(folder, {})
            self.assertEqual(result['intervals'], [rows[1]])
            self.assertEqual(result['input_corrections']['excluded_count'], 1)
            self.assertEqual((folder / 'input-events.json').read_bytes(), raw)
            # Portable projection keeps the notice without requiring private journal/correction files.
            path.unlink()
            (folder / 'input-events.json').write_text(json.dumps(result), encoding='utf-8')
            self.assertEqual(input_payload(folder, {})['input_corrections'], result['input_corrections'])
            # A changed source must not accidentally inherit a stale correction.
            path.write_text(json.dumps(correction), encoding='utf-8')
            failed = input_payload(folder, {})
            self.assertEqual(failed['state'], 'failed')
            self.assertEqual(failed['intervals'], [])
            self.assertIn('不匹配', failed['error'])


if __name__ == '__main__':
    unittest.main()
