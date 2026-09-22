"""Deterministic collector tests: no real keyboard/mouse/controller capture."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch

from input_capture import InputCaptureError, InputRecorder, capture_readiness, prepare_capture
from input_capture_devices import axis_event, Event, ControllerEvent, XBOX_BUTTONS, PS_BUTTONS
from input_capture_windows import parse_obs_window, key_code
import ctypes


class Clock:
    def __init__(self): self.value = 100.
    def __call__(self): return self.value


class Source:
    def __init__(self): self.stopped = 0
    def start(self, callback): self.callback = callback
    def stop(self): self.stopped += 1


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = Clock()
        self.source = Source()
        self.capture = InputRecorder(self.temp.name, lambda: self.source, clock=self.clock, flush_interval=60)
        self.capture.start(origin=100)
        self.addCleanup(self.capture.stop)
        self.send('focus', 0, foreground=True)

    def send(self, event_type, time, **data):
        self.clock.value = 100 + time
        self.source.callback(dict(type=event_type, timestamp=100 + time, **data))

    def button(self, code, time, down=True, device='keyboard', **data):
        self.send('button', time, device=device, code=code, down=down, foreground=True, **data)

    def test_short_tap_exact_interval_and_auto_repeat(self):
        self.button('Q', .100)
        self.button('Q', .101)  # auto-repeat does not create another key
        self.button('Q', .102, False)
        result = self.capture.stop()
        self.assertEqual(len(result['intervals']), 1)
        self.assertAlmostEqual(result['intervals'][0]['end'] - result['intervals'][0]['start'], .002)

    def test_snapshot_does_not_erase_queued_short_tap_timing(self):
        self.clock.value = 101
        self.capture.snapshot()
        self.button('Q', .8)
        self.button('Q', .802, False)
        result = self.capture.stop()
        self.assertAlmostEqual(result['intervals'][0]['end'] - result['intervals'][0]['start'], .002)
        self.assertGreaterEqual(result['duration'], 1)

    def test_focus_loss_closes_holds_and_excludes_other_app(self):
        self.button('W', 1)
        self.send('focus', 2, foreground=False)
        self.button('Password', 2.5)
        self.send('focus', 4, foreground=True)
        self.button('W', 4, resumed=True)
        self.button('W', 6, False)
        result = self.capture.stop()
        self.assertEqual([(i['code'], i['start'], i['end']) for i in result['intervals']], [('W', 1, 2), ('W', 4, 6)])
        self.assertTrue(result['intervals'][1]['resumed'])
        self.assertEqual([(g['type'], g['start'], g['end']) for g in result['gaps']], [('focus', 2, 4)])
        self.assertNotIn('Password', self.capture.path.read_text(encoding='utf-8'))

    def test_per_event_foreground_is_required(self):
        self.send('button', 1, device='keyboard', code='A', down=True)
        self.send('button', 2, device='keyboard', code='B', down=True, foreground=False)
        self.assertEqual(self.capture.stop()['intervals'], [])

    def test_long_hold_closed_once_stop_is_idempotent(self):
        self.button('W', 1)
        self.clock.value = 140
        result = self.capture.stop()
        self.assertEqual(result['intervals'][0]['end'], 40)
        self.assertEqual(self.capture.stop(), result)
        self.button('Q', 45)
        self.assertEqual(len(self.capture.snapshot()['intervals']), 1)

    def test_device_disconnect_does_not_close_keyboard(self):
        self.button('W', 1)
        self.button('A', 2, device='xbox')
        self.send('disconnect', 3, device='xbox')
        self.send('connect', 5, device='xbox')
        self.button('W', 6, False)
        result = self.capture.stop()
        self.assertEqual([(i['code'], i['end']) for i in result['intervals']], [('W', 6), ('A', 3)])
        self.assertEqual(result['gaps'][0]['type'], 'disconnect')
        self.assertEqual(result['gaps'][0]['end'], 5)

    def test_motion_idle_ends_at_last_sample_not_timeout(self):
        for t in (1, 1.03):
            self.send('motion', t, device='mouse', code='MouseMove', kind='motion', x=1, y=0, value=1, foreground=True)
        self.send('tick', 1.2)
        i = self.capture.stop()['intervals'][0]
        self.assertEqual((i['start'], i['end'], i['direction']), (1, 1.03, '→'))

    def test_axis_deadzone_and_trigger_depth(self):
        self.send('axis', 1, device='xbox', code='LeftStick', kind='axis', x=.1, y=.1, foreground=True)
        self.send('axis', 2, device='dualsense', code='R2', kind='trigger', value=.6, foreground=True)
        self.send('axis', 3, device='dualsense', code='R2', kind='trigger', value=0, foreground=True)
        result = self.capture.stop()
        self.assertEqual(len(result['intervals']), 1)
        self.assertEqual(result['intervals'][0]['value'], .6)

    def test_error_closes_capture_but_preserves_data(self):
        self.button('W', 1)
        self.send('error', 2)
        self.button('Q', 3)
        result = self.capture.stop()
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['intervals'][0]['end'], 2)
        self.assertEqual(result['gaps'][0]['type'], 'capture')
        self.assertEqual(json.loads(self.capture.path.read_text(encoding='utf-8'))['state'], 'failed')

    def test_offset_matches_video_seconds(self):
        self.capture.stop()
        source = Source()
        capture = InputRecorder(Path(self.temp.name) / 'offset', lambda: source, clock=self.clock, flush_interval=60)
        capture.start(origin=100, video_offset=2.5)
        self.addCleanup(capture.stop)
        source.callback({'type': 'focus', 'foreground': True, 'timestamp': 100.02})
        source.callback({'type': 'button', 'foreground': True, 'timestamp': 100.12,
                         'device': 'keyboard', 'code': 'A', 'down': True})
        source.callback({'type': 'button', 'foreground': True, 'timestamp': 100.14,
                         'device': 'keyboard', 'code': 'A', 'down': False})
        result = capture.stop()
        self.assertEqual(result['intervals'][0]['start'], 2.62)
        self.assertTrue(any(g['type'] == 'capture' and g['start'] == 0 and g['end'] == 2.5 for g in result['gaps']))

    def test_source_start_failure_closes_and_writes_failed(self):
        self.capture.stop()
        source = Source()
        source.start = lambda callback: (_ for _ in ()).throw(InputCaptureError('测试启动失败'))
        capture = InputRecorder(Path(self.temp.name) / 'fail', lambda: source, clock=self.clock)
        with self.assertRaises(InputCaptureError): capture.start()
        self.assertEqual(capture.snapshot()['state'], 'failed')
        self.assertEqual(source.stopped, 1)

    def test_no_sensitive_or_non_key_fields_persisted(self):
        self.button('A', 1, text='secret', window='other-app', clipboard='private')
        self.button('bad:<script>', 2)
        value = json.dumps(self.capture.stop(), ensure_ascii=False)
        self.assertNotIn('secret', value)
        self.assertNotIn('private', value)
        self.assertNotIn('other-app', value)
        self.assertNotIn('<script>', value)

    def test_out_of_order_same_key_does_not_make_negative_duration(self):
        self.button('W', 2)
        self.button('W', 1, False)
        self.button('W', 3, False)
        i = self.capture.stop()['intervals'][0]
        self.assertEqual((i['start'], i['end']), (2, 3))


class ProtocolTests(unittest.TestCase):
    def test_opt_out_does_not_import_native_or_readiness(self):
        with patch('input_capture.capture_readiness') as check:
            self.assertIsNone(prepare_capture({}, '.'))
            check.assert_not_called()

    def test_fullscreen_rejected_before_native_resolution(self):
        result = capture_readiness({'record_inputs': True, 'source': '整个屏幕'})
        self.assertFalse(result['ready'])
        self.assertIn('指定游戏窗口', result['error'])

    def test_obs_escaping_and_key_names(self):
        self.assertEqual(parse_obs_window('a#3Ab#22:UnityWndClass:game.exe'), ('a:b#', 'UnityWndClass', 'game.exe'))
        with self.assertRaises(InputCaptureError): parse_obs_window('unknown')
        self.assertEqual(key_code(16, 0x36), 'ShiftRight')
        self.assertEqual(key_code(17, flags=2), 'ControlRight')
        self.assertEqual(key_code(13, flags=2), 'NumEnter')
        self.assertIsNone(key_code(255))

    def test_existing_journal_is_not_overwritten(self):
        with TemporaryDirectory() as folder:
            journal = Path(folder) / 'input-events.journal'
            journal.write_text('preserved', encoding='utf-8')
            recorder = InputRecorder(folder, Source)
            with self.assertRaises(InputCaptureError):
                recorder.start()
            recorder.stop(error='已存在记录')
            self.assertEqual(journal.read_text(encoding='utf-8'), 'preserved')
            self.assertFalse((Path(folder) / 'input-events.json').exists())

    def test_sdl_abi_and_both_device_mappings(self):
        self.assertEqual(ctypes.sizeof(Event), 56)
        self.assertEqual(ControllerEvent.value.offset, 16)
        self.assertEqual(XBOX_BUTTONS[0], 'A')
        self.assertEqual(PS_BUTTONS[0], 'Cross')
        self.assertEqual(axis_event('dualsense', 5, [0, 0, 0, 0, 0, 16384])['code'], 'R2')
        self.assertEqual(axis_event('xbox', 0, [1000, 1000, 0, 0, 0, 0])['value'], 0)
        left = axis_event('xbox', 0, [-32768, 0, 0, 0, 0, 0])
        self.assertEqual((left['code'], left['x']), ('LeftStick', -1))

class RawDecoderTests(unittest.TestCase):
    """Inject Win32 structs into the decoder; no device registration is made."""
    def source_for(self, raw, foreground=True):
        from input_capture_windows import WindowsInputSource, TargetWindow
        source = WindowsInputSource(TargetWindow(0, 0, 0, 'synthetic'), 'unused', lambda: 101.)
        source._focus = lambda: foreground
        source._eligible_since = 100
        source._stamp = lambda: 101
        events = []
        source._emit = events.append
        def get_data(handle, command, buffer, size, header_size):
            ctypes.cast(size, ctypes.POINTER(ctypes.c_uint)).contents.value = ctypes.sizeof(raw)
            if buffer is not None:
                ctypes.memmove(buffer, ctypes.byref(raw), ctypes.sizeof(raw))
                return ctypes.sizeof(raw)
            return 0
        from types import SimpleNamespace
        source.user = SimpleNamespace(GetRawInputData=get_data)
        return source, events

    def test_raw_keyboard_press_and_release(self):
        from input_capture_windows import RawInput
        raw = RawInput()
        raw.header.type = 1
        raw.data.keyboard.vkey = 87
        source, events = self.source_for(raw)
        source._raw(1)
        raw.data.keyboard.flags = 1
        source._raw(1)
        self.assertEqual([(e['code'], e['down']) for e in events], [('W', True), ('W', False)])

    def test_raw_mouse_buttons_wheel_and_direction(self):
        from input_capture_windows import RawInput
        raw = RawInput()
        raw.header.type = 0
        raw.data.mouse.flags = 1 | 0x400
        raw.data.mouse.data = 120
        raw.data.mouse.x = 30
        raw.data.mouse.y = -30
        source, events = self.source_for(raw)
        source._raw(1)
        self.assertEqual([e['code'] for e in events], ['MouseLeft', 'WheelUp', 'MouseMove'])
        self.assertGreater(events[-1]['x'], 0)
        self.assertLess(events[-1]['y'], 0)

    def test_outside_focus_rejects_before_reading_raw_contents(self):
        from input_capture_windows import RawInput
        source, events = self.source_for(RawInput(), False)
        with patch.object(source.user, 'GetRawInputData') as read:
            source._raw(1)
            read.assert_not_called()
        self.assertEqual(events, [])

    def test_queued_old_event_is_not_attributed_after_focus_return(self):
        from input_capture_windows import RawInput
        raw = RawInput()
        raw.header.type = 1
        raw.data.keyboard.vkey = 87
        source, events = self.source_for(raw)
        source._eligible_since = 102
        source._raw(1)
        self.assertEqual(events, [])



class JournalAndFocusRegressionTests(unittest.TestCase):
    setUp = CollectorTests.setUp
    send = CollectorTests.send
    button = CollectorTests.button

    def test_live_checkpoint_stays_small_and_recovers_holds(self):
        from input_capture import recover_capture
        for index in range(500):
            self.button('A', index * .01)
            self.button('A', index * .01 + .005, False)
        self.button('W', 5)
        self.clock.value = 106
        self.capture._flush()
        checkpoint = json.loads(self.capture.path.read_text(encoding='utf-8'))
        self.assertEqual(checkpoint['intervals'], [])
        self.assertEqual(checkpoint['journal_records'], 500)
        self.assertLess(self.capture.path.stat().st_size, 2000)
        recovered = recover_capture(self.temp.name, duration=8)
        self.assertEqual(len(recovered['intervals']), 501)
        self.assertEqual(recovered['intervals'][-1]['end'], 6)
        self.assertEqual(recovered['gaps'][-1]['start'], 6)
        self.assertEqual(recovered['gaps'][-1]['end'], 8)

    def test_recovery_ignores_uncheckpointed_and_partial_journal_tail(self):
        from input_capture import recover_capture
        self.button('A', 1)
        self.button('A', 2, False)
        self.capture._flush()
        with self.capture.journal_path.open('a', encoding='utf-8') as file:
            file.write('{"type":"interval","value":{"untrusted":')
        recovered = recover_capture(self.temp.name, 5)
        self.assertEqual(len(recovered['intervals']), 1)
        self.assertEqual(recovered['intervals'][0]['code'], 'A')
        self.assertEqual(recovered['gaps'][-1]['end'], 5)

    def test_video_cutoff_removes_unsynchronized_tail(self):
        self.button('W', 1)
        self.button('A', 6)
        self.clock.value = 110
        value = self.capture.stop(duration=10, trim_to=5, error='视频时间中断')
        self.assertEqual(value['duration'], 5)
        self.assertEqual([(i['code'], i['start'], i['end']) for i in value['intervals']], [('W', 1, 5)])

    def test_history_read_does_not_hold_capture_lock(self):
        import threading
        import input_capture
        entered, release = threading.Event(), threading.Event()
        original = input_capture._read_journal
        def blocking_read(*args):
            entered.set()
            release.wait(2)
            return original(*args)
        with patch('input_capture._read_journal', side_effect=blocking_read):
            thread = threading.Thread(target=self.capture.snapshot)
            thread.start()
            self.assertTrue(entered.wait(1))
            self.button('Q', 1)
            self.button('Q', 1.002, False)
            release.set()
            thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_resuming_samples_recheck_actual_focus_before_emitting(self):
        from input_capture_windows import WindowsInputSource, TargetWindow
        from types import SimpleNamespace
        from unittest.mock import Mock
        source = WindowsInputSource(TargetWindow(0, 0, 0, 'test'), 'unused', self.clock)
        source._eligible = True
        source._eligible_since = 99
        source._foreground = Mock(side_effect=[True, False, False])
        source.user = SimpleNamespace(GetAsyncKeyState=Mock(return_value=0x8000))
        source.callback = Mock()
        source._resume_keyboard()
        self.assertEqual(source._pending, [])
        self.assertEqual(source.user.GetAsyncKeyState.call_count, 1)
        source.callback.assert_not_called()

    def test_away_and_back_while_capture_blocked_does_not_authorize_queued_input(self):
        from input_capture_windows import WindowsInputSource, TargetWindow, ForegroundLedger
        from types import SimpleNamespace
        ledger = ForegroundLedger()
        ledger.note(True, 100)
        ledger.note(False, 101)
        ledger.note(True, 102)
        ledger.publish(103)
        self.assertFalse(ledger.authorized(101.5))
        self.assertTrue(ledger.authorized(102.5))
        source = WindowsInputSource(TargetWindow(0, 0, 0, 'test'), 'unused', self.clock)
        source._observer = SimpleNamespace(ledger=ledger, error=None)
        source._pending = [{'type': 'button', 'device': 'keyboard', 'code': 'PasswordKey',
                            'down': True, 'foreground': True, 'timestamp': 101.5}]
        events = []
        source.callback = events.append
        source._flush_pending()
        self.assertFalse(any(e['type'] == 'button' for e in events))
        self.assertTrue(any(e['type'] == 'coverage_gap' for e in events))

    def test_late_notification_removes_already_checkpointed_event_and_journal(self):
        from input_capture import recover_capture
        from input_capture_windows import WindowsInputSource, TargetWindow, ForegroundLedger
        from types import SimpleNamespace
        ledger = ForegroundLedger()
        ledger.note(True, 100)
        ledger.publish(103)
        source = WindowsInputSource(TargetWindow(0, 0, 0, 'test'), 'unused', self.clock)
        source._observer = SimpleNamespace(ledger=ledger, error=None)
        source.callback = self.capture.feed
        source._pending = [
            {'type': 'button', 'device': 'keyboard', 'code': 'A', 'down': True, 'foreground': True, 'timestamp': 101.5},
            {'type': 'button', 'device': 'keyboard', 'code': 'A', 'down': False, 'foreground': True, 'timestamp': 101.6}]
        self.clock.value = 103
        source._flush_pending()
        self.capture._flush()
        self.assertIn('"code":"A"', self.capture.journal_path.read_text(encoding='utf-8'))
        ledger.note(False, 101, observed=104)
        ledger.note(True, 102, observed=104)
        self.clock.value = 104
        source._flush_pending()
        self.assertTrue(source._stop.is_set())
        self.capture._purger.join(2)
        self.assertNotIn('"code":"A"', self.capture.journal_path.read_text(encoding='utf-8'))
        result = self.capture.stop()
        self.assertEqual(result['intervals'], [])
        self.assertEqual(result['state'], 'failed')
        self.assertTrue(any(g['type']=='capture' and g['start']==1 for g in result['gaps']))
        recovered = recover_capture(self.temp.name, duration=6)
        self.assertEqual(recovered['intervals'], [])

    def test_trimmed_journal_cannot_reintroduce_discarded_tail(self):
        self.button('W', 1)
        self.button('W', 2, False)
        self.button('A', 6)
        self.button('A', 7, False)
        self.capture._flush()
        self.capture.stop(duration=8, trim_to=4)
        journal = self.capture.journal_path.read_text(encoding='utf-8')
        self.assertIn('"code":"W"', journal)
        self.assertNotIn('"code":"A"', journal)

    def test_revocation_survives_checkpoint_write_failure_with_stale_active_hold(self):
        import input_capture
        self.button('A', 1.5)
        self.send('watermark', 3)
        self.capture._flush()
        old = json.loads(self.capture.path.read_text(encoding='utf-8'))
        self.assertEqual(old['journal_records'], 0)
        self.assertEqual(old['active'][0]['end'], 3)
        original = input_capture._atomic_json
        def fail_checkpoint(path, value):
            if path == self.capture.path:
                raise OSError('Synthetic checkpoint replacement failure')
            return original(path, value)
        with patch('input_capture._atomic_json', side_effect=fail_checkpoint):
            self.send('invalidate', 1)
            self.capture._purger.join(2)
        self.assertFalse(self.capture._purger.is_alive())
        self.assertEqual(json.loads(self.capture.revocation_path.read_text(encoding='utf-8'))['invalid_from'], 1)
        self.assertEqual(json.loads(self.capture.path.read_text(encoding='utf-8'))['active'][0]['code'], 'A')
        result = input_capture.recover_capture(self.temp.name, duration=5)
        self.assertEqual(result['intervals'], [])
        self.assertNotIn('"code":"A"', self.capture.journal_path.read_text(encoding='utf-8'))
        self.assertTrue(any(g['type']=='capture' and g['start']==1 for g in result['gaps']))

    def test_persistent_revocation_keeps_earliest_cutoff(self):
        from input_capture import _record_revocation, _read_revocation
        _record_revocation(self.capture.revocation_path, 2)
        _record_revocation(self.capture.revocation_path, 4)
        self.assertEqual(_read_revocation(self.capture.revocation_path), 2)
        _record_revocation(self.capture.revocation_path, 1)
        self.assertEqual(_read_revocation(self.capture.revocation_path), 1)

    def test_raw_message_age_is_not_clamped_to_sixty_seconds(self):
        from input_capture_windows import WindowsInputSource, TargetWindow
        from types import SimpleNamespace
        source = WindowsInputSource(TargetWindow(0,0,0,'test'), 'unused', lambda: 1000.)
        source.kernel = SimpleNamespace(GetTickCount64=lambda: 100000)
        source.user = SimpleNamespace(GetMessageTime=lambda: 10000)
        self.assertEqual(source._stamp(), 910.)

    def test_wall_time_without_marker_ack_does_not_release_queued_input(self):
        from input_capture_windows import WindowsInputSource, TargetWindow, ForegroundLedger
        from types import SimpleNamespace
        ledger = ForegroundLedger()
        ledger.note(True, 100)
        source = WindowsInputSource(TargetWindow(0,0,0,'test'), 'unused', self.clock)
        source._observer = SimpleNamespace(ledger=ledger, error=None)
        source._pending = [{'type':'button','device':'keyboard','code':'A','down':True,'foreground':True,'timestamp':101}]
        events=[]
        source.callback=events.append
        self.clock.value=500
        source._flush_pending()
        self.assertFalse(any(e['type']=='button' for e in events))
        ledger.publish(102)  # Simulates the acknowledged marker callback only.
        source._flush_pending()
        self.assertTrue(any(e['type']=='button' for e in events))

    def test_checkpoint_hold_does_not_extend_beyond_acknowledged_boundary(self):
        self.button('W', 1)
        self.send('watermark', 1.5)
        self.clock.value=110
        self.capture._flush()
        checkpoint=json.loads(self.capture.path.read_text(encoding='utf-8'))
        self.assertEqual(checkpoint['duration'], 1.5)
        self.assertEqual(checkpoint['active'][0]['end'], 1.5)
        value=self.capture.stop(duration=10)
        self.assertEqual(value['intervals'][0]['end'], 1.5)
        self.assertTrue(any(g['type']=='capture' and g['start']==1.5 and g['end']>=10 for g in value['gaps']))

    def test_source_stop_wait_does_not_extend_hold_past_final_ack(self):
        self.button('W', 1)
        self.send('watermark', 1.5)
        def stop_after_wait():
            self.source.stopped += 1
            self.clock.value = 104
        self.source.stop = stop_after_wait
        value = self.capture.stop(duration=5)
        self.assertEqual(value['intervals'][0]['end'], 1.5)
        self.assertTrue(any(g['type']=='capture' and g['start']==1.5 and g['end']==5 for g in value['gaps']))
        journal = [json.loads(line) for line in self.capture.journal_path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([r['value']['end'] for r in journal if r['type']=='interval'], [1.5])

    def test_observer_error_closes_hold_at_last_ack_and_records_gap(self):
        self.button('W', 1)
        self.send('watermark', 1.5)
        self.send('error', 3)
        value = self.capture.stop(duration=5)
        self.assertEqual(value['state'], 'failed')
        self.assertEqual(value['intervals'][0]['end'], 1.5)
        self.assertTrue(any(g['type']=='capture' and g['start']==1.5 and g['end']==5 for g in value['gaps']))

    def test_shared_tick_mapping_preserves_event_time_across_delivery_delay(self):
        from input_capture_windows import SystemTickClock
        ticks = [100000]
        mapper = SystemTickClock(self.clock, lambda: ticks[0])
        ticks[0] = 101000
        first = mapper.from_tick32(100500)
        self.clock.value = 190
        ticks[0] = 190000
        self.assertEqual(mapper.from_tick32(100500), first)
        self.assertEqual(first, 100.5)

    def test_focus_transition_quantization_band_is_excluded(self):
        from input_capture_windows import ForegroundLedger
        ledger = ForegroundLedger()
        ledger.note(True, 100)
        ledger.note(False, 101)
        ledger.note(True, 102)
        ledger.publish(103)
        self.assertFalse(ledger.authorized(100.980))
        self.assertFalse(ledger.authorized(102.020))
        self.assertTrue(ledger.authorized(100.950))
        self.assertTrue(ledger.authorized(102.050))

    def test_late_foreground_event_invalidates_ambiguous_range(self):
        from input_capture_windows import ForegroundLedger
        ledger = ForegroundLedger()
        ledger.note(True, 100)
        ledger.publish(102)
        ledger.note(False, 101, observed=103)
        ledger.note(True, 101.5, observed=103)
        ledger.publish(104)
        self.assertFalse(ledger.authorized(102.5))
        self.assertTrue(ledger.authorized(103.5))


if __name__ == '__main__':
    unittest.main()
