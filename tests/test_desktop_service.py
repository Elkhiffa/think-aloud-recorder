"""Synthetic bridge tests: never capture media, query a real OBS, or upload audio."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import desktop_service as bridge
import hotword_files


class DesktopServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / 'library'
        self.vault.mkdir()
        obs = self.root / 'tools/obs/bin/64bit/obs64.exe'
        obs.parent.mkdir(parents=True)
        obs.write_bytes(b'synthetic fixture, never executed')
        self.devices = {
            'window': [{'itemName': 'Synthetic window', 'itemValue': 'window-id', 'itemEnabled': True}],
            'monitor': [{'itemName': 'Synthetic monitor', 'itemValue': 'monitor-id', 'itemEnabled': True}],
            'mic': [{'itemName': 'Synthetic microphone', 'itemValue': 'mic-id', 'itemEnabled': True}],
        }
        self.actual_probe = bridge.DesktopService._probe_obs_devices
        self.config = dict(vault=str(self.vault), game='Synthetic game', preset='均衡 1080p30',
                           source='游戏窗口', window='window-id', monitor='', mic='mic-id',
                           language='zh', hotwords='', transcription_provider='later',
                           obsidian_exe='', configured=True, games={}, model='large-v3',
                           device='cpu', compute_type='float32', password='private-obs-password', port=54981)
        self.model = MagicMock()
        self.model.status.return_value = dict(state='missing', model='large-v3', path=None,
            downloaded_bytes=0, total_bytes=100, error=None, source=None, revision='pinned')
        self.model.resolve_model.return_value = None
        self.model.wait.return_value = True
        self.model.start_download.return_value = {'ok': True}
        self.patches = [
            patch.object(bridge, 'load_settings', return_value=deepcopy(self.config)),
            patch.object(bridge, 'ModelManager', return_value=self.model),
            patch.object(bridge.recorder, 'client', side_effect=ConnectionRefusedError('offline')),
            patch.object(bridge.secret_store, 'has_key', return_value=False),
            patch.object(bridge.DesktopService, '_monitor_loop', return_value=None),
            patch.object(bridge.DesktopService, '_probe_obs_devices', side_effect=lambda: (deepcopy(self.devices), None)),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        self.service = bridge.DesktopService(self.root)
        self.wait()
        self.addCleanup(self.shutdown)

    def shutdown(self):
        self.service._closed.set()
        self.wait()

    def wait(self):
        if self.service._job:
            self.service._job.join(5)
            self.assertFalse(self.service._job.is_alive(), 'synthetic job did not finish')
        if self.service._readiness_thread:
            self.service._readiness_thread.join(5)
            self.assertFalse(self.service._readiness_thread.is_alive(), 'synthetic readiness did not finish')

    def session(self, ident='synthetic-1', **extra):
        path = self.vault / '场次' / (ident + ' fixture')
        path.mkdir(parents=True, exist_ok=True)
        data = dict(id=ident, game=self.config['game'], created='2026-09-20T08:00:00+08:00',
                    state='待整理', settings={k: v for k, v in self.config.items() if k not in ('password', 'port', 'vault')},
                    test=True, media={'duration': 12.5}, started=1)
        data.update(extra)
        bridge.recorder.write(path / 'session.json', data)
        return bridge.recorder.Session(path)

    def test_record_only_start_does_not_require_model_or_cloud(self):
        session = self.session(test=False)
        with patch.object(bridge.recorder.Session, 'start', return_value=session) as start:
            result = self.service.start_recording({})
            self.assertTrue(result['ok'])
            self.wait()
        self.assertIs(self.service._active, session)
        self.assertEqual(self.service.get_state()['data']['activity']['kind'], 'recording')
        self.model.resolve_model.assert_not_called()
        self.assertEqual(len(start.call_args.args), 1)
        self.assertNotIn('test_file', start.call_args.kwargs)

    def test_finished_startup_recovery_reports_ready_and_keeps_existing_errors(self):
        activity = self.service.get_state()['data']['activity']
        self.assertFalse(activity['busy'])
        self.assertEqual(activity['kind'], 'idle')
        self.assertEqual(activity['status'], '待开始')
        self.service._progress('previous operation failed', status='操作未完成')
        self.service._recover()
        activity = self.service.get_state()['data']['activity']
        self.assertEqual(activity['status'], '操作未完成')
        self.assertEqual(activity['detail'], 'previous operation failed')

    def test_record_only_stop_saves_without_transcribing(self):
        session = self.session(state='录制中')
        self.service._active = session
        with patch.object(session, 'stop') as stop, patch.object(bridge, 'process_isolated') as process:
            self.assertTrue(self.service.stop_recording()['ok'])
            self.wait()
        stop.assert_called_once()
        process.assert_not_called()
        self.assertIsNone(self.service._active)
        self.assertEqual(bridge.recorder.Session(session.path).meta['state'], '待整理')

    def test_failed_stop_retains_ownership_when_obs_unreachable(self):
        session = self.session(state='录制中')
        self.service._active = session
        with patch.object(session, 'stop', side_effect=ConnectionError('lost stop acknowledgement')):
            self.service.stop_recording()
            self.wait()
        self.assertIs(self.service._active, session)
        self.assertFalse(self.service.start_recording({})['ok'])
        self.assertFalse(self.service.close_allowed())

    def test_start_lost_acknowledgement_preserves_uncertain_ownership(self):
        def failed_start(cfg):
            self.session('new-start', state='失败', test=False, error='acknowledgement lost')
            raise ConnectionError('lost start acknowledgement')
        with patch.object(bridge.recorder.Session, 'start', side_effect=failed_start):
            self.service.start_recording({})
            self.wait()
        self.assertIn('new-start', self.service._uncertain_ids)
        self.assertFalse(self.service.start_recording({})['ok'])
        self.assertFalse(self.service.close_allowed())

    def test_failed_stop_releases_only_after_confirmed_inactive(self):
        session = self.session(state='录制中')
        self.service._active = session
        client = MagicMock()
        client.get_record_status.return_value.output_active = False
        with patch.object(session, 'stop', side_effect=RuntimeError('bad media')), \
                patch.object(bridge.recorder, 'client', return_value=client):
            self.service.stop_recording()
            self.wait()
        self.assertIsNone(self.service._active)
        self.assertEqual(bridge.recorder.Session(session.path).meta['state'], '失败')

    def test_job_admission_is_atomic(self):
        entered, release = threading.Event(), threading.Event()
        def operation():
            entered.set()
            release.wait(3)
        try:
            self.assertTrue(self.service._launch('processing', operation)['ok'])
            self.assertTrue(entered.wait(2))
            self.assertFalse(self.service._launch('export', lambda: None)['ok'])
            self.assertFalse(self.service.save_settings({'game': 'changed'})['ok'])
            self.assertFalse(self.service.close_allowed())
        finally:
            release.set()
            self.wait()

    def test_session_ids_and_ambiguous_ids_cannot_escape_vault(self):
        self.session()
        for value in ('../outside', str(self.root), 'synthetic-1/../outside', '', None):
            with self.assertRaises(ValueError):
                self.service._session(value)
        duplicate = self.vault / '场次' / 'duplicate'
        duplicate.mkdir()
        bridge.recorder.write(duplicate / 'session.json', {'id': 'synthetic-1'})
        with self.assertRaises(ValueError):
            self.service._session('synthetic-1')

    def test_setting_validation_preserves_existing_config_on_failure(self):
        for payload in ({'vault': str(self.vault / '.obsidian')}, {'vault': 'relative'},
                        {'vault': str(self.root / 'runtime' / 'library')}, {'source': 'synthetic'},
                        {'language': 'unsafe'}, {'test_file': 'example.mkv'},
                        {'password': 'changed'}, {'port': '1234'}):
            with self.subTest(payload=payload):
                self.assertFalse(self.service.save_settings(payload)['ok'])
        self.assertEqual(self.service._cfg['password'], self.config['password'])
        self.assertFalse((self.root / 'config.json').exists())

    def test_snapshot_whitelists_nested_presets_and_session_fields(self):
        self.service._cfg['games'] = {'Synthetic game': {'password': 'nested-secret', 'port': 1234, 'mic': 'mic-id'}}
        self.session(error='failure sk-abcdsecretxyz private-obs-password at 127.0.0.1:54981', credentials={'key': 'session-secret'})
        snapshot = self.service.get_state()
        encoded = json.dumps(snapshot)
        self.assertNotIn('private-obs-password', encoded)
        self.assertNotIn('nested-secret', encoded)
        self.assertNotIn('session-secret', encoded)
        self.assertNotIn('sk-abcdsecretxyz', encoded)
        self.assertNotIn('54981', encoded)
        self.assertNotIn('"port"', encoded)
        self.assertNotIn('"password"', encoded)
        self.assertEqual(snapshot['data']['devices'], self.devices)

    def test_dpapi_save_never_returns_or_writes_plaintext_key(self):
        with patch.object(bridge.secret_store, 'save_key') as save:
            result = self.service.save_cloud_key('synthetic-sensitive-key')
        self.assertEqual(result, {'ok': True, 'data': {'saved': True}})
        save.assert_called_once_with('synthetic-sensitive-key', directory=self.root / 'state/secrets')
        self.assertFalse((self.root / 'config.json').exists())

    def test_transcription_requires_opt_in_and_preserves_version_path(self):
        session = self.session(state='可回看')
        with patch.object(bridge, 'process_isolated') as process:
            self.service.process_session(session.meta['id'])
            self.wait()
            process.assert_not_called()
            self.assertIn('仅录制', self.service.get_state()['data']['activity']['detail'])
            self.service._cfg['transcription_provider'] = 'local'
            self.model.resolve_model.return_value = self.root / 'model'
            self.service.process_session(session.meta['id'])
            self.wait()
        self.assertEqual(process.call_count, 1)
        self.assertEqual(process.call_args.kwargs['transcription_settings']['transcription_provider'], 'local')

    def test_uncertain_cloud_submission_blocks_changed_settings(self):
        session = self.session()
        bridge.recorder.write(session.path / '转写原始/old/云端任务.json', {'state': 'SUBMITTING'})
        self.service._cfg['transcription_provider'] = 'local'
        self.model.resolve_model.return_value = self.root / 'model'
        with patch.object(bridge, 'process_isolated') as process:
            self.service.process_session(session.meta['id'])
            self.wait()
        process.assert_not_called()
        self.assertIn('结果不明', self.service.get_state()['data']['activity']['detail'])

    def test_cloud_recovery_uses_original_settings_and_existing_cache(self):
        session = self.session(transcription_cache='转写原始/original')
        session.meta['settings']['transcription_provider'] = 'qwen'
        session.update(settings=session.meta['settings'])
        job = session.path / '转写原始/original/云端任务.json'
        bridge.recorder.write(job, {'state': 'SUBMITTING', 'fingerprint': 'unchanged'})
        self.service._cfg['transcription_provider'] = 'local'
        with patch.object(bridge.secret_store, 'has_key', return_value=True), \
             patch.object(bridge, 'process_isolated') as process:
            self.assertTrue(self.service.recover_cloud_task(session.meta['id'], 'existing-task-id')['ok'])
            self.wait()
        process.assert_called_once()
        self.assertEqual(process.call_args.kwargs, {})
        restored = bridge.recorder.read(job)
        self.assertEqual(restored['task_id'], 'existing-task-id')
        self.assertEqual(restored['fingerprint'], 'unchanged')

    def test_cloud_recovery_rejects_outside_cache_and_task_replacement(self):
        session = self.session(transcription_cache='../outside')
        session.meta['settings']['transcription_provider'] = 'qwen'
        session.update(settings=session.meta['settings'])
        with patch.object(bridge.secret_store, 'has_key', return_value=True), \
             patch.object(bridge, 'process_isolated') as process:
            self.service.recover_cloud_task(session.meta['id'], 'new-task')
            self.wait()
            process.assert_not_called()
            self.assertIn('路径无效', self.service.get_state()['data']['activity']['detail'])
            session.update(transcription_cache='转写原始/original')
            job = session.path / '转写原始/original/云端任务.json'
            bridge.recorder.write(job, {'state': 'PENDING', 'task_id': 'old-task'})
            self.service.recover_cloud_task(session.meta['id'], 'new-task')
            self.wait()
            process.assert_not_called()
            self.assertEqual(bridge.recorder.read(job)['task_id'], 'old-task')

    def test_review_distinguishes_plugin_ack_from_browser_request(self):
        session = self.session(state='可回看')
        with patch.object(bridge.recorder, 'open_review', return_value='obsidian'):
            self.service.open_review(session.meta['id'])
            self.wait()
            self.assertIn('插件已确认', self.service.get_state()['data']['activity']['detail'])
        with patch.object(bridge.recorder, 'open_review', return_value='browser-requested'):
            self.service.open_review(session.meta['id'])
            self.wait()
            self.assertIn('未确认', self.service.get_state()['data']['activity']['detail'])

    def test_external_processing_lock_is_not_clobbered_during_recovery(self):
        import msvcrt
        session = self.session(state='转写中')
        with (session.path / '.processing.lock').open('a+b') as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                self.service._recover()
                self.assertEqual(bridge.recorder.Session(session.path).meta['state'], '转写中')
                self.assertEqual(self.service.get_state()['data']['activity']['status'], '场次正在后台整理')
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def test_recovery_only_adopts_own_non_test_session(self):
        owned = self.session(test=False, state='录制中')
        client = MagicMock()
        client.get_record_status.return_value.output_active = True
        client.send.return_value.record_directory = str(owned.path)
        with patch.object(bridge.recorder, 'client', return_value=client):
            self.service._recover()
        self.assertEqual(self.service._active.path, owned.path)
        self.service._active = None
        owned.update(test=True)
        with patch.object(bridge.recorder, 'client', return_value=client):
            self.service._recover()
        self.assertIsNone(self.service._active)

    def test_interrupted_recording_uncertainty_survives_restart(self):
        session = self.session(test=False, state='录制中')
        self.service._recover()
        self.assertTrue(bridge.recorder.Session(session.path).meta['recording_uncertain'])
        self.service._uncertain_ids.clear()
        self.service._recover()
        self.assertIn(session.meta['id'], self.service._uncertain_ids)
        self.assertFalse(self.service.close_allowed())
        self.assertFalse(self.service.save_settings({'vault': str(self.root / 'new-vault')})['ok'])

    def test_recovery_active_status_without_directory_is_unknown_not_idle(self):
        session = self.session(test=False, state='录制中')
        client = MagicMock()
        client.get_record_status.return_value.output_active = True
        client.send.side_effect = bridge.OBSSDKError('directory acknowledgement lost')
        with patch.object(bridge.recorder, 'client', return_value=client):
            self.service._recover()
        self.assertTrue(self.service._obs_uncertain)
        self.assertTrue(bridge.recorder.Session(session.path).meta['recording_uncertain'])
        self.assertIn(session.meta['id'], self.service._uncertain_ids)
        self.assertFalse(self.service.close_allowed())
        self.assertFalse(self.service.start_recording({})['ok'])
        # Losing the entire connection afterward is not proof of an idle OBS.
        self.service._recover()
        self.assertTrue(self.service._obs_uncertain)
        client.get_record_status.return_value.output_active = False
        with patch.object(bridge.recorder, 'client', return_value=client):
            self.service._recover()
        self.assertFalse(self.service._obs_uncertain)
        self.assertNotIn(session.meta['id'], self.service._uncertain_ids)
        self.assertFalse(bridge.recorder.Session(session.path).meta['recording_uncertain'])
        self.assertTrue(self.service.close_allowed())

    def test_unknown_active_directory_blocks_exit_even_without_local_sessions(self):
        client = MagicMock()
        client.get_record_status.return_value.output_active = True
        client.send.side_effect = ConnectionError('lost directory')
        with patch.object(bridge.recorder, 'client', return_value=client):
            self.service._recover()
        self.assertFalse(self.service.close_allowed())
        self.assertFalse(self.service.save_settings({'game': 'different'})['ok'])

    def test_foreign_obs_recording_is_not_stopped_by_health_check(self):
        session = self.session(state='录制中')
        self.service._active = session
        client = MagicMock()
        client.get_record_status.return_value.output_active = True
        client.send.return_value.record_directory = str(self.root / 'other-session')
        with patch.object(bridge.recorder, 'client', return_value=client), patch.object(session, 'stop') as stop:
            self.service._inspect_recording()
        stop.assert_not_called()
        self.assertIsNone(self.service._active)
        self.assertEqual(bridge.recorder.Session(session.path).meta['state'], '失败')

    def test_low_disk_stops_owned_recording_without_transcribing(self):
        session = self.session(state='录制中')
        self.service._active = session
        client = MagicMock()
        client.get_record_status.return_value.output_active = True
        client.send.return_value.record_directory = str(session.path)
        with patch.object(bridge.recorder, 'client', return_value=client), \
             patch.object(bridge.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)), \
             patch.object(session, 'stop') as stop, patch.object(bridge, 'process_isolated') as process:
            self.service._inspect_recording()
        stop.assert_called_once()
        process.assert_not_called()
        self.assertIsNone(self.service._active)
        self.assertEqual(bridge.recorder.Session(session.path).meta['state'], '待整理')

    def test_model_errors_propagate_and_close_waits_for_file_writes(self):
        self.model.start_download.return_value = {'ok': False, 'error': 'model mismatch'}
        self.assertEqual(self.service.model_action('download')['error'], 'model mismatch')
        self.model.wait.return_value = False
        self.model.status.return_value['state'] = 'paused'
        window = MagicMock()
        self.service.set_window(window)
        self.assertFalse(self.service.close_allowed())
        window.minimize.assert_not_called()  # Native shell owns asynchronous minimization.
        self.model.wait.return_value = True
        self.assertTrue(self.service.close_allowed())

    def test_picker_and_hotword_import_do_not_save_settings(self):
        words = self.root / 'fixture.txt'
        words.write_text('测试术语\n测试术语\nAnother term', encoding='utf-8')
        with patch.object(self.service, '_dialog', return_value=(str(words),)):
            result = self.service.import_hotwords()
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['count'], 2)
        self.assertEqual(self.service._cfg['hotwords'], '')
        with patch.object(self.service, '_dialog', return_value=(str(self.vault),)):
            self.assertEqual(self.service.choose_directory('vault')['data']['path'], str(self.vault))
        self.assertFalse((self.root / 'config.json').exists())

    def test_import_merges_current_draft_and_keeps_deletions_and_cancelled_draft(self):
        self.service._cfg['hotwords'] = 'previously deleted word'
        incoming = self.root / 'incoming.txt'
        incoming.write_text('new imported word', encoding='utf-8')
        with patch.object(self.service, '_dialog', return_value=(str(incoming),)):
            result = self.service.import_hotwords('unsaved draft word')
        self.assertEqual(result['data']['text'], 'unsaved draft word\nnew imported word')
        self.assertEqual(result['data']['count'], 1)
        self.assertEqual(self.service._cfg['hotwords'], 'previously deleted word')
        with patch.object(self.service, '_dialog', return_value=()):
            result = self.service.import_hotwords('unsaved draft word')
        self.assertEqual(result['data'], {'text': 'unsaved draft word', 'count': 0})

    def test_import_rejects_invalid_or_oversized_draft_before_native_picker(self):
        with patch.object(self.service, '_dialog') as dialog:
            self.assertFalse(self.service.import_hotwords({'bad': 'type'})['ok'])
            self.assertFalse(self.service.import_hotwords('x' * 128001)['ok'])
        dialog.assert_not_called()

    def test_obs_sdk_disconnect_allows_saved_media_but_not_uncertain_recording(self):
        session = self.session()
        for exception in (bridge.OBSSDKError('not running'), bridge.WebSocketException('closed')):
            with patch.object(bridge.recorder, 'client', side_effect=exception):
                self.service._ensure_not_recording(session)
                session.update(recording_uncertain=True)
                with self.assertRaisesRegex(RuntimeError, '尚无法确认'):
                    self.service._ensure_not_recording(session)
                session.update(recording_uncertain=False)

    def readiness(self):
        with self.service._operation_lock:
            return self.service._update_readiness()

    def test_readiness_tracks_disappearance_and_reappearance_with_labels(self):
        self.assertTrue(self.readiness()['ready'])
        available = deepcopy(self.devices)
        self.devices['window'] = []
        self.devices['mic'] = []
        state = self.readiness()
        self.assertFalse(state['ready'])
        self.assertEqual({x['code'] for x in state['errors']}, {'WINDOW_UNAVAILABLE', 'MIC_UNAVAILABLE'})
        self.assertTrue(all(x['step'] == 1 for x in state['errors']))
        self.assertIn('Synthetic window', str(state['errors']))
        self.assertIn('Synthetic microphone', str(state['errors']))
        self.devices.update(available)
        self.assertTrue(self.readiness()['ready'])

    def test_readiness_distinguishes_cloud_key_missing_and_unreadable(self):
        self.service._cfg['transcription_provider'] = 'qwen'
        self.assertEqual(self.readiness()['errors'][0]['code'], 'CLOUD_KEY_MISSING')
        key = self.root / 'state/secrets/dashscope-beijing.dpapi'
        key.parent.mkdir(parents=True)
        key.write_bytes(b'invalid synthetic encrypted blob')
        state = self.readiness()
        self.assertEqual(state['errors'][0]['code'], 'CLOUD_KEY_UNREADABLE')
        self.assertEqual(state['errors'][0]['step'], 2)
        with patch.object(bridge.secret_store, 'has_key', return_value=True):
            self.assertTrue(self.readiness()['ready'])

    def test_readiness_local_requires_model_but_later_does_not(self):
        self.service._cfg['transcription_provider'] = 'local'
        self.assertEqual(self.readiness()['errors'][0]['code'], 'LOCAL_MODEL_MISSING')
        self.model.resolve_model.return_value = self.root / 'verified-model'
        self.assertTrue(self.readiness()['ready'])
        self.service._cfg['transcription_provider'] = 'later'
        self.model.resolve_model.return_value = None
        self.assertTrue(self.readiness()['ready'])

    def test_readiness_requires_saved_preset_and_checks_real_output_access(self):
        self.service._cfg['active_preset_id'] = None
        self.assertIn('SETUP_REQUIRED', {x['code'] for x in self.readiness()['errors']})
        self.service._cfg['active_preset_id'] = 'legacy'
        with patch.object(self.service, '_probe_location', side_effect=PermissionError('denied')):
            error = self.readiness()['errors'][0]
            self.assertEqual((error['code'], error['step']), ('OUTPUT_UNAVAILABLE', 3))
        with patch.object(self.service, '_probe_location', return_value=100):
            self.assertEqual(self.readiness()['errors'][0]['code'], 'OUTPUT_SPACE_LOW')

    def test_saving_disconnected_choice_keeps_preset_but_disables_start(self):
        result = self.service.save_settings({'window': 'Closed window:Class:closed.exe'})
        self.assertTrue(result['ok'])
        self.wait()
        state = self.service.get_state()['data']
        self.assertEqual(state['config']['window'], 'Closed window:Class:closed.exe')
        self.assertFalse(state['readiness']['ready'])
        self.assertIn('closed.exe', str(state['readiness']['errors']))

    def test_start_rechecks_saved_setup_and_rejects_unsaved_payload(self):
        self.assertTrue(self.readiness()['ready'])
        self.assertFalse(self.service.start_recording({'window': 'new window'})['ok'])
        self.devices['window'] = []
        with patch.object(bridge.recorder.Session, 'start') as start:
            self.assertTrue(self.service.start_recording({})['ok'])
            self.wait()
        start.assert_not_called()
        self.assertFalse(self.service.get_state()['data']['readiness']['ready'])
        self.assertIn('未打开', self.service.get_state()['data']['activity']['detail'])

    def test_background_check_does_not_block_snapshot_or_flash_job(self):
        entered, release = threading.Event(), threading.Event()
        def probe():
            entered.set()
            release.wait(3)
            return deepcopy(self.devices), None
        with patch.object(self.service, '_probe_obs_devices', side_effect=probe):
            try:
                self.assertTrue(self.service._request_readiness())
                self.assertTrue(entered.wait(2))
                began = time.monotonic()
                state = self.service.get_state()['data']
                self.assertLess(time.monotonic() - began, .5)
                self.assertFalse(state['activity']['busy'])
                self.assertEqual(state['activity']['kind'], 'idle')
                self.assertFalse(state['readiness']['checking'])
                self.assertTrue(state['readiness']['ready'])
            finally:
                release.set()
                self.wait()
        self.assertTrue(self.service.get_state()['data']['readiness']['ready'])

    def test_capture_waits_for_probe_then_rechecks_before_mutating_obs(self):
        entered, release = threading.Event(), threading.Event()
        calls = []
        def probe():
            calls.append('probe')
            if len(calls) == 1:
                entered.set()
                release.wait(3)
                return deepcopy(self.devices), None
            return {**deepcopy(self.devices), 'window': []}, None
        with patch.object(self.service, '_probe_obs_devices', side_effect=probe), \
             patch.object(bridge.recorder.Session, 'start') as capture:
            try:
                self.service._request_readiness()
                self.assertTrue(entered.wait(2))
                self.service.start_recording({})
                capture.assert_not_called()
            finally:
                release.set()
                self.wait()
            self.assertEqual(len(calls), 2)
            capture.assert_not_called()

    def test_idle_probe_does_not_release_recording_or_run_during_job(self):
        session = self.session(state='录制中')
        self.service._active = session
        self.assertFalse(self.service._request_readiness())
        self.assertIs(self.service._active, session)
        self.service._active = None
        self.service._activity['busy'] = True
        self.assertFalse(self.service._request_readiness())
        self.service._activity['busy'] = False

    def test_actual_obs_probe_never_adds_inputs_to_busy_recording(self):
        client = MagicMock()
        client.get_record_status.return_value.output_active = True
        with patch.object(bridge.recorder, 'client', return_value=client):
            devices, error = self.actual_probe(self.service)
        self.assertIsNone(devices)
        self.assertEqual(error[0], 'OBS_BUSY')
        client.create_input.assert_not_called()
        client.remove_input.assert_not_called()
        client.stop_record.assert_not_called()
        client.set_current_scene_collection.assert_not_called()

    def test_native_picker_keeps_poll_responsive_and_blocks_capture(self):
        entered, release = threading.Event(), threading.Event()
        window = MagicMock()
        def choose(*args, **kwargs):
            entered.set()
            release.wait(3)
            return ()
        window.create_file_dialog.side_effect = choose
        self.service.set_window(window)
        with patch.dict('sys.modules', {'webview': SimpleNamespace(FOLDER_DIALOG=1, OPEN_DIALOG=2)}):
            thread = threading.Thread(target=lambda: self.service.choose_directory('vault'))
            try:
                thread.start()
                self.assertTrue(entered.wait(2))
                began = time.monotonic()
                self.assertTrue(self.service.get_state()['ok'])
                self.assertLess(time.monotonic() - began, .5)
                self.assertFalse(self.service.start_recording({})['ok'])
            finally:
                release.set()
                thread.join(3)

    def test_full_presets_isolate_vault_and_transcription_and_private_config(self):
        first = self.service._cfg['active_preset_id']
        self.session('first-session')
        result = self.service.save_preset({'name': 'Second project', 'vault': str(self.root / 'second-library'),
                                          'source': '整个显示器', 'monitor': 'monitor-id',
                                          'transcription_provider': 'qwen', 'hotwords': 'Second term'})
        self.assertTrue(result['ok'], result)
        second = result['data']['id']
        self.wait()
        snapshot = self.service.get_state()['data']
        self.assertEqual(snapshot['active_preset_id'], second)
        self.assertEqual(snapshot['sessions'], [])
        self.assertEqual(snapshot['config']['source'], '整个显示器')
        self.assertEqual(snapshot['config']['transcription_provider'], 'qwen')
        self.assertEqual(len(snapshot['presets']), 2)
        stored = bridge.recorder.read(self.root / 'config.json')
        self.assertEqual(stored['password'], self.config['password'])
        self.assertNotIn('password', json.dumps(stored['presets']))
        self.assertNotIn('port', json.dumps(stored['presets']))
        self.assertTrue(self.service.select_preset(first)['ok'])
        self.wait()
        snapshot = self.service.get_state()['data']
        self.assertEqual(snapshot['config']['vault'], str(self.vault))
        self.assertEqual(snapshot['config']['transcription_provider'], 'later')
        self.assertEqual(snapshot['sessions'][0]['id'], 'first-session')
        self.assertTrue(snapshot['readiness']['ready'])

    def test_editing_nonactive_preset_preserves_its_settings_and_switch_is_guarded(self):
        first = self.service._cfg['active_preset_id']
        second = self.service.save_preset({'name': 'Second', 'vault': str(self.root / 'second'),
                                          'language': 'en'})['data']['id']
        self.wait()
        result = self.service.save_preset({'name': 'Renamed first'}, first)
        self.assertTrue(result['ok'], result)
        self.wait()
        self.assertEqual(self.service._cfg['vault'], str(self.vault))
        self.assertEqual(self.service._cfg['language'], 'zh')
        self.service._active = self.session(state='录制中')
        self.assertFalse(self.service.select_preset(second)['ok'])
        self.assertEqual(self.service._cfg['active_preset_id'], first)

    def test_renamed_same_name_presets_cannot_change_historical_transcription_vocabulary(self):
        legacy_games = {'Legacy entry': {'language': 'ja', 'hotwords': 'legacy words'}}
        self.service._cfg['games'] = deepcopy(legacy_games)
        first = self.service.save_preset({'name': 'Same game', 'language': 'zh', 'hotwords': 'Alpha'})['data']['id']
        self.wait()
        session = self.session('historical-a', game='Same game', settings={
            'game': 'Same game', 'language': 'zh', 'hotwords': 'Alpha',
            'transcription_provider': 'later', 'model': 'large-v3',
            'device': 'cpu', 'compute_type': 'float32',
        })
        second = self.service.save_preset({'name': 'Same game', 'vault': str(self.root / 'vault-b'),
                                          'language': 'en', 'hotwords': 'Beta'})['data']['id']
        self.wait()
        self.assertNotEqual(first, second)
        self.assertEqual(self.service._cfg['games'], legacy_games)
        # Also retain a contaminated map written by older versions: reading it
        # must not change this historical session's language or vocabulary.
        self.service._cfg['games']['Same game'] = {'language': 'en', 'hotwords': 'Beta'}
        self.model.resolve_model.return_value = self.root / 'verified-model'
        renamed = self.service.save_preset({'name': 'Alpha renamed', 'transcription_provider': 'local',
                                            'language': 'ja', 'hotwords': 'New preset terms'}, first)
        self.assertTrue(renamed['ok'], renamed)
        self.wait()
        with patch.object(bridge, 'process_isolated') as process:
            self.assertTrue(self.service.process_session(session.meta['id'])['ok'])
            self.wait()
        process.assert_called_once()
        settings = process.call_args.kwargs['transcription_settings']
        self.assertEqual(settings['language'], 'zh')
        self.assertEqual(settings['hotwords'], 'Alpha')
        self.assertEqual(settings['transcription_provider'], 'local')
        self.assertEqual(self.service._cfg['presets'][second]['hotwords'], 'Beta')
        self.assertEqual(bridge.recorder.Session(session.path).meta['settings']['hotwords'], 'Alpha')

    def test_unconfigured_legacy_migrates_no_presets_and_does_not_guess_games(self):
        self.service._cfg.pop('presets')
        self.service._cfg['configured'] = False
        self.service._cfg['games'] = {'Old partial game': {'mic': 'unknown'}}
        self.service._initialize_presets()
        self.assertEqual(self.service._cfg['presets'], {})
        self.assertIsNone(self.service._cfg['active_preset_id'])
        self.assertFalse(self.service.start_recording({})['ok'])

    def test_saved_setup_initializes_private_obs_once_on_startup(self):
        self.service._startup_launch_attempted = False
        client = MagicMock()
        def connect(*args, **kwargs):
            self.service._progress('正在启动录制引擎，请稍候…')
            return client
        with patch.object(self.service, '_recover'), \
             patch.object(bridge.recorder, 'client', side_effect=connect) as launch:
            self.service._startup()
            self.service._startup()
            launch.assert_called_once_with(launch=True, progress=self.service._progress)
        self.assertTrue(self.service.get_state()['data']['readiness']['ready'])
        self.assertEqual(self.service.get_state()['data']['activity']['detail'], '')
        client.disconnect.assert_called_once()

    def test_startup_launch_failure_not_retried_by_periodic_checks(self):
        self.service._startup_launch_attempted = False
        with patch.object(self.service, '_recover'), \
             patch.object(bridge.recorder, 'client', side_effect=OSError('unavailable')) as launch, \
             patch.object(self.service, '_probe_obs_devices', side_effect=OSError('unavailable')):
            self.service._startup()
            self.service._request_readiness()
            self.wait()
            self.service._request_readiness()
            self.wait()
        self.assertEqual(launch.call_count, 1)
        state = self.service.get_state()['data']['readiness']
        self.assertFalse(state['ready'])
        self.assertEqual(state['errors'][0]['code'], 'OBS_UNAVAILABLE')

    def test_startup_never_launches_with_unconfirmed_recording_or_without_setup(self):
        for condition in ('unknown', 'active', 'no_setup'):
            with self.subTest(condition=condition):
                self.service._startup_launch_attempted = False
                self.service._obs_uncertain = condition == 'unknown'
                self.service._active = self.session() if condition == 'active' else None
                self.service._cfg['active_preset_id'] = None if condition == 'no_setup' else 'legacy'
                with patch.object(self.service, '_recover'), patch.object(bridge.recorder, 'client') as launch:
                    self.service._startup()
                launch.assert_not_called()

    def test_routine_cached_success_expires_if_probe_stalls(self):
        entered, release = threading.Event(), threading.Event()
        def probe():
            entered.set()
            release.wait(3)
            return deepcopy(self.devices), None
        self.assertTrue(self.readiness()['ready'])
        with patch.object(self.service, '_probe_obs_devices', side_effect=probe):
            try:
                self.service._request_readiness()
                self.assertTrue(entered.wait(2))
                state = self.service.get_state()['data']['readiness']
                self.assertTrue(state['ready'])
                self.assertFalse(state['checking'])
                with self.service._lock:
                    self.service._readiness['checked_at'] = time.time() - 16
                began = time.monotonic()
                stale = self.service.get_state()['data']['readiness']
                self.assertLess(time.monotonic() - began, .5)
                self.assertFalse(stale['ready'])
                self.assertTrue(stale['checking'])
                self.assertEqual(stale['errors'][0]['code'], 'READINESS_STALE')
            finally:
                release.set()
                self.wait()
        self.assertTrue(self.service.get_state()['data']['readiness']['ready'])

    def test_routine_check_never_enables_last_failed_result(self):
        self.devices['window'] = []
        self.assertFalse(self.readiness()['ready'])
        entered, release = threading.Event(), threading.Event()
        def probe():
            entered.set()
            release.wait(3)
            return deepcopy(self.devices), None
        with patch.object(self.service, '_probe_obs_devices', side_effect=probe):
            try:
                self.service._request_readiness()
                self.assertTrue(entered.wait(2))
                state = self.service.get_state()['data']['readiness']
                self.assertFalse(state['ready'])
                self.assertEqual(state['errors'][0]['code'], 'WINDOW_UNAVAILABLE')
            finally:
                release.set()
                self.wait()

    def test_unconfigured_readiness_only_requires_setup_but_caches_devices(self):
        self.service._cfg.update(active_preset_id=None, configured=False, vault='', mic='', window='',
                                 transcription_provider='local')
        state = self.readiness()
        self.assertEqual([item['code'] for item in state['errors']], ['SETUP_REQUIRED'])
        self.assertEqual(self.service.get_state()['data']['devices'], self.devices)

    def choose_dictionaries(self, *files):
        with patch.object(self.service, '_dialog', return_value=tuple(str(file) for file in files)) as dialog:
            result = self.service.choose_hotword_files()
        dialog.assert_called_once_with('file', allow_multiple=True,
                                       file_types=('Hotword dictionaries (*.txt;*.scel)',))
        return result

    def test_dictionary_multiselect_returns_only_name_content_and_stable_id(self):
        first, second = self.root / '术语.txt', self.root / 'Other.txt'
        first.write_text('角色名\n共享词\n角色名', encoding='utf-8')
        second.write_text('共享词\nOther term', encoding='utf-8')
        result = self.choose_dictionaries(first, second)
        self.assertTrue(result['ok'], result)
        self.assertEqual(len(result['data']['files']), 2)
        self.assertEqual(result['data']['files'][0]['words'], ['角色名', '共享词'])
        self.assertEqual(result['data']['files'][0]['name'], '术语.txt')
        for item in result['data']['files']:
            self.assertEqual(set(item), {'id', 'name', 'words'})
            self.assertRegex(item['id'], r'^[a-f0-9]{64}$')
        self.assertNotIn(str(self.root), json.dumps(result, ensure_ascii=False))
        self.assertEqual(self.service._cfg['hotword_files'], [])
        self.assertFalse((self.root / 'config.json').exists())

    def test_dictionary_cancel_and_partial_parse_failure_are_atomic(self):
        self.assertEqual(self.choose_dictionaries(), {'ok': True, 'data': {'files': []}})
        valid = self.root / 'good.txt'
        valid.write_text('valid term', encoding='utf-8')
        invalid = self.root / 'bad.scel'
        invalid.write_bytes(b'not a SCEL dictionary')
        before = deepcopy(self.service._cfg)
        result = self.choose_dictionaries(valid, invalid)
        self.assertFalse(result['ok'])
        self.assertNotIn('data', result)
        self.assertIn('bad.scel', result['error'])
        self.assertNotIn(str(self.root), result['error'])
        self.assertEqual(self.service._cfg, before)
        self.assertFalse((self.root / 'config.json').exists())

    def test_identical_dictionaries_deduplicate_across_filename_order_and_unicode(self):
        first, duplicate = self.root / 'first.txt', self.root / 'renamed.txt'
        first.write_text('Alpha\nCafe\u0301\nBeta', encoding='utf-8')
        duplicate.write_text(' Beta \nCaf\u00e9\nAlpha\nBeta', encoding='utf-8')
        one = self.choose_dictionaries(first)['data']['files'][0]
        two = self.choose_dictionaries(duplicate)['data']['files'][0]
        self.assertEqual(one['id'], two['id'])
        result = self.choose_dictionaries(first, duplicate)
        self.assertEqual(len(result['data']['files']), 1)
        result = self.service.save_settings({'hotword_files': [one, two], 'hotword_manual': 'Alpha\nManual'})
        self.assertTrue(result['ok'], result)
        self.wait()
        self.assertEqual(len(self.service._cfg['hotword_files']), 1)
        self.assertEqual(self.service._cfg['hotwords'], 'Alpha\nCafé\nBeta\nManual')

    def test_removing_dictionary_recomputes_words_and_ignores_flattened_payload(self):
        first, second = self.root / 'one.txt', self.root / 'two.txt'
        first.write_text('Alpha\nShared', encoding='utf-8')
        second.write_text('Beta\nShared', encoding='utf-8')
        files = self.choose_dictionaries(first, second)['data']['files']
        saved = self.service.save_settings({'hotword_files': files, 'hotword_manual': 'Manual',
                                            'hotwords': 'Untrusted flattened text'})
        self.assertTrue(saved['ok'], saved)
        self.wait()
        self.assertEqual(self.service._cfg['hotwords'], 'Alpha\nShared\nBeta\nManual')
        removed = self.service.save_settings({'hotword_files': [files[1]], 'hotword_manual': 'Manual',
                                              'hotwords': self.service._cfg['hotwords']})
        self.assertTrue(removed['ok'], removed)
        self.wait()
        self.assertEqual(self.service._cfg['hotwords'], 'Beta\nShared\nManual')
        self.assertTrue(self.service.save_settings({'hotword_files': [], 'hotword_manual': ''})['ok'])
        self.wait()
        self.assertEqual(self.service._cfg['hotwords'], '')

    def test_dictionary_snapshots_survive_source_move_and_stay_out_of_session_settings(self):
        file = self.root / 'source.txt'
        file.write_text('Durable term', encoding='utf-8')
        files = self.choose_dictionaries(file)['data']['files']
        file.rename(self.root / 'moved-source.txt')
        saved = self.service.save_settings({'hotword_files': files, 'hotword_manual': 'Manual term'})
        self.assertTrue(saved['ok'], saved)
        self.wait()
        # Exercise the engine's actual allowlist used for session.json, without
        # creating any recording. Files/manual metadata must never be copied.
        settings = bridge.recorder.session_settings(self.service._cfg)
        self.assertEqual(settings['hotwords'], 'Durable term\nManual term')
        self.assertNotIn('hotword_files', settings)
        self.assertNotIn('hotword_manual', settings)
        self.assertNotIn(str(self.root), json.dumps(settings, ensure_ascii=False))
        self.assertNotIn('source.txt', json.dumps(settings))

    def test_legacy_hotwords_migrate_to_manual_and_text_api_remains_compatible(self):
        legacy = self.service._cfg['presets']['legacy']
        legacy.pop('hotword_files')
        legacy.pop('hotword_manual')
        legacy['hotwords'] = '旧词条,Another term'
        self.service._initialize_presets()
        config = self.service.get_state()['data']['config']
        self.assertEqual(config['hotword_files'], [])
        self.assertEqual(config['hotword_manual'], '旧词条,Another term')
        self.assertEqual(config['hotwords'], '旧词条\nAnother term')
        self.assertTrue(self.service.save_settings({'hotwords': 'Text editor replacement'})['ok'])
        self.wait()
        self.assertEqual(self.service._cfg['hotword_manual'], 'Text editor replacement')
        self.assertEqual(self.service._cfg['hotwords'], 'Text editor replacement')

    def test_dictionary_snapshots_are_deeply_isolated_between_presets_and_callers(self):
        file = self.root / 'shared.txt'
        file.write_text('Shared source', encoding='utf-8')
        selected = self.choose_dictionaries(file)['data']['files']
        first = self.service.save_preset({'name': 'Preset A', 'hotword_files': selected,
                                           'hotword_manual': 'Only A'})['data']['id']
        self.wait()
        second_result = self.service.save_preset({'name': 'Preset B', 'hotword_files': selected,
                                                  'hotword_manual': 'Only B'})
        second = second_result['data']['id']
        self.wait()
        selected[0]['words'].append('Caller mutation')
        second_result['data']['config']['hotword_files'][0]['words'].append('Response mutation')
        self.assertTrue(self.service.save_settings({'hotword_files': [], 'hotword_manual': 'Only B'})['ok'])
        self.wait()
        self.assertEqual(self.service._cfg['presets'][second]['hotword_files'], [])
        self.assertTrue(self.service.select_preset(first)['ok'])
        self.wait()
        config = self.service.get_state()['data']['config']
        self.assertEqual(config['hotword_files'][0]['words'], ['Shared source'])
        self.assertEqual(config['hotwords'], 'Shared source\nOnly A')

    def test_dictionary_selection_defers_qwen_limits_until_preset_save(self):
        self.service._cfg['transcription_provider'] = 'qwen'
        file = self.root / 'long-term.txt'
        word = '甲' * 16
        file.write_text(word, encoding='utf-8')
        result = self.choose_dictionaries(file)
        self.assertTrue(result['ok'], result)
        before = deepcopy(self.service._cfg)
        saved = self.service.save_settings({'hotword_files': result['data']['files'], 'hotword_manual': ''})
        self.assertFalse(saved['ok'])
        self.assertIn('过长', saved['error'])
        self.assertEqual(self.service._cfg, before)

    def test_dictionary_structure_hash_paths_and_word_limits_are_validated_before_save(self):
        file = self.root / 'valid.txt'
        file.write_text('Alpha', encoding='utf-8')
        valid = self.choose_dictionaries(file)['data']['files'][0]
        too_many = [f'word-{index}' for index in range(2000)]
        limit_file = dict(name='limit.txt', words=too_many, id=hotword_files.dictionary_id(too_many))
        malformed = [
            {'hotword_files': 'not an array', 'hotword_manual': ''},
            {'hotword_files': [{**valid, 'path': str(file)}], 'hotword_manual': ''},
            {'hotword_files': [{**valid, 'name': str(file)}], 'hotword_manual': ''},
            {'hotword_files': [{**valid, 'id': 'forged'}], 'hotword_manual': ''},
            {'hotword_files': [{**valid, 'words': [42]}], 'hotword_manual': ''},
            {'hotword_files': [limit_file], 'hotword_manual': 'one more unique word'},
            {'hotword_files': [], 'hotword_manual': 'x' * 128001},
        ]
        before = deepcopy(self.service._cfg)
        for payload in malformed:
            with self.subTest(payload_kind=next(iter(payload))):
                self.assertFalse(self.service.save_settings(payload)['ok'])
                self.assertEqual(self.service._cfg, before)
        self.assertFalse((self.root / 'config.json').exists())

    def test_dictionary_file_size_and_combined_words_are_bounded(self):
        oversized = self.root / 'oversized.txt'
        with oversized.open('wb') as file:
            file.truncate(hotword_files.MAX_FILE_BYTES + 1)
        self.assertIn('8 MB', self.choose_dictionaries(oversized)['error'])
        first, second = self.root / 'first.txt', self.root / 'second.txt'
        first.write_text('\n'.join(f'word-{index}' for index in range(1500)), encoding='utf-8')
        second.write_text('\n'.join(f'word-{index}' for index in range(1500, 2100)), encoding='utf-8')
        result = self.choose_dictionaries(first, second)
        self.assertFalse(result['ok'])
        self.assertIn('2000', result['error'])
        self.assertEqual(self.service._cfg['hotword_files'], [])

    def test_dictionary_site_opens_fixed_url_without_preset_name_or_upload(self):
        self.service._cfg['game'] = 'Private project name'
        with patch.object(bridge.webbrowser, 'open', return_value=True) as browser:
            self.assertEqual(self.service.open_dictionary_site(), {'ok': True, 'data': {'requested': True}})
        browser.assert_called_once_with('https://pinyin.sogou.com/dict/')
        with patch.object(bridge.webbrowser, 'open', return_value=False):
            self.assertFalse(self.service.open_dictionary_site()['ok'])


if __name__ == '__main__':
    unittest.main()
