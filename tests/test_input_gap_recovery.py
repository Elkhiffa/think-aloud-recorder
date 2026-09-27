"""Missing foreground notification and pathological historical gap regressions."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from input_capture import InputRecorder, compact_gaps, UNCERTAIN_INPUT, FOREGROUND_MISMATCH
from input_capture_windows import ForegroundLedger, ForegroundObserver, TargetWindow, WindowsInputSource
from review_runtime import input_payload


class GapRecoveryTests(unittest.TestCase):
    def test_long_legacy_focus_gap_absorbs_rejected_points_without_inventing_input(self):
        focus = dict(start=7., end=3700., type='focus', reason='目标窗口不在前台，操作采集已暂停')
        points = [dict(start=100+i/130., end=100+i/130., type='capture', reason=UNCERTAIN_INPUT) for i in range(466727)]
        result = compact_gaps([focus, *points])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['discarded_events'], 466727)
        self.assertEqual(result[0]['reason'], FOREGROUND_MISMATCH)
        self.assertEqual((result[0]['start'], result[0]['end']), (7., 3700.))
        self.assertEqual(focus['type'], 'focus')  # Does not edit source evidence.
        self.assertEqual(compact_gaps(result), result)

    def test_device_disconnect_does_not_hide_unrelated_gap_or_bridge_success(self):
        gaps = [dict(start=0,end=10,type='disconnect',device='xbox',reason='disconnect'),
                dict(start=1,end=1,type='capture',reason=UNCERTAIN_INPUT),
                dict(start=2,end=3,type='capture',reason='error'),
                dict(start=4,end=5,type='capture',reason='error')]
        self.assertEqual(compact_gaps(gaps), gaps)

    def test_live_rejected_event_storm_keeps_bounded_checkpoint_and_journal(self):
        clock = [100.]
        source = SimpleNamespace(start=lambda callback: None, stop=lambda: None)
        with TemporaryDirectory() as folder:
            capture = InputRecorder(folder, lambda: source, clock=lambda: clock[0], flush_interval=1000)
            capture.start()
            for i in range(10000):
                clock[0] = 101+i*.004
                capture.feed(dict(type='coverage_gap', timestamp=clock[0], end=clock[0]))
                if i % 500 == 0:
                    capture._flush()
            value = capture.stop()
            self.assertEqual(value['intervals'], [])
            self.assertLess(len(value['gaps']), 4)
            self.assertEqual(sum(g.get('discarded_events',0) for g in value['gaps']), 10000)
            self.assertLess(Path(folder,'input-events.journal').stat().st_size, 2000)

    def test_missing_return_notification_recovers_only_future_confirmed_events(self):
        target = TargetWindow(1,2,3,'test')
        observer = ForegroundObserver(target, lambda: 102.)
        ledger = observer.ledger
        ledger.note(False, 100)
        ledger.publish(101)
        observer._confirm_focus(True, 101.01)
        observer._confirm_focus(True, 101.04)
        self.assertFalse(ledger.transitions[-1][1])
        observer._confirm_focus(True, 101.08)
        self.assertEqual(observer.focus_reconciliations, 1)
        ledger.publish(102)
        self.assertFalse(ledger.authorized(100.8))
        self.assertFalse(ledger.authorized(101.05))
        self.assertFalse(ledger.authorized(101.10))
        self.assertTrue(ledger.authorized(101.2))
        source = WindowsInputSource(target, 'unused', lambda: 102.)
        source._observer = observer
        events = []
        source.callback = events.append
        source._pending = [dict(type='button',timestamp=t,device='keyboard',code='W',foreground=True,down=True) for t in (100.8,101.2)]
        source._flush_pending()
        self.assertEqual([e['timestamp'] for e in events if e['type']=='button'], [101.2])
        self.assertAlmostEqual(source._resume_due, 102.064)

    def test_transient_focus_disagreement_does_not_override_notifications(self):
        observer = ForegroundObserver(TargetWindow(1,2,3,'test'),lambda: 102.)
        observer.ledger.note(False,100)
        observer._confirm_focus(True,101)
        observer._confirm_focus(False,101.03)
        observer._confirm_focus(True,101.04)
        observer._confirm_focus(True,101.07)
        self.assertEqual(observer.focus_reconciliations,0)
        self.assertEqual(observer.ledger.transitions,[(100,False)])

    def test_late_notification_after_reconciliation_still_revokes(self):
        ledger = ForegroundLedger()
        ledger.note(False,100)
        ledger.publish(101)
        ledger.reconcile(True,101.1)
        ledger.publish(102)
        ledger.note(False,101.5,observed=103)
        self.assertEqual(ledger.invalid_from,101.5)
        self.assertFalse(ledger.authorized(101.7))

    def test_review_compacts_evidence_without_mutating_stored_sidecar(self):
        with TemporaryDirectory() as folder:
            data = dict(version=1,state='complete',duration=10,timebase='video_seconds',intervals=[],gaps=[
                dict(start=0,end=10,type='focus',reason='outside'),
                *[dict(start=1+i/1000,end=1+i/1000,type='capture',reason=UNCERTAIN_INPUT) for i in range(5000)]])
            path=Path(folder,'input-events.json'); raw=json.dumps(data).encode(); path.write_bytes(raw)
            result=input_payload(folder,dict(media=dict(duration=10)))
            self.assertEqual(len(result['gaps']),1)
            self.assertEqual(result['gaps'][0]['discarded_events'],5000)
            self.assertEqual(result['intervals'],[])
            self.assertEqual(path.read_bytes(),raw)


if __name__ == '__main__':
    unittest.main()
