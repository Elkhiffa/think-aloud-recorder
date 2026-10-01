"""Missed releases are repaired using physical-state observations, not a cap."""
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

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
        tracker = ButtonStateReconciler()
        self.down(tracker)
        for at in range(101, 6000):
            self.assertEqual(tracker.sample(at, lambda vk: True), [])
        tracker.observe(dict(type='button', timestamp=6000., device='mouse', code='MouseLeft', down=False))
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
        source._button_probe = SimpleNamespace(available=lambda: calls.append(1) or True)
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
