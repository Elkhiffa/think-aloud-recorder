"""Synthetic level events only: no physical microphone, OBS or user recordings."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace as NS
import threading
import unittest
from unittest.mock import Mock, patch

from microphone_monitor import MicrophoneLevels, MicrophoneMonitor
from desktop_service import DesktopService
import recorder


class MicrophoneLevelsTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.levels = MicrophoneLevels(clock=lambda: self.now)
        self.levels.muted = False
        self.levels.track = True

    def feed(self, peak=0, name='口述', **extra):
        self.levels.on_input_volume_meters(NS(inputs=[dict(inputName=name,
            inputLevelsMul=[[peak / 2, peak, 1]], **extra)]))
        return self.levels.snapshot()

    def test_only_narration_output_peak_counts_and_not_game_or_input_peak(self):
        self.assertEqual(self.feed(.9, '游戏声音')['state'], 'unavailable')
        result = self.feed(0)
        self.assertEqual((result['state'], result['level']), ('quiet', 0))
        self.assertEqual(self.feed(.1)['state'], 'signal')
        self.assertEqual(self.levels.snapshot()['db'], -20)

    def test_short_pauses_are_neutral_and_long_silence_warns_then_recovers(self):
        self.assertEqual(self.feed()['state'], 'quiet')
        self.now = 119.9
        self.assertEqual(self.feed()['state'], 'quiet')
        self.now = 120
        self.assertEqual(self.feed()['state'], 'silent')
        self.now = 121
        self.assertEqual(self.feed(.1)['state'], 'signal')
        self.now = 122.2
        self.assertEqual(self.feed()['state'], 'quiet')
        self.now = 241
        self.assertEqual(self.feed()['state'], 'silent')

    def test_last_sound_time_survives_mute_routing_and_missing_packets(self):
        self.now=50;self.feed(.2)
        self.now=90
        self.levels.on_input_mute_state_changed(NS(input_name='口述',input_muted=True))
        self.now=169.9;self.feed(.5)
        self.assertEqual(self.levels.snapshot()['quiet_seconds'],119)
        self.now=170;self.feed(.5)
        self.assertEqual(self.levels.snapshot()['quiet_seconds'],120)
        self.levels.on_input_audio_tracks_changed(NS(input_name='口述',input_audio_tracks={'2':False}))
        self.levels.on_input_removed(NS(input_name='口述'))
        self.assertEqual(self.levels.snapshot(connected=False)['quiet_seconds'],120)
        self.levels.on_input_mute_state_changed(NS(input_name='口述',input_muted=False))
        self.levels.on_input_audio_tracks_changed(NS(input_name='口述',input_audio_tracks={'2':True}))
        self.assertEqual(self.feed(.1)['quiet_seconds'],0)

    def test_obs_mute_is_immediate_even_when_obs_reports_pre_mute_signal(self):
        self.feed(.5)
        self.levels.on_input_mute_state_changed(NS(input_name='口述', input_muted=True))
        self.assertEqual(self.feed(.5)['state'], 'muted')
        self.assertEqual(self.levels.snapshot()['level'], 0)
        self.levels.on_input_mute_state_changed(NS(input_name='口述', input_muted=False))
        self.assertEqual(self.feed(0)['state'], 'quiet')
        self.assertEqual(self.feed(.2)['state'], 'signal')

    def test_stale_missing_or_dead_connection_never_keeps_a_green_meter(self):
        self.feed(.5)
        self.now = 3
        self.assertEqual(self.levels.snapshot()['state'], 'unavailable')
        self.feed(.5)
        self.assertEqual(self.levels.snapshot(connected=False)['level'], 0)
        self.levels.on_input_volume_meters(NS(inputs=[]))
        self.assertEqual(self.levels.snapshot()['state'], 'unavailable')

    def test_missing_initial_settings_cannot_claim_signal(self):
        self.levels.muted = None
        self.assertEqual(self.feed(.5)['state'], 'unavailable')

    def test_routing_and_unrelated_mute_events(self):
        self.feed(.2)
        self.levels.on_input_mute_state_changed(NS(input_name='游戏声音', input_muted=True))
        self.assertEqual(self.levels.snapshot()['state'], 'signal')
        self.levels.on_input_audio_tracks_changed(NS(input_name='口述', input_audio_tracks={'2': False}))
        self.assertEqual(self.levels.snapshot()['state'], 'unrouted')
        self.assertEqual(self.levels.snapshot()['level'], 0)

    def test_multichannel_and_malformed_values_remain_finite(self):
        self.levels.on_input_volume_meters(NS(inputs=[dict(inputName='口述',
            inputLevelsMul=[[0, float('nan'), 1], [0, float('inf'), 1], [0, .25, 1], [0, 'bad'], []])]))
        self.assertAlmostEqual(self.levels.snapshot()['db'], -12, delta=.1)
        for data in (None, {}, ['bad'], [dict(inputName='口述', inputLevelsMul=None)]):
            self.levels.on_input_volume_meters(NS(inputs=data))

    def test_clipping_and_peak_decay_are_bounded(self):
        self.assertEqual(self.feed(1.2)['state'], 'loud')
        self.now = .2
        self.assertGreater(self.feed(0)['level'], 0)
        self.now = 2
        self.assertEqual(self.feed(0)['level'], 0)

    def test_subscription_wait_and_initial_failure_are_not_silence(self):
        self.assertEqual(self.levels.snapshot()['state'], 'connecting')
        self.now = 3
        self.assertEqual(self.levels.snapshot()['state'], 'unavailable')


class MicrophoneConnectionTests(unittest.TestCase):
    def request(self):
        request = Mock()
        request.base_client = NS(host='127.0.0.1', port=5555, password='synthetic-secret')
        request.get_input_mute.return_value = NS(input_muted=False)
        request.get_input_audio_tracks.return_value = NS(input_audio_tracks={'2': True})
        return request

    def test_connection_is_read_only_and_closes_once(self):
        request, client = self.request(), Mock()
        with patch('microphone_monitor.obs.EventClient', return_value=client) as create:
            meter = MicrophoneMonitor(request)
            self.assertEqual(create.call_args.kwargs['subs'], 65544)
            self.assertEqual([c[0] for c in request.method_calls], ['get_input_mute', 'get_input_audio_tracks'])
            meter.close()
            meter.close()
            client.disconnect.assert_called_once()
            self.assertEqual(meter.snapshot()['state'], 'unavailable')

    def test_init_failure_releases_event_socket(self):
        request, client = self.request(), Mock()
        request.get_input_mute.side_effect = RuntimeError('synthetic failure')
        with patch('microphone_monitor.obs.EventClient', return_value=client):
            with self.assertRaises(RuntimeError):
                MicrophoneMonitor(request)
        client.disconnect.assert_called_once()

    def test_event_during_initial_query_wins_over_old_response(self):
        request, client = self.request(), Mock()
        def mute_query(name):
            handlers = client.callback.register.call_args.args[0]
            handlers[1](NS(input_name=name, input_muted=True))
            return NS(input_muted=False)
        request.get_input_mute.side_effect = mute_query
        with patch('microphone_monitor.obs.EventClient', return_value=client):
            meter = MicrophoneMonitor(request)
            self.assertTrue(meter.levels.muted)
            meter.close()

    def test_session_failure_is_optional_and_reconnect_replaces_dead_monitor(self):
        with TemporaryDirectory() as directory:
            recorder.write(Path(directory) / 'session.json', dict(id='synthetic', test=False))
            session = recorder.Session(directory)
            first, second = Mock(), Mock()
            first.healthy.return_value = False
            with patch('microphone_monitor.MicrophoneMonitor', side_effect=[RuntimeError('failure'), first, second]):
                session.ensure_microphone_monitor(self.request())
                self.assertEqual(session.microphone_state()['state'], 'unavailable')
                session.ensure_microphone_monitor(self.request())
                session.ensure_microphone_monitor(self.request())
                first.close.assert_called_once()
                session.close_microphone_monitor()
                second.close.assert_called_once()

    def test_fast_bridge_reads_active_session_not_new_preset_or_other_sessions(self):
        service = DesktopService.__new__(DesktopService)
        service._lock = threading.RLock()
        service._device_labels = {'mic': {'active-device': '合成麦克风'}}
        service._devices = {'mic': []}
        service._active = NS(meta=dict(id='synthetic-active', settings=dict(mic='active-device')),
                            microphone_state=lambda: dict(state='signal', level=.5))
        with patch('recorder.client', side_effect=AssertionError('must not access OBS')):
            data = service.get_microphone_state()['data']
            self.assertEqual((data['session_id'], data['name']), ('synthetic-active', '合成麦克风'))
            service._active = None
            self.assertEqual(service.get_microphone_state()['data']['state'], 'idle')


if __name__ == '__main__':
    unittest.main()
