"""Synthetic lifecycle checks: no OBS, native listeners, or cloud requests."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import threading
import unittest
import json
import zipfile

import recorder
from review_runtime import ReviewAPI, prepare_window, render_player


class SessionInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cfg = dict(game='Synthetic', vault=str(self.root / 'library'), source='游戏窗口',
            window='synthetic:window:test.exe', mic='default', record_inputs=True,
            transcription_provider='qwen', language='zh')

    def session(self, **changes):
        folder = self.root / 'library' / '场次' / 'synthetic'
        folder.mkdir(parents=True)
        recorder.write(folder / 'session.json', dict(id='synthetic', game='Synthetic', created='synthetic',
            settings=self.cfg, state='录制中', **changes))
        return recorder.Session(folder)

    def test_capture_begins_only_after_obs_ack_on_output_clock(self):
        client, capture = MagicMock(), MagicMock()
        statuses=iter(SimpleNamespace(output_active=True,output_duration=ms) for ms in (0,0,100,200,300))
        def status():
            capture.start.assert_not_called()
            return next(statuses)
        client.get_record_status.side_effect=status
        calls = []
        client.start_record.side_effect = lambda: calls.append('obs')
        capture.start.side_effect = lambda **kwargs: calls.append('inputs')
        with patch.object(recorder, 'client', return_value=client), patch.object(recorder, 'ensure_idle'), \
             patch.object(recorder, 'configure_scene'), patch.object(recorder.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)), \
             patch('input_capture.prepare_capture', return_value=capture), patch.object(recorder.time, 'sleep'), \
             patch.object(recorder.time, 'perf_counter', side_effect=[100,100.002,100.4,100.402,100.5,100.502,100.6,100.602,100.7,100.702]):
            session = recorder.Session.start(self.cfg)
        self.assertEqual(calls, ['obs', 'inputs'])
        self.assertEqual(capture.start.call_count, 1)
        self.assertAlmostEqual(capture.start.call_args.kwargs['origin'], 100.701)
        self.assertEqual(capture.start.call_args.kwargs['video_offset'], .3)
        self.assertEqual(session.meta['input_clock']['initial_seconds'], .3)
        self.assertEqual(session.meta['input_state'], 'recording')
        client.disconnect.assert_called_once()
        self.assertTrue(session.observe_input_clock(SimpleNamespace(output_duration=700),101.1,101.102))
        capture.stop.assert_not_called()
        capture.stop.return_value = {'state': 'complete'}
        session.finish_inputs(3)

    def test_frozen_startup_clock_times_out_without_starting_listeners(self):
        from itertools import count
        client,capture=MagicMock(),MagicMock()
        client.get_record_status.return_value=SimpleNamespace(output_active=True,output_duration=0)
        capture.stop.return_value={'state':'failed'}
        with patch.object(recorder,'client',return_value=client), patch.object(recorder,'ensure_idle'), \
             patch.object(recorder,'configure_scene'), patch.object(recorder.shutil,'disk_usage',return_value=SimpleNamespace(free=10*1024**3)), \
             patch('input_capture.prepare_capture',return_value=capture), patch.object(recorder.time,'sleep'), \
             patch.object(recorder.time,'perf_counter',side_effect=count(100,.1)):
            session=recorder.Session.start(self.cfg)
        capture.start.assert_not_called()
        capture.stop.assert_called_once()
        client.disconnect.assert_called_once()
        client.stop_record.assert_not_called()
        self.assertEqual(session.meta['state'],'录制中')
        self.assertEqual(session.meta['input_state'],'failed')
        self.assertIsNone(session._input_clock_anchor)
        self.assertLessEqual(client.get_record_status.call_count,52)

    def test_startup_pause_does_not_accept_an_advancing_sample(self):
        session=self.session()
        client=MagicMock()
        with self.assertRaisesRegex(RuntimeError,'已暂停'):
            session.await_input_clock(client,SimpleNamespace(output_active=True,output_paused=True,output_duration=100),100,100.002)
        client.get_record_status.assert_not_called()
        self.assertIsNone(session._input_clock_anchor)

    def test_delayed_listener_start_marks_all_preceding_video_as_startup_gap(self):
        from input_capture import InputRecorder
        session=self.session()
        source=MagicMock()
        capture=InputRecorder(session.path,lambda:source,clock=lambda:100.73,flush_interval=60)
        self.addCleanup(capture.stop)
        session._input_capture=capture
        capture.start(origin=100.701,video_offset=.3)
        session.finish_inputs(1)
        data=recorder.read(session.path/'input-events.json')
        startup=next(gap for gap in data['gaps'] if '启动确认' in gap['reason'])
        self.assertEqual(startup['start'],0)
        self.assertAlmostEqual(startup['end'],.329)
        self.assertEqual(data['intervals'],[])

    def test_opt_out_never_prepares_native_source(self):
        from input_capture import prepare_capture
        with patch('input_capture.capture_readiness') as check:
            self.assertIsNone(prepare_capture({**self.cfg, 'record_inputs': False}, self.root))
            check.assert_not_called()

    def test_resumed_is_strict_boolean_in_desktop_and_export_public_inputs(self):
        session=self.session(media={'duration':5})
        session.update(state='可回看',transcription_state='ready')
        values=[True,False,1,'true','false',{},[],None]
        intervals=[dict(id=str(i),device='xbox',code='LeftStick',kind='axis',start=i*.3,end=i*.3+.2,
                        x=.5,y=0,resumed=value,private_field='must not cross bridge') for i,value in enumerate(values)]
        recorder.write(session.path/'input-events.json',dict(version=1,state='complete',duration=5,timebase='video_seconds',
            intervals=intervals,gaps=[dict(start=3,end=4,type='capture',reason='synthetic gap',resumed=True)]))
        recorder.write(session.path/'录像.whisper.json',dict(segments=[]))
        (session.path/'录像.mp4').write_bytes(b'synthetic media fixture')
        desktop=ReviewAPI(session.path,{}).get_snapshot()['data']['inputs']
        self.assertIs(desktop['intervals'][0]['resumed'],True)
        for row in desktop['intervals'][1:]:self.assertNotIn('resumed',row)
        for row in desktop['intervals']:self.assertNotIn('private_field',row)
        self.assertNotIn('resumed',desktop['gaps'][0])
        with patch('review_runtime.render_player',wraps=render_player) as render:
            archive=session.package()
        with zipfile.ZipFile(archive) as bundle:
            name=next(name for name in bundle.namelist() if name.endswith('/input-events.json'))
            exported=json.loads(bundle.read(name))
        self.assertEqual(exported,desktop)
        self.assertEqual(render.call_args.args[1]['inputs'],desktop)

    def test_unconfirmed_start_never_starts_listeners_and_finalizes_failure(self):
        client, capture = MagicMock(), MagicMock()
        client.get_record_status.return_value = SimpleNamespace(output_active=False)
        capture.stop.return_value = {'state': 'failed'}
        with patch.object(recorder, 'client', return_value=client), patch.object(recorder, 'ensure_idle'), \
             patch.object(recorder, 'configure_scene'), patch.object(recorder.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)), \
             patch('input_capture.prepare_capture', return_value=capture), patch.object(recorder.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, '尚未确认'):
                recorder.Session.start(self.cfg)
        capture.start.assert_not_called()
        capture.stop.assert_called_once()
        client.disconnect.assert_called_once()

    def test_capture_failure_does_not_abandon_confirmed_recording(self):
        client, capture = MagicMock(), MagicMock()
        client.get_record_status.side_effect = [SimpleNamespace(output_active=True,output_duration=ms) for ms in (200,300,400)]
        capture.start.side_effect = RuntimeError('synthetic listener failed')
        capture.stop.return_value = {'state': 'failed'}
        with patch.object(recorder, 'client', return_value=client), patch.object(recorder, 'ensure_idle'), \
             patch.object(recorder, 'configure_scene'), patch.object(recorder.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)), \
             patch('input_capture.prepare_capture', return_value=capture), patch.object(recorder.time,'sleep'), \
             patch.object(recorder.time,'perf_counter',side_effect=[100,100.002,100.1,100.102,100.2,100.202]):
            session = recorder.Session.start(self.cfg)
        capture.start.assert_called_once()
        self.assertEqual(session.meta['state'], '录制中')
        self.assertEqual(session.meta['input_state'], 'failed')
        client.stop_record.assert_not_called()

    def test_stop_releases_listeners_before_obs_request_and_media_work(self):
        session = self.session()
        client, capture = MagicMock(), MagicMock()
        session._input_capture = capture
        calls = []
        capture.stop.side_effect = lambda **kwargs: calls.append('inputs') or {'state': 'complete'}
        client.send.return_value = SimpleNamespace(record_directory=str(session.path))
        client.get_record_status.side_effect = [SimpleNamespace(output_active=True, output_duration=12000), SimpleNamespace(output_active=False)]
        client.stop_record.side_effect = lambda: calls.append('obs') or SimpleNamespace(output_path=str(session.path / 'obs.mkv'))
        client.get_input_list.return_value.inputs = []
        with patch.object(recorder, 'client', return_value=client), patch.object(session, 'adopt_recording'), \
             patch.object(session, 'prepare_video', side_effect=lambda: calls.append('media')):
            session.stop()
        self.assertEqual(calls, ['inputs', 'obs', 'media'])
        capture.stop.assert_called_once_with(duration=12, interrupted=False, error=None)
        client.disconnect.assert_called_once()

    def test_start_validation_and_stop_failures_release_owned_connections(self):
        client=MagicMock()
        with patch.object(recorder,'client',return_value=client), patch.object(recorder,'ensure_idle',side_effect=RuntimeError('synthetic busy')):
            with self.assertRaisesRegex(RuntimeError,'synthetic busy'):recorder.Session.start(self.cfg)
        client.disconnect.assert_called_once()
        client.reset_mock()
        session=self.session()
        client.send.side_effect=ConnectionError('synthetic directory query failure')
        with patch.object(recorder,'client',return_value=client):
            with self.assertRaises(ConnectionError):session.stop()
        client.disconnect.assert_called_once()

    def test_device_enumeration_failure_releases_connection(self):
        client=MagicMock()
        with patch.object(recorder,'client',return_value=client), patch.object(recorder,'ensure_idle'), patch.object(recorder,'add',side_effect=RuntimeError('synthetic failed source')):
            with self.assertRaisesRegex(RuntimeError,'synthetic failed source'):recorder.devices()
        client.disconnect.assert_called_once()

    def test_recovery_marks_gap_without_resuming_capture(self):
        session = self.session()
        recorder.write(session.path / 'input-events.json', dict(version=1, state='recording', duration=2,
            timebase='video_seconds', intervals=[], gaps=[]))
        with patch('input_capture.prepare_capture') as prepare:
            session.finish_inputs(5, interrupted=True)
            prepare.assert_not_called()
        data = recorder.read(session.path / 'input-events.json')
        self.assertEqual(data['state'], 'interrupted')
        self.assertEqual((data['gaps'][0]['start'], data['gaps'][0]['end']), (2, 5))

    def test_video_finalization_marks_uncaptured_tail_without_overwriting_intervals(self):
        session = self.session(media={'duration': 12})
        (session.path / '录像.mp4').write_bytes(b'synthetic published media')
        interval = dict(id='1', start=1, end=3, device='keyboard', code='KeyW', kind='button', label='W')
        recorder.write(session.path / 'input-events.json', dict(version=1, state='complete', duration=11.8,
            timebase='video_seconds', intervals=[interval], gaps=[]))
        with patch.object(recorder, 'probe', return_value={'duration': 12}), patch.object(recorder, 'run') as run:
            session.prepare_video()
        run.assert_not_called()
        data = recorder.read(session.path / 'input-events.json')
        self.assertEqual(data['duration'], 12)
        self.assertEqual(data['intervals'], [interval])
        self.assertEqual((data['gaps'][0]['start'], data['gaps'][0]['end']), (11.8, 12))

    def test_video_is_published_before_blocked_transcription(self):
        session = self.session()
        entered, release = threading.Event(), threading.Event()
        errors = []
        options = dict(provider='qwen', region='beijing', model='synthetic')
        def transcribe(*args):
            entered.set()
            release.wait(3)
            return [{'start': 0, 'end': 1, 'text': 'Synthetic words'}]
        def run(args, log):
            Path(args[-1]).write_bytes(b'synthetic media fixture')
        def process():
            try:session.process()
            except Exception as error:errors.append(error)
        with patch.object(session, 'adopt_recording', side_effect=lambda: session.update(media={'duration': 12}, processing_source='raw.mkv')), \
             patch.object(recorder, 'run', side_effect=run), patch.object(recorder, 'probe', return_value={'duration': 12}), \
             patch.object(recorder, 'microphone_is_silent', return_value=False), \
             patch('transcription_runtime.profile', return_value=options), patch('secret_store.load_key', return_value='synthetic'), \
             patch('qwen_transcription.transcribe', side_effect=transcribe):
            worker = threading.Thread(target=process)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue((session.path / '录像.mp4').is_file())
                self.assertTrue((session.path / '独立回看.html').is_file())
                api = ReviewAPI(session.path, {})
                self.assertEqual(api.get_snapshot()['data']['transcription']['state'], 'pending')
                self.assertTrue(api.rename_session('Named while transcribing')['ok'])
            finally:
                release.set()
                worker.join(4)
        self.assertFalse(errors, errors)
        self.assertEqual(api.get_snapshot()['data']['transcription']['state'], 'ready')
        self.assertEqual(api.get_snapshot()['data']['title'], 'Named while transcribing')

    def test_corrupt_prior_transcript_is_archived_then_replaced_by_retranscription(self):
        session=self.session()
        corrupt=b'{unfinished prior transcript'
        (session.path/'录像.whisper.json').write_bytes(corrupt)
        (session.path/'录像.mp4').write_bytes(b'existing synthetic video')
        options=dict(provider='qwen',region='beijing',model='synthetic')
        segments=[{'start':0,'end':1,'text':'Recovered transcript'}]
        with patch.object(session,'adopt_recording',side_effect=lambda:session.update(media={'duration':12},processing_source='raw.mkv')), \
             patch.object(recorder,'run',side_effect=lambda args,log:Path(args[-1]).write_bytes(b'synthetic media fixture')), \
             patch.object(recorder,'probe',return_value={'duration':12}), patch.object(recorder,'microphone_is_silent',return_value=False), \
             patch('transcription_runtime.profile',return_value=options),patch('secret_store.load_key',return_value='synthetic'), \
             patch('qwen_transcription.transcribe',return_value=segments) as transcribe:
            session.process(transcription_settings=self.cfg)
        transcribe.assert_called_once()
        backups=list((session.path/'转写版本').glob('*/录像.whisper.json'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),corrupt)
        self.assertEqual(recorder.read(session.path/'录像.whisper.json')['segments'],segments)
        self.assertEqual(session.meta['transcription_state'],'ready')

    def test_pause_trims_to_frozen_obs_duration_and_does_not_resume_inputs(self):
        session=self.session()
        capture=MagicMock()
        capture.stop.return_value={'state':'failed'}
        session._input_capture=capture
        session.observe_input_clock(SimpleNamespace(output_duration=0,output_paused=False),100,100.02)
        self.assertFalse(session.observe_input_clock(SimpleNamespace(output_duration=7000,output_paused=True),112,112.02))
        self.assertEqual(capture.stop.call_args.kwargs['trim_to'],7)
        self.assertIsNone(session._input_capture)
        self.assertFalse(session.observe_input_clock(SimpleNamespace(output_duration=9000,output_paused=False),114,114.02))
        self.assertEqual(capture.stop.call_count,1)

    def test_missed_pause_or_cumulative_drift_trims_to_last_trusted_sample(self):
        session=self.session()
        capture=MagicMock()
        capture.stop.return_value=dict(version=1,state='failed',duration=5,timebase='video_seconds',intervals=[],gaps=[])
        session._input_capture=capture
        self.assertTrue(session.observe_input_clock(SimpleNamespace(output_duration=0),100,100.02))
        self.assertTrue(session.observe_input_clock(SimpleNamespace(output_duration=5000),105,105.02))
        self.assertFalse(session.observe_input_clock(SimpleNamespace(output_duration=7000),112,112.02))
        self.assertEqual(capture.stop.call_args.kwargs['trim_to'],5)
        data=recorder.read(session.path/'input-events.json')
        self.assertEqual(data['duration'],7)
        self.assertEqual((data['gaps'][0]['start'],data['gaps'][0]['end']),(5,7))

    def test_obs_query_jitter_is_tolerated_without_moving_original_clock_anchor(self):
        session=self.session()
        capture=MagicMock()
        session._input_capture=capture
        self.assertTrue(session.observe_input_clock(SimpleNamespace(output_duration=0),100,100.1))
        # The actual OBS sample could have happened anywhere during this reply.
        self.assertTrue(session.observe_input_clock(SimpleNamespace(output_duration=5100),105,105.8))
        self.assertTrue(session.observe_input_clock(SimpleNamespace(output_duration=9950),110,110.1))
        self.assertEqual(session._input_clock_anchor,(100.05,0,.04999999999999716))
        capture.stop.assert_not_called()

    def test_unknown_obs_clock_fails_closed_at_last_trusted_video_point(self):
        session=self.session()
        capture=MagicMock();capture.stop.return_value={'state':'failed'}
        session._input_capture=capture
        self.assertTrue(session.observe_input_clock(SimpleNamespace(output_duration=4000),100,100.02))
        self.assertFalse(session.observe_input_clock(SimpleNamespace(output_duration=float('nan')),105,105.02))
        self.assertEqual(capture.stop.call_args.kwargs['trim_to'],4)

    def test_pause_actually_trims_collected_intervals_and_final_media_extends_gap(self):
        from input_capture import InputRecorder
        session=self.session(media={'duration':12})
        clock=SimpleNamespace(value=100.)
        source=MagicMock()
        capture=InputRecorder(session.path,lambda:source,clock=lambda:clock.value,flush_interval=60)
        session._input_capture=capture
        session.observe_input_clock(SimpleNamespace(output_duration=0),100,100)
        capture.start(origin=100)
        self.addCleanup(capture.stop)
        capture.feed(dict(type='focus',timestamp=100,foreground=True))
        for seconds,code,down in [(1,'A',True),(2,'A',False),(6,'B',True),(11,'C',True),(13,'C',False)]:
            clock.value=100+seconds
            capture.feed(dict(type='button',device='keyboard',code=code,down=down,timestamp=clock.value,foreground=True))
        clock.value=114
        session.observe_input_clock(SimpleNamespace(output_duration=7000,output_paused=True),114,114)
        data=recorder.read(session.path/'input-events.json')
        self.assertEqual([(i['code'],i['start'],i['end']) for i in data['intervals']],[('A',1,2),('B',6,7)])
        self.assertEqual(data['duration'],7)
        source.stop.assert_called_once()
        (session.path/'录像.mp4').write_bytes(b'synthetic published media')
        with patch.object(recorder,'probe',return_value={'duration':12}):session.prepare_video()
        data=recorder.read(session.path/'input-events.json')
        self.assertEqual((data['gaps'][-1]['start'],data['gaps'][-1]['end']),(7,12))
        self.assertIn('没有可靠操作数据',data['gaps'][-1]['reason'])

    def test_restart_recovers_only_last_verified_clock_and_preserves_completed_capture(self):
        session=self.session(input_clock={'last_verified_seconds':3})
        recorder.write(session.path/'input-events.json',dict(version=1,state='recording',duration=5,timebase='video_seconds',
            intervals=[dict(id='a',device='keyboard',code='A',kind='button',start=2,end=4)],gaps=[]))
        session.finish_inputs(5,interrupted=True)
        data=recorder.read(session.path/'input-events.json')
        self.assertEqual(data['intervals'][0]['end'],3)
        self.assertEqual((data['gaps'][0]['start'],data['gaps'][0]['end']),(3,5))
        # A later transcription interruption is unrelated to already finalized input.
        data['state']='complete'
        recorder.write(session.path/'input-events.json',data)
        before=(session.path/'input-events.json').read_bytes()
        session.update(state='转写中')
        session.finish_inputs(interrupted=True,error='transcription interrupted')
        self.assertEqual((session.path/'input-events.json').read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
