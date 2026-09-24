"""Synthetic bridge tests: never capture media, query a real OBS, or upload audio."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import json
import hashlib
import os
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import desktop_service as bridge
import hotword_files
from updater import UpdateManager as RealUpdateManager


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
        self.updates = MagicMock()
        self.updates.snapshot.return_value = dict(current_version='0.6.0',state='idle',latest_version=None,
            release_url=None,notes='',downloaded_bytes=0,total_bytes=0,error=None,include_prerelease=False)
        self.updates.launch_install.return_value={'ready':True}
        self.updates.cancel_install.return_value={'cancelled':True}
        self.patches = [
            patch.dict('sys.modules',{'updater':SimpleNamespace(UpdateManager=MagicMock(return_value=self.updates))}),
            patch.object(bridge, 'load_settings', return_value=deepcopy(self.config)),
            patch.object(bridge, 'ModelManager', return_value=self.model),
            patch.object(bridge.recorder, 'client', side_effect=ConnectionRefusedError('offline')),
            patch.object(bridge.secret_store, 'has_key', return_value=False),
            patch.object(bridge.DesktopService, '_monitor_loop', return_value=None),
            patch.object(bridge.DesktopService, '_main_is_foreground', return_value=True),
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

    def wait(self, background=True):
        if self.service._update_thread:
            self.service._update_thread.join(5)
            self.assertFalse(self.service._update_thread.is_alive(),'synthetic update did not finish')
        if self.service._job:
            self.service._job.join(5)
            self.assertFalse(self.service._job.is_alive(), 'synthetic job did not finish')
        while (readiness := self.service._readiness_thread) is not None:
            readiness.join(5)
            self.assertFalse(readiness.is_alive(), 'synthetic readiness did not finish')
            if readiness is self.service._readiness_thread:
                break
        worker = self.service._background_thread
        if background and worker:
            worker.join(5)
            self.assertFalse(worker.is_alive(), 'synthetic background worker did not finish')

    def session(self, ident='synthetic-1', **extra):
        path = self.vault / '场次' / (ident + ' fixture')
        path.mkdir(parents=True, exist_ok=True)
        data = dict(id=ident, game=self.config['game'], created='2026-09-20T08:00:00+08:00',
                    state='待整理', settings={k: v for k, v in self.config.items() if k not in ('password', 'port', 'vault')},
                    test=True, media={'duration': 12.5}, started=1)
        data.update(extra)
        bridge.recorder.write(path / 'session.json', data)
        return bridge.recorder.Session(path)

    def fresh_shared_vault(self):
        self.service.root = self.root / 'recorder-version'
        self.service.root.mkdir()
        self.vault = self.root / 'think-aloud-database'
        self.service._cfg.update(vault=str(self.vault), configured=False, presets={}, active_preset_id=None)
        return self.vault

    def test_unconfirmed_default_is_not_scanned_recovered_or_probed(self):
        candidate = self.fresh_shared_vault()
        session = self.session(state='转写中')
        before = (session.path / 'session.json').read_bytes()
        real_read = bridge.recorder.read

        def guarded_read(path):
            if Path(path).resolve().is_relative_to(candidate):
                raise AssertionError('unconfirmed shared database was read')
            return real_read(path)

        with patch.object(bridge.recorder, 'read', side_effect=guarded_read), \
             patch.object(self.service, '_probe_location') as probe, \
             patch.object(self.service, '_install_vault') as install:
            self.service._startup()
            self.service._update_readiness()
            state = self.service.get_state()['data']
        probe.assert_not_called()
        install.assert_not_called()
        self.assertEqual(state['sessions'], [])
        self.assertEqual(state['default_vault'], dict(path=str(candidate), exists=True,
                         is_directory=True, requires_confirmation=True))
        self.assertEqual((session.path / 'session.json').read_bytes(), before)

    def test_default_reuse_requires_matching_confirmation_and_never_persists_it(self):
        candidate = self.fresh_shared_vault()
        candidate.mkdir()
        payload = {'name': 'First project', 'vault': str(candidate)}
        with patch.object(self.service, '_install_vault') as install, \
             patch.object(self.service, '_persist') as persist:
            for confirmation in (None, str(self.root / 'other-directory')):
                draft = dict(payload)
                if confirmation is not None:
                    draft['confirmed_vault'] = confirmation
                result = self.service.save_preset(draft)
                self.assertEqual(result.get('code'), 'VAULT_REUSE_REQUIRED', result)
            install.assert_not_called()
            persist.assert_not_called()
        result = self.service.save_preset({**payload, 'confirmed_vault': str(candidate)})
        self.assertTrue(result['ok'], result)
        self.wait()
        saved = bridge.recorder.read(self.service.root / 'config.json')
        self.assertNotIn('confirmed_vault', json.dumps(saved))
        self.assertNotIn('confirmed_vault', json.dumps(self.service.get_state()))
        self.assertFalse(self.service.get_state()['data']['default_vault']['requires_confirmation'])
        # Later preset creation/editing does not ask for first-run reuse again.
        self.assertTrue(self.service.save_preset({'name': 'Second project'})['ok'])
        self.wait()

    def test_first_run_picker_cancel_or_alternate_does_not_touch_default(self):
        candidate = self.fresh_shared_vault()
        candidate.mkdir()
        with patch.object(self.service, '_dialog', return_value=None):
            self.assertEqual(self.service.choose_directory('vault')['data']['path'], None)
        self.assertEqual(list(candidate.iterdir()), [])
        self.assertFalse((self.service.root / 'config.json').exists())
        alternate = self.root / 'chosen-library'
        result = self.service.save_preset({'name': 'Other location', 'vault': str(alternate),
                                          'confirmed_vault': str(alternate)})
        self.assertTrue(result['ok'], result)
        self.wait()
        self.assertTrue(alternate.is_dir())
        self.assertEqual(list(candidate.iterdir()), [])

    def test_default_directory_appearing_after_snapshot_requires_confirmation(self):
        candidate = self.fresh_shared_vault()
        self.assertFalse(self.service.get_state()['data']['default_vault']['exists'])
        candidate.mkdir()
        result = self.service.save_preset({'name': 'First project'})
        self.assertEqual(result.get('code'), 'VAULT_REUSE_REQUIRED', result)
        self.assertEqual(list(candidate.iterdir()), [])
        self.assertFalse((self.service.root / 'config.json').exists())

    def test_default_atomic_creation_catches_last_moment_race(self):
        candidate = self.fresh_shared_vault()
        real_mkdir = Path.mkdir

        def raced_mkdir(path, *args, **kwargs):
            if path == candidate:
                real_mkdir(path)
            return real_mkdir(path, *args, **kwargs)

        with patch.object(Path, 'mkdir', new=raced_mkdir), \
             patch.object(self.service, '_install_vault') as install:
            result = self.service.save_preset({'name': 'First project'})
        self.assertEqual(result.get('code'), 'VAULT_REUSE_REQUIRED', result)
        install.assert_not_called()
        self.assertFalse((self.service.root / 'config.json').exists())

    def test_new_default_created_only_on_save_and_rejects_file_or_permission_failure(self):
        candidate = self.fresh_shared_vault()
        state = self.service.get_state()['data']['default_vault']
        self.assertEqual(state, dict(path=str(candidate), exists=False, is_directory=False, requires_confirmation=False))
        self.assertFalse(candidate.exists())
        real_mkdir = Path.mkdir

        def denied_mkdir(path, *args, **kwargs):
            if path == candidate:
                raise PermissionError('synthetic parent is read-only')
            return real_mkdir(path, *args, **kwargs)

        with patch.object(Path, 'mkdir', new=denied_mkdir):
            result = self.service.save_preset({'name': 'First project'})
        self.assertFalse(result['ok'])
        self.assertFalse(candidate.exists())
        self.assertFalse((self.service.root / 'config.json').exists())
        candidate.write_text('keep this existing file')
        file_state = self.service.get_state()['data']['default_vault']
        self.assertTrue(file_state['requires_confirmation'])
        self.assertFalse(file_state['is_directory'])
        self.assertFalse(self.service.save_preset({'name': 'First project', 'confirmed_vault': str(candidate)})['ok'])
        self.assertEqual(candidate.read_text(), 'keep this existing file')

    def test_missing_default_is_created_at_successful_first_save(self):
        candidate = self.fresh_shared_vault()
        self.assertFalse(candidate.exists())
        result = self.service.save_preset({'name': 'First project'})
        self.assertTrue(result['ok'], result)
        self.wait()
        self.assertTrue(candidate.is_dir())
        self.assertEqual(self.service._cfg['vault'], str(candidate))

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

    def test_start_reports_real_stages_and_waits_for_input_preparation_result(self):
        prepared, release = threading.Event(), threading.Event()
        session = self.session(test=False, input_state='recording', settings={**self.config, 'record_inputs': True})
        stages = []

        def readiness():
            stages.append(self.service.get_state()['data']['activity']['status'])
            return {'ready': True}

        def start(cfg, *, progress):
            for stage in ('正在启动录像', '正在准备操作记录'):
                progress(stage)
                stages.append(self.service.get_state()['data']['activity']['status'])
            prepared.set()
            release.wait(3)
            return session

        with patch.object(self.service, '_update_readiness', side_effect=readiness), \
             patch.object(bridge.recorder.Session, 'start', side_effect=start):
            try:
                self.assertTrue(self.service.start_recording()['ok'])
                self.assertTrue(prepared.wait(2))
                activity = self.service.get_state()['data']['activity']
                self.assertEqual(stages, ['正在检查录制条件', '正在启动录像', '正在准备操作记录'])
                self.assertEqual(activity['kind'], 'starting')
                self.assertTrue(activity['busy'])
                self.assertIn('录像已开始', activity['detail'])
                self.assertIsNone(self.service._active)
            finally:
                release.set()
                self.wait()
        activity = self.service.get_state()['data']['activity']
        self.assertFalse(activity['busy'])
        self.assertEqual(activity['kind'], 'recording')
        self.assertEqual(activity['status'], '录制中')
        self.assertIs(self.service._active, session)

    def test_input_start_failure_is_visible_while_video_continues_and_survives_health_check(self):
        session = self.session(test=False, input_state='failed', settings={**self.config, 'record_inputs': True},
                               warning='操作采集未能启动，录像仍在继续。')
        with patch.object(bridge.recorder.Session, 'start', return_value=session):
            self.assertTrue(self.service.start_recording()['ok'])
            self.wait()
        activity = self.service.get_state()['data']['activity']
        self.assertIs(self.service._active, session)
        self.assertEqual(activity['kind'], 'recording')
        self.assertEqual(activity['status'], '录制中 · 操作记录未启动')
        self.assertEqual(activity['detail'], session.meta['warning'])
        client = MagicMock()
        client.get_record_status.return_value = SimpleNamespace(output_active=True, output_timecode='00:00:05.000')
        client.send.return_value = SimpleNamespace(record_directory=str(session.path))
        with patch.object(bridge.recorder, 'client', return_value=client), \
             patch.object(bridge.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)):
            self.service._inspect_recording()
        after = self.service.get_state()['data']['activity']
        self.assertEqual(after['status'], activity['status'])
        self.assertEqual(after['detail'], activity['detail'])
        client.stop_record.assert_not_called()

    def test_input_interruption_does_not_revert_to_all_clear_on_health_check(self):
        session = self.session(test=False, input_state='interrupted',
            settings={**self.config, 'record_inputs': True}, input_clock={'initial_seconds': .3},
            input_error='操作采集已停止，录像仍在继续。')
        self.service._active = session
        client = MagicMock()
        client.get_record_status.return_value = SimpleNamespace(output_active=True, output_timecode='00:00:05.000')
        client.send.return_value = SimpleNamespace(record_directory=str(session.path))
        with patch.object(bridge.recorder, 'client', return_value=client), \
             patch.object(bridge.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)):
            self.service._inspect_recording()
        activity = self.service.get_state()['data']['activity']
        self.assertEqual(activity['status'], '录制中 · 操作记录已中断')
        self.assertEqual(activity['detail'], session.meta['input_error'])
        client.stop_record.assert_not_called()

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
        def failed_start(cfg, *, progress=None):
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
            result = self.service.process_session(session.meta['id'])
            self.wait()
            process.assert_not_called()
            self.assertIn('仅录制', result['error'])
            self.service._cfg['transcription_provider'] = 'local'
            self.model.resolve_model.return_value = self.root / 'model'
            result = self.service.process_session(session.meta['id'])
            self.wait()
        self.assertEqual(process.call_count, 1)
        self.assertEqual(process.call_args.kwargs['transcription_settings']['transcription_provider'], 'local')

    def test_uncertain_cloud_submission_blocks_changed_settings(self):
        session = self.session()
        bridge.recorder.write(session.path / '转写原始/old/云端任务.json', {'state': 'SUBMITTING'})
        self.service._cfg['transcription_provider'] = 'local'
        self.model.resolve_model.return_value = self.root / 'model'
        with patch.object(bridge, 'process_isolated') as process:
            result = self.service.process_session(session.meta['id'])
            self.wait()
        process.assert_not_called()
        self.assertIn('结果不明', result['error'])

    def test_blocked_processing_allows_next_capture_and_serial_stop_queue(self):
        self.service._cfg['transcription_provider'] = 'local'
        self.model.resolve_model.return_value = self.root / 'model'
        a, b = self.session('capture-a'), self.session('capture-b')
        for session in (a, b):
            session.meta['settings']['transcription_provider'] = 'local'
            session.update(settings=session.meta['settings'])
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        calls, callbacks = [], []

        def process(session, progress, transcription_settings):
            calls.append(session.meta['id'])
            callbacks.append(progress)
            session.update(state='转写中')
            if session.meta['id'] == 'capture-a':
                entered.set()
                self.assertTrue(release.wait(5))
            session.update(state='可回看', segments=3)

        with patch.object(bridge, 'process_isolated', side_effect=process), \
             patch.object(a, 'stop'), patch.object(b, 'stop'), \
             patch.object(bridge.recorder.Session, 'start', return_value=b):
            try:
                self.service._active = a
                self.assertTrue(self.service.stop_recording()['ok'])
                self.wait(background=False)
                self.assertTrue(entered.wait(2))
                self.assertFalse(self.service.get_state()['data']['activity']['busy'])
                self.assertTrue(self.service.get_state()['data']['readiness']['ready'])
                self.assertTrue(self.service.start_recording({})['ok'])
                self.wait(background=False)
                self.assertIs(self.service._active, b)
                foreground = self.service.get_state()['data']['activity']
                callbacks[0]('A uploading synthetic audio')
                after_progress = self.service.get_state()['data']['activity']
                self.assertEqual({k: v for k, v in after_progress.items() if k != 'elapsed_seconds'},
                                 {k: v for k, v in foreground.items() if k != 'elapsed_seconds'})
                self.assertTrue(self.service.stop_recording()['ok'])
                self.wait(background=False)
                state = self.service.get_state()['data']
                self.assertFalse(state['activity']['busy'])
                self.assertTrue(state['readiness']['ready'])
                self.assertIsNone(self.service._active)
                self.assertEqual([j['state'] for j in state['background_jobs']], ['running', 'queued'])
                self.assertEqual(calls, ['capture-a'])
                with patch.object(bridge.recorder, 'open_review') as review:
                    result = self.service.open_review('capture-a')
                    self.assertFalse(result['ok'])
                    review.assert_not_called()
                    self.assertIn('场次文件不存在', result['error'])
                self.assertEqual(bridge.recorder.read(b.path / 'session.json')['state'], '待整理')
                self.assertFalse(self.service.close_allowed())
                self.service._recover()
                self.assertEqual(bridge.recorder.read(a.path / 'session.json')['state'], '转写中')
                self.assertEqual(bridge.recorder.read(b.path / 'session.json')['state'], '待整理')
            finally:
                release.set()
                self.wait()
        self.assertEqual(calls, ['capture-a', 'capture-b'])
        state = self.service.get_state()['data']
        self.assertEqual(state['background_jobs'], [])
        self.assertTrue(all(s['background_result']['state'] == 'completed' for s in state['sessions']))

    def test_queue_preserves_settings_and_outcomes_across_preset_vault_switch(self):
        self.service._cfg['transcription_provider'] = 'local'
        self.model.resolve_model.return_value = self.root / 'model'
        a, b = self.session('old-a'), self.session('old-b')
        a.meta['settings'].update(language='zh', hotwords='Alpha')
        a.update(settings=a.meta['settings'])
        b.meta['settings'].update(language='ja', hotwords='Beta')
        b.update(settings=b.meta['settings'])
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        captured = []

        def process(session, progress, transcription_settings):
            captured.append((session.path, deepcopy(transcription_settings)))
            if session.meta['id'] == 'old-a':
                entered.set()
                self.assertTrue(release.wait(5))
                raise RuntimeError('synthetic A failure')
            session.update(state='可回看')

        with patch.object(bridge, 'process_isolated', side_effect=process):
            try:
                self.assertTrue(self.service.process_session('old-a')['ok'])
                self.assertTrue(entered.wait(2))
                self.assertTrue(self.service.process_session('old-b')['ok'])
                self.assertFalse(self.service.process_session('old-a')['ok'])
                self.assertFalse(self.service.process_session('old-b')['ok'])
                # A full saved preset switches both engine and vault while B waits.
                changed = self.service.save_preset({'name': 'Other game',
                    'vault': str(self.root / 'other-vault'), 'transcription_provider': 'later',
                    'language': 'en', 'hotword_manual': 'Other terms'})
                self.assertTrue(changed['ok'], changed)
                self.wait(background=False)
                self.assertEqual({s['id'] for s in self.service.get_state()['data']['sessions']}, {'old-a', 'old-b'})
                self.assertTrue(all(not s['in_current_vault'] for s in self.service.get_state()['data']['sessions']))
            finally:
                release.set()
                self.wait()
        self.assertEqual([p for p, _ in captured], [a.path, b.path])
        self.assertEqual([(c['language'], c['hotwords'], c['transcription_provider']) for _, c in captured],
                         [('zh', 'Alpha', 'local'), ('ja', 'Beta', 'local')])
        rows = {s['id']: s for s in self.service.get_state()['data']['sessions']}
        self.assertEqual(rows['old-a']['background_result']['state'], 'failed')
        self.assertIn('synthetic A failure', rows['old-a']['error'])
        self.assertEqual(rows['old-b']['background_result']['state'], 'completed')
        self.assertEqual(self.service._session('old-a').path, a.path)

    def test_background_failure_does_not_overwrite_new_recording_activity(self):
        self.service._cfg['transcription_provider'] = 'local'
        self.model.resolve_model.return_value = self.root / 'model'
        a, b = self.session('failure-a'), self.session('recording-b')
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def process(session, progress, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            raise RuntimeError('synthetic transcription failed')

        with patch.object(bridge, 'process_isolated', side_effect=process), \
             patch.object(bridge.recorder.Session, 'start', return_value=b):
            try:
                self.assertTrue(self.service.process_session(a.meta['id'])['ok'])
                self.assertTrue(entered.wait(2))
                self.assertTrue(self.service.start_recording({})['ok'])
                self.wait(background=False)
                before = self.service.get_state()['data']['activity']
            finally:
                release.set()
                self.wait()
        self.assertIs(self.service._active, b)
        after = self.service.get_state()['data']['activity']
        self.assertEqual({k: v for k, v in after.items() if k != 'elapsed_seconds'},
                         {k: v for k, v in before.items() if k != 'elapsed_seconds'})
        self.assertEqual(bridge.recorder.read(a.path / 'session.json')['state'], '失败')

    def test_restart_leaves_persisted_queue_pending_without_auto_upload(self):
        session = self.session(background_processing={'id': 'prior-job', 'state': 'queued',
            'settings': {'transcription_provider': 'qwen'}})
        with patch.object(bridge, 'process_isolated') as process:
            self.service._recover()
        process.assert_not_called()
        restored = bridge.recorder.read(session.path / 'session.json')
        self.assertEqual(restored['state'], '待整理')
        self.assertIsNone(restored['background_processing'])
        self.assertIn('不会自动上传', restored['warning'])

    def test_stop_keeps_recording_owned_until_all_native_cleanup_returns(self):
        session = self.session(state='录制中')
        self.service._active = session
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def finishing_stop():
            entered.set()
            self.assertTrue(release.wait(5))

        with patch.object(session, 'stop', side_effect=finishing_stop):
            try:
                self.assertTrue(self.service.stop_recording()['ok'])
                self.assertTrue(entered.wait(2))
                self.assertIs(self.service._active, session)
                self.assertFalse(self.service.start_recording({})['ok'])
                self.assertTrue(self.service.get_state()['data']['activity']['busy'])
                self.assertEqual(self.service.get_state()['data']['background_jobs'], [])
            finally:
                release.set()
                self.wait()
        self.assertIsNone(self.service._active)

    def test_duplicate_cloud_recovery_does_not_restore_or_queue_twice(self):
        session = self.session(transcription_cache='转写原始/original')
        session.meta['settings']['transcription_provider'] = 'qwen'
        session.update(settings=session.meta['settings'])
        cloud = session.path / '转写原始/original/云端任务.json'
        bridge.recorder.write(cloud, {'state': 'SUBMITTING', 'fingerprint': 'same'})
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def process(owned, progress, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            owned.update(state='可回看')

        from qwen_transcription import restore_task
        with patch.object(bridge.secret_store, 'has_key', return_value=True), \
             patch.object(bridge, 'process_isolated', side_effect=process) as process_mock, \
             patch('qwen_transcription.restore_task', wraps=restore_task) as restore:
            try:
                self.assertTrue(self.service.recover_cloud_task(session.meta['id'], 'task-one')['ok'])
                self.assertTrue(entered.wait(2))
                self.assertFalse(self.service.recover_cloud_task(session.meta['id'], 'task-two')['ok'])
                self.assertEqual(restore.call_count, 1)
                self.assertEqual(bridge.recorder.read(cloud)['task_id'], 'task-one')
            finally:
                release.set()
                self.wait()
        self.assertEqual(process_mock.call_count, 1)

    def test_progress_presentation_failure_cannot_abort_processing_or_release_queue(self):
        self.service._cfg['transcription_provider'] = 'local'
        self.model.resolve_model.return_value = self.root / 'model'
        session = self.session()
        safe_text = self.service._safe_text

        def fail_presentation(text):
            if text == 'unrenderable-progress':
                raise RuntimeError('synthetic presentation failure')
            return safe_text(text)

        def process(owned, progress, **kwargs):
            progress('unrenderable-progress')
            owned.update(state='可回看', segments=4)

        with patch.object(self.service, '_safe_text', side_effect=fail_presentation), \
             patch.object(bridge, 'process_isolated', side_effect=process):
            self.assertTrue(self.service.process_session(session.meta['id'])['ok'])
            self.wait()
        row = self.service.get_state()['data']['sessions'][0]
        self.assertEqual(row['segments'], 4)
        self.assertEqual(row['background_result']['state'], 'completed')

    def test_external_worker_lock_rejects_queue_without_mutating_session(self):
        import msvcrt
        self.service._cfg['transcription_provider'] = 'local'
        self.model.resolve_model.return_value = self.root / 'model'
        session = self.session(state='转写中', background_processing={'id': 'external', 'state': 'running'})
        original = deepcopy(session.meta)
        with (session.path / '.processing.lock').open('a+b') as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                self.assertFalse(self.service.process_session(session.meta['id'])['ok'])
                self.service._recover()
                self.assertEqual(bridge.recorder.read(session.path / 'session.json'), original)
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        self.assertEqual(self.service.get_state()['data']['background_jobs'], [])

    def test_recovery_rereads_completed_metadata_after_acquiring_lock(self):
        session = self.session(state='转写中')
        actual_lock = bridge.recorder.session_lock

        def completing_lock(fn):
            def complete_first(owned, *args, **kwargs):
                bridge.recorder.Session(owned.path).update(state='可回看', completed=123, segments=7)
                return fn(owned, *args, **kwargs)
            return actual_lock(complete_first)

        with patch.object(bridge.recorder, 'session_lock', side_effect=completing_lock):
            self.service._recover()
        meta = bridge.recorder.read(session.path / 'session.json')
        self.assertEqual((meta['state'], meta['completed'], meta['segments']), ('可回看', 123, 7))

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
        self.assertEqual(process.call_args.kwargs['transcription_settings']['transcription_provider'], 'qwen')
        restored = bridge.recorder.read(job)
        self.assertEqual(restored['task_id'], 'existing-task-id')
        self.assertEqual(restored['fingerprint'], 'unchanged')

    def test_cloud_recovery_rejects_outside_cache_and_task_replacement(self):
        session = self.session(transcription_cache='../outside')
        session.meta['settings']['transcription_provider'] = 'qwen'
        session.update(settings=session.meta['settings'])
        with patch.object(bridge.secret_store, 'has_key', return_value=True), \
             patch.object(bridge, 'process_isolated') as process:
            result = self.service.recover_cloud_task(session.meta['id'], 'new-task')
            self.wait()
            process.assert_not_called()
            self.assertIn('路径无效', result['error'])
            session.update(transcription_cache='转写原始/original')
            job = session.path / '转写原始/original/云端任务.json'
            bridge.recorder.write(job, {'state': 'PENDING', 'task_id': 'old-task'})
            self.service.recover_cloud_task(session.meta['id'], 'new-task')
            self.wait()
            process.assert_not_called()
            self.assertEqual(bridge.recorder.read(job)['task_id'], 'old-task')

    def test_review_does_not_replace_recording_activity(self):
        old = self.session(state='可回看')
        (old.path / '录像.mp4').write_bytes(b'synthetic published video placeholder')
        active = self.session('new-recording', state='录制中')
        self.service._active = active
        before = dict(self.service._activity)
        opener = MagicMock(return_value={'ready': True})
        self.service.set_review_opener(opener)
        result = self.service.open_review(old.meta['id'])
        self.assertTrue(result['ok'], result)
        self.assertTrue(result['data']['ready'])
        self.assertEqual(self.service._activity, before)
        self.assertFalse(self.service.open_review(active.meta['id'])['ok'])
        self.service._active = None

    def test_pending_review_and_rename_are_independent_of_background_processing(self):
        session = self.session(state='转写中')
        (session.path / '录像.mp4').write_bytes(b'synthetic published video placeholder')
        self.service._background_jobs['j'] = dict(id='j', session_id=session.meta['id'], game='Synthetic',
            path=session.path.resolve(), state='running', detail='synthetic pending transcription')
        self.addCleanup(self.service._background_jobs.clear)
        self.service.set_review_opener(MagicMock(return_value={'ready': True}))
        self.assertTrue(self.service.open_review(session.meta['id'])['ok'])
        self.assertTrue(self.service.rename_session(session.meta['id'], '自定义场次')['ok'])
        session.update(step='new processing progress')
        state = self.service.get_state()['data']['sessions'][0]
        self.assertTrue(state['can_review'])
        self.assertEqual(state['session_name'], '自定义场次')
        self.assertEqual(self.service._cfg['game'], self.config['game'])

    def test_record_inputs_requires_boolean_and_window_source(self):
        for payload in ({'record_inputs': 'true'}, {'record_inputs': 1},
                        {'record_inputs': True, 'source': '整个显示器'}):
            self.assertFalse(self.service.save_settings(payload)['ok'])
        validated = self.service._validated_settings({'record_inputs': True, 'source': '游戏窗口'})
        self.assertTrue(validated['record_inputs'])

    def test_legacy_preset_never_inherits_another_presets_input_opt_in(self):
        first=self.service._cfg['active_preset_id']
        self.service._cfg['record_inputs']=True
        self.service._cfg['presets'][first]['record_inputs']=True
        old=deepcopy(self.service._cfg['presets'][first])
        old.pop('record_inputs',None)
        old.update(game='Legacy',name='Legacy')
        self.service._cfg['presets']['old']=old
        self.assertTrue(self.service.select_preset('old')['ok'])
        self.wait()
        self.assertIs(self.service._cfg['record_inputs'],False)
        self.assertIs(self.service._cfg['presets']['old']['record_inputs'],False)
        self.assertIs(self.service.get_state()['data']['config']['record_inputs'],False)

    def test_loading_legacy_and_monitor_presets_defaults_input_recording_off(self):
        for source,value in [('游戏窗口',None),('整个显示器',True)]:
            cfg=self.service._cfg
            cfg['record_inputs']=True
            selected=deepcopy(cfg['presets'][cfg['active_preset_id']])
            selected['source']=source
            if value is None:selected.pop('record_inputs',None)
            else:selected['record_inputs']=value
            cfg['presets']['legacy-input']=selected
            cfg['active_preset_id']='legacy-input'
            self.service._initialize_presets()
            self.assertIs(cfg['record_inputs'],False)
            self.assertIs(cfg['presets']['legacy-input']['record_inputs'],False)

    def test_new_preset_without_input_field_does_not_inherit_current_opt_in(self):
        self.service._cfg['record_inputs']=True
        result=self.service.save_preset({'name':'New without opt-in','game':'New without opt-in'})
        self.assertTrue(result['ok'],result)
        self.wait()
        self.assertIs(self.service._cfg['record_inputs'],False)

    def test_idle_readiness_never_prevents_exit(self):
        self.service._readiness.update(checking=True)
        self.service._readiness_thread = MagicMock()
        self.service._readiness_thread.is_alive.return_value = True
        self.assertTrue(self.service.close_allowed())
        self.assertTrue(self.service._closed.is_set())
        self.service._readiness_thread = None

    def test_closing_a_slow_idle_probe_is_nonblocking(self):
        entered, release = threading.Event(), threading.Event()
        def probe():
            entered.set()
            release.wait(3)
            return deepcopy(self.devices), None
        with patch.object(self.service, '_probe_obs_devices', side_effect=probe):
            try:
                self.service._request_readiness(invalidate=True)
                self.assertTrue(entered.wait(2))
                start = time.monotonic()
                self.assertTrue(self.service.close_allowed())
                self.assertLess(time.monotonic()-start, .2)
                self.assertFalse(self.service._request_readiness())
            finally:
                release.set()
                self.wait()

    def test_engine_shutdown_requires_accepted_close_and_is_idempotent(self):
        with patch.object(bridge.recorder, 'shutdown_owned_obs', return_value={'status': 'closed'}) as shutdown:
            self.assertEqual(self.service.shutdown(), {'status': 'close_not_accepted'})
            shutdown.assert_not_called()
            self.service._obs_uncertain = True
            self.assertFalse(self.service.close_allowed())
            self.assertEqual(self.service.shutdown(), {'status': 'close_not_accepted'})
            shutdown.assert_not_called()
            self.service._obs_uncertain = False
            self.assertTrue(self.service.close_allowed())
            self.assertEqual(self.service.shutdown(), {'status': 'closed'})
            self.assertEqual(self.service.shutdown(), {'status': 'closed'})
            shutdown.assert_called_once_with(self.root)

    def test_engine_shutdown_waits_until_an_admitted_idle_operation_finishes(self):
        entered, release = threading.Event(), threading.Event()
        def operation():
            with self.service._operation_lock:
                entered.set()
                release.wait(3)
        worker = threading.Thread(target=operation)
        worker.start()
        self.assertTrue(entered.wait(1))
        try:
            with patch.object(bridge.recorder, 'shutdown_owned_obs', return_value={'status': 'closed'}) as shutdown:
                self.assertTrue(self.service.close_allowed())
                cleanup = threading.Thread(target=self.service.shutdown)
                cleanup.start()
                self.assertTrue(cleanup.is_alive())
                shutdown.assert_not_called()
                release.set()
                worker.join(1)
                cleanup.join(1)
                self.assertFalse(cleanup.is_alive())
                shutdown.assert_called_once_with(self.root)
        finally:
            release.set()
            worker.join(1)

    def test_background_work_close_confirmation_waits_before_any_obs_shutdown(self):
        from window_manager import WindowManager
        class Event:
            def __iadd__(self, handler):
                self.handler = handler
                return self
        window = MagicMock()
        window.events.closing = Event()
        window.events.closed = Event()
        manager = WindowManager(self.service, MagicMock())
        manager.bind_main(window)
        window.create_confirmation_dialog.return_value = True
        window.destroy.side_effect = lambda: window.events.closed.handler()
        cleaned = threading.Event()
        def shutdown(root):
            self.assertTrue(self.service._closed.is_set())
            self.assertEqual(self.service._background_jobs, {})
            cleaned.set()
            return {'status': 'closed'}
        with patch.object(bridge.recorder, 'shutdown_owned_obs', side_effect=shutdown) as stop_obs:
            self.service._background_jobs['synthetic-processing'] = {'state': 'running'}
            try:
                self.assertFalse(manager.close_main())
                deadline = time.monotonic() + 2
                while not self.service._exit_pending and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(self.service._exit_pending)
                self.assertFalse(self.service._closed.is_set())
                stop_obs.assert_not_called()
                window.destroy.assert_not_called()
                window.create_confirmation_dialog.assert_called_once_with('关闭记录器',
                    '还有场次正在整理或排队，完成后可以安全关闭。'
                    '\n\n结束当前录制，并等待保存和整理完成后关闭此窗口？已打开的回看窗口会继续保留。')
                with self.service._lock:
                    self.service._background_jobs.clear()
                self.assertTrue(cleaned.wait(2))
                manager._shutdown_thread.join(1)
                stop_obs.assert_called_once_with(self.root)
                window.destroy.assert_called_once()
            finally:
                self.service._background_jobs.clear()

    def test_background_work_close_cancel_keeps_window_and_obs(self):
        from window_manager import WindowManager
        window = MagicMock()
        manager = WindowManager(self.service, MagicMock())
        manager.main = window
        confirmed = threading.Event()
        def cancel(*args):
            confirmed.set()
            return False
        window.create_confirmation_dialog.side_effect = cancel
        with patch.object(bridge.recorder, 'shutdown_owned_obs') as stop_obs:
            self.service._background_jobs['synthetic-processing'] = {'state': 'running'}
            try:
                self.assertFalse(manager.close_main())
                self.assertTrue(confirmed.wait(1))
                self.assertFalse(self.service._closed.is_set())
                self.assertFalse(self.service._exit_pending)
                self.assertIn('synthetic-processing', self.service._background_jobs)
                window.destroy.assert_not_called()
                stop_obs.assert_not_called()
                self.assertIsNone(manager._shutdown_thread)
            finally:
                self.service._background_jobs.clear()

    def test_close_waits_for_queued_work_and_refuses_new_jobs(self):
        self.service._background_jobs['synthetic'] = {'state': 'running'}
        done = threading.Event()
        thread = threading.Thread(target=lambda: (self.service.finish_for_close(), done.set()))
        try:
            thread.start()
            deadline = time.monotonic()+2
            while not self.service._exit_pending and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertTrue(self.service._exit_pending)
            self.assertFalse(self.service.start_recording({})['ok'])
            self.assertFalse(done.is_set())
            with self.service._lock:
                self.service._background_jobs.clear()
            self.assertTrue(done.wait(2))
            self.assertTrue(self.service._closed.is_set())
        finally:
            self.service._background_jobs.clear()
            thread.join(3)

    def test_safe_close_stops_recording_once_and_waits_for_file_save(self):
        session = self.session(state='录制中')
        self.service._active = session
        entered, release, done = threading.Event(), threading.Event(), threading.Event()
        errors = []

        def finish():
            try:
                self.service.finish_for_close()
                done.set()
            except Exception as error:
                errors.append(error)

        thread = threading.Thread(target=finish)
        with patch.object(session, 'stop', side_effect=lambda: (entered.set(), release.wait(3))) as stop:
            try:
                thread.start()
                self.assertTrue(entered.wait(2))
                self.assertFalse(done.is_set())
                self.assertFalse(self.service._closed.is_set())
                self.assertFalse(self.service.start_recording({})['ok'])
                release.set()
                self.assertTrue(done.wait(2), errors)
                stop.assert_called_once()
                self.assertIsNone(self.service._active)
                self.assertEqual(bridge.recorder.Session(session.path).meta['state'], '待整理')
                self.assertTrue(self.service._closed.is_set())
            finally:
                release.set()
                thread.join(3)

    def test_failed_stop_preserves_recording_and_cancels_pending_close(self):
        session = self.session(state='录制中')
        self.service._active = session
        with patch.object(session, 'stop', side_effect=RuntimeError('synthetic stop failure')) as stop:
            with self.assertRaisesRegex(RuntimeError, '尚未确认保存成功'):
                self.service.finish_for_close()
            stop.assert_called_once()
        self.assertIs(self.service._active, session)
        self.assertFalse(self.service._closed.is_set())
        self.assertFalse(self.service._exit_pending)


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
        client.disconnect.assert_called_once()
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

    def test_idle_readiness_requires_main_foreground_and_resumes_on_activation(self):
        with patch.object(self.service, '_main_is_foreground', return_value=False), \
             patch.object(self.service, '_probe_obs_devices') as probe:
            self.assertFalse(self.service._request_readiness())
            self.service.main_activation_changed()
            probe.assert_not_called()
            self.assertFalse(self.service.get_state()['data']['readiness']['ready'])
        with patch.object(self.service, '_probe_obs_devices', return_value=(deepcopy(self.devices), None)) as probe:
            self.service.main_activation_changed()
            self.wait()
            probe.assert_called_once()
            self.assertTrue(self.service.get_state()['data']['readiness']['ready'])

    def test_startup_defers_obs_launch_until_main_activation(self):
        self.service._startup_launch_attempted = False
        with patch.object(self.service, '_main_is_foreground', return_value=False), \
             patch.object(self.service, '_recover'), patch.object(bridge.recorder, 'client') as client:
            self.service._startup()
            client.assert_not_called()
        self.assertFalse(self.service._startup_launch_attempted)
        with patch.object(bridge.recorder, 'client') as client:
            self.service.main_activation_changed()
            self.wait()
            client.assert_called_once_with(launch=True, progress=self.service._progress,
                                           continue_if=self.service._automatic_probe_allowed)

    def test_queued_automatic_probe_is_cancelled_when_main_loses_foreground(self):
        foreground = {'active': True}
        with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
             patch.object(self.service, '_probe_obs_devices') as probe:
            with self.service._operation_lock:
                self.assertTrue(self.service._request_readiness())
                foreground['active'] = False
            self.wait()
            probe.assert_not_called()

    def test_focus_loss_during_probe_cannot_publish_ready(self):
        entered, release = threading.Event(), threading.Event()
        foreground = {'active': True}
        def probe():
            entered.set()
            release.wait(3)
            return deepcopy(self.devices), None
        with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
             patch.object(self.service, '_probe_obs_devices', side_effect=probe):
            self.assertTrue(self.service._request_readiness())
            self.assertTrue(entered.wait(2))
            foreground['active'] = False
            self.service.main_activation_changed()
            release.set()
            self.wait()
            self.assertFalse(self.service.get_state()['data']['readiness']['ready'])

    def test_automatic_probe_checks_focus_before_connecting(self):
        self.service._automatic_readiness.foreground_only = True
        try:
            with patch.object(self.service, '_main_is_foreground', return_value=False), \
                 patch.object(bridge.recorder, 'client') as client:
                devices, problem = self.actual_probe(self.service)
                self.assertIsNone(devices)
                self.assertEqual(problem[0], 'READINESS_PAUSED')
                client.assert_not_called()
        finally:
            self.service._automatic_readiness.foreground_only = False

    def test_return_to_foreground_queues_fresh_check_behind_inflight_probe(self):
        entered, release, checked_again = threading.Event(), threading.Event(), threading.Event()
        foreground, calls = {'active': True}, []
        def probe():
            calls.append(1)
            if len(calls) == 1:
                entered.set()
                release.wait(3)
            else:
                checked_again.set()
            return deepcopy(self.devices), None
        with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
             patch.object(self.service, '_probe_obs_devices', side_effect=probe):
            self.assertTrue(self.service._request_readiness())
            self.assertTrue(entered.wait(2))
            foreground['active'] = False
            self.service.main_activation_changed()
            foreground['active'] = True
            self.service.main_activation_changed()
            release.set()
            self.assertTrue(checked_again.wait(2))
            self.wait()
            self.assertEqual(len(calls), 2)

    def test_focus_cycle_while_queued_replaces_old_generation_before_running(self):
        foreground = {'active': True}
        with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
             patch.object(self.service, '_run_automatic_readiness', wraps=self.service._run_automatic_readiness) as run, \
             patch.object(self.service, '_probe_obs_devices', return_value=(deepcopy(self.devices), None)) as probe:
            with self.service._operation_lock:
                self.assertTrue(self.service._request_readiness())
                foreground['active'] = False
                self.service.main_activation_changed()
                foreground['active'] = True
                self.service.main_activation_changed()
            self.wait()
            run.assert_called_once_with(invalidate=True, generation=self.service._main_activation_generation)
            probe.assert_called_once()

    def test_focus_cycle_during_launch_file_check_keeps_one_shot_available(self):
        self.service._startup_launch_attempted = False
        foreground = {'active': True}
        is_file = Path.is_file

        def file_check(path):
            result = is_file(path)
            if path.name == 'obs64.exe':
                foreground['active'] = False
                self.service.main_activation_changed()
                foreground['active'] = True
                self.service.main_activation_changed()
            return result

        with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
             patch.object(self.service, '_request_readiness', return_value=False), \
             patch.object(bridge.recorder, 'client') as connect:
            with patch.object(Path, 'is_file', autospec=True, side_effect=file_check):
                state = self.service._run_automatic_readiness()
            self.assertFalse(state['ready'])
            self.assertIsNone(state['checked_at'])
            self.assertFalse(self.service._startup_launch_attempted)
            connect.assert_not_called()
            self.assertTrue(self.service._run_automatic_readiness()['ready'])
            connect.assert_called_once_with(launch=True, progress=self.service._progress,
                                            continue_if=self.service._automatic_probe_allowed)
            self.assertTrue(self.service._startup_launch_attempted)

    def test_automatic_probe_rechecks_focus_after_every_obs_io_and_keeps_cleanup(self):
        boundaries = [('connect', 1), ('get_record_status', 1), ('get_stream_status', 1),
            ('get_profile_list', 1), ('get_scene_collection_list', 1), ('get_input_list', 1),
            ('get_record_status', 2), ('get_stream_status', 2), ('create_input', 1),
            ('get_input_properties_list_property_items', 1), ('get_input_properties_list_property_items', 3)]
        for restore_foreground in (False, True):
            for operation, occurrence in boundaries:
                with self.subTest(operation=operation, occurrence=occurrence, restore=restore_foreground):
                    foreground = {'active': True}
                    client = MagicMock()
                    client.get_record_status.return_value.output_active = False
                    client.get_stream_status.return_value.output_active = False
                    client.get_profile_list.return_value.current_profile_name = 'Experience'
                    client.get_scene_collection_list.return_value.current_scene_collection_name = 'Experience'
                    client.get_input_list.return_value.inputs = []
                    client.get_input_properties_list_property_items.return_value.property_items = []
                    count = 0

                    def change_focus():
                        foreground['active'] = False
                        self.service.main_activation_changed()
                        if restore_foreground:
                            foreground['active'] = True
                            self.service.main_activation_changed()

                    def during_request(*args, **kwargs):
                        nonlocal count
                        count += 1
                        if count == occurrence:
                            change_focus()
                        return client if operation == 'connect' else getattr(client, operation).return_value

                    if operation != 'connect':
                        getattr(client, operation).side_effect = during_request
                    with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
                         patch.object(self.service, '_request_readiness', return_value=False), \
                         patch.object(bridge.recorder, 'client', side_effect=during_request if operation == 'connect' else None,
                                      return_value=client), \
                         patch.object(self.service, '_probe_obs_devices', side_effect=lambda: self.actual_probe(self.service)), \
                         patch.object(self.service, '_cache_devices') as cache, \
                         patch.object(self.service, '_probe_location') as location:
                        state = self.service._run_automatic_readiness()
                    expected_creates = occurrence if operation == 'get_input_properties_list_property_items' else int(operation == 'create_input')
                    self.assertEqual(client.create_input.call_count, expected_creates)
                    self.assertEqual(client.remove_input.call_count, expected_creates)
                    expected_properties = occurrence if operation == 'get_input_properties_list_property_items' else 0
                    self.assertEqual(client.get_input_properties_list_property_items.call_count, expected_properties)
                    client.disconnect.assert_called_once_with()
                    cache.assert_not_called()
                    location.assert_not_called()
                    self.assertFalse(state['ready'])
                    self.assertIsNone(state['checked_at'])

    def test_focus_change_during_connection_releases_socket_and_stops_following_probe(self):
        self.service._startup_launch_attempted = False
        client = MagicMock()
        foreground = {'active': True}

        def connect(*args, **kwargs):
            foreground['active'] = False
            self.service.main_activation_changed()
            foreground['active'] = True
            self.service.main_activation_changed()
            return client

        with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
             patch.object(self.service, '_request_readiness', return_value=False), \
             patch.object(bridge.recorder, 'client', side_effect=connect), \
             patch.object(self.service, '_probe_obs_devices') as probe:
            state = self.service._run_automatic_readiness()
        client.disconnect.assert_called_once_with()
        probe.assert_not_called()
        self.assertTrue(self.service._startup_launch_attempted)
        self.assertFalse(state['ready'])

    def test_blocking_obs_rpc_does_not_hold_service_lock_during_focus_notification(self):
        entered, release = threading.Event(), threading.Event()
        foreground = {'active': True}
        client = MagicMock()

        def status():
            entered.set()
            release.wait(3)
            return SimpleNamespace(output_active=False)

        client.get_record_status.side_effect = status
        with patch.object(self.service, '_main_is_foreground', side_effect=lambda: foreground['active']), \
             patch.object(bridge.recorder, 'client', return_value=client), \
             patch.object(self.service, '_probe_obs_devices', side_effect=lambda: self.actual_probe(self.service)):
            try:
                self.assertTrue(self.service._request_readiness())
                self.assertTrue(entered.wait(2))
                foreground['active'] = False
                began = time.monotonic()
                self.service.main_activation_changed()
                self.assertLess(time.monotonic() - began, .5)
                self.assertTrue(self.service.get_state()['ok'])
            finally:
                release.set()
                self.wait()
        client.get_stream_status.assert_not_called()
        client.create_input.assert_not_called()
        client.disconnect.assert_called_once_with()

    def test_manual_device_probe_and_refresh_remain_available_outside_main_foreground(self):
        client = MagicMock()
        client.get_record_status.return_value.output_active = False
        client.get_stream_status.return_value.output_active = False
        client.get_profile_list.return_value.current_profile_name = 'Experience'
        client.get_scene_collection_list.return_value.current_scene_collection_name = 'Experience'
        client.get_input_list.return_value.inputs = []
        client.get_input_properties_list_property_items.return_value.property_items = []
        with patch.object(self.service, '_main_is_foreground', return_value=False), \
             patch.object(bridge.recorder, 'client', return_value=client):
            devices, problem = self.actual_probe(self.service)
            self.assertIsNone(problem)
            self.assertEqual(set(devices), {'mic', 'window', 'monitor'})
            self.assertEqual(client.create_input.call_count, 3)
            self.assertEqual(client.remove_input.call_count, 3)
            with patch.object(bridge.recorder, 'devices', return_value=deepcopy(self.devices)), \
                 patch.object(self.service, '_recover'):
                self.assertTrue(self.service.refresh_devices()['ok'])
                self.wait()
            self.assertEqual(self.service._device_refresh['state'], 'succeeded')
            self.assertTrue(self.service._readiness['ready'])

    def test_changed_window_class_matches_for_readiness_and_actual_start_without_saving(self):
        old, current = 'Game:OldRandom:game.exe', 'Game:NewRandom:game.exe'
        self.service._cfg.update(window=old, record_inputs=True)
        self.devices['window'] = [dict(itemName='Game', itemValue=current, itemEnabled=True)]
        before = deepcopy(self.service._cfg)
        session = self.session()
        with patch('input_capture.capture_readiness', return_value={'ready': True}) as capture, \
             patch.object(bridge.recorder.Session, 'start', return_value=session) as start:
            state = self.readiness()
            self.assertTrue(state['ready'])
            self.assertEqual(state['window_selection']['resolved'], current)
            self.assertEqual(capture.call_args.args[0]['window'], current)
            # A user's Start operation retains final checking even if focus
            # changes after the click; this is not an automatic idle probe.
            with patch.object(self.service, '_main_is_foreground', return_value=False):
                self.assertTrue(self.service.start_recording()['ok'])
                self.wait()
            self.assertEqual(start.call_args.args[0]['window'], current)
            self.assertEqual(capture.call_args.args[0]['window'], current)
        self.assertEqual(self.service._cfg, before)

    def test_ambiguous_game_process_blocks_start_and_does_not_guess_input_target(self):
        self.service._cfg.update(window='Game:OldRandom:game.exe', record_inputs=True)
        self.devices['window'] = [dict(itemName='Game', itemValue=f'Game:{kind}:game.exe', itemEnabled=True)
                                  for kind in ('One', 'Two')]
        with patch('input_capture.capture_readiness') as capture, patch.object(bridge.recorder.Session, 'start') as start:
            state = self.readiness()
            self.assertEqual([x['code'] for x in state['errors']], ['WINDOW_AMBIGUOUS'])
            self.assertFalse(state['ready'])
            self.service.start_recording()
            self.wait()
            start.assert_not_called()
            capture.assert_not_called()

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
            launch.assert_called_once_with(launch=True, progress=self.service._progress,
                                           continue_if=self.service._automatic_probe_allowed)
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

    def restart_with_bundled_vocabulary(self, config=None):
        directory = self.root / 'vocabularies'
        directory.mkdir(exist_ok=True)
        (directory / 'uiux-terms.txt').write_text('用户体验\nUX\n交互设计', encoding='utf-8')
        self.shutdown()
        with patch.object(bridge, 'load_settings', return_value=deepcopy(config or self.config)):
            self.service = bridge.DesktopService(self.root)
        self.wait()
        return self.service.get_state()['data']['default_hotword_files']

    def test_bundled_defaults_seed_new_presets_without_inheriting_existing_manual_terms(self):
        defaults = self.restart_with_bundled_vocabulary({**self.config, 'hotwords': 'Saved manual term'})
        self.assertEqual(defaults[0]['words'], ['用户体验', 'UX', '交互设计'])
        before = deepcopy(self.service._cfg)
        self.assertEqual(before['hotword_files'], [])
        self.assertEqual(before['hotword_manual'], 'Saved manual term')
        self.assertFalse((self.root / 'config.json').exists())

        result = self.service.save_preset({'name': 'New UI review'})
        self.assertTrue(result['ok'], result)
        self.wait()
        self.assertEqual(result['data']['config']['hotword_files'], defaults)
        self.assertEqual(result['data']['config']['hotword_manual'], '')
        self.assertEqual(result['data']['config']['hotwords'], '用户体验\nUX\n交互设计')
        self.assertEqual(self.service._cfg['presets']['legacy'], before['presets']['legacy'])

    def test_new_preset_explicit_empty_manual_and_legacy_choices_do_not_add_defaults(self):
        defaults = self.restart_with_bundled_vocabulary()
        self.assertTrue(defaults)
        for payload, expected_manual in [
            ({'hotword_manual': 'Typed manual term'}, 'Typed manual term'),
            ({'hotwords': 'Legacy text'}, 'Legacy text'),
            ({'hotword_files': [], 'hotword_manual': ''}, ''),
        ]:
            with self.subTest(payload=payload):
                result = self.service.save_preset({'name': 'Explicit choice', **payload})
                self.assertTrue(result['ok'], result)
                self.wait()
                self.assertEqual(result['data']['config']['hotword_files'], [])
                self.assertEqual(result['data']['config']['hotword_manual'], expected_manual)

        self.assertTrue(self.service.save_preset({'name': 'Defaults enabled'})['ok'])
        self.wait()
        self.assertEqual(self.service._cfg['hotword_files'], defaults)
        empty = self.service.save_preset({'name': 'Explicit empty list', 'hotword_files': []})
        self.assertTrue(empty['ok'], empty)
        self.wait()
        self.assertEqual(empty['data']['config']['hotword_files'], [])

    def test_removed_bundled_default_stays_removed_after_edit_and_reload(self):
        defaults = self.restart_with_bundled_vocabulary()
        result = self.service.save_preset({'name': 'UI review'})
        self.assertTrue(result['ok'], result)
        self.wait()
        ident = result['data']['id']
        removed = self.service.save_preset({'name': 'UI review', 'hotword_files': [],
                                           'hotword_manual': 'Keep my term'}, ident)
        self.assertTrue(removed['ok'], removed)
        self.wait()
        edited = self.service.save_preset({'name': 'Renamed review'}, ident)
        self.assertTrue(edited['ok'], edited)
        self.wait()
        saved = bridge.recorder.read(self.root / 'config.json')
        self.restart_with_bundled_vocabulary(saved)
        self.assertEqual(self.service._cfg['hotword_files'], [])
        self.assertEqual(self.service._cfg['hotword_manual'], 'Keep my term')
        self.assertEqual(self.service._cfg['presets'][ident]['hotword_files'], [])
        self.assertEqual(self.service.get_state()['data']['default_hotword_files'], defaults)
        self.assertTrue(self.service.save_preset({'name': 'Another new review'})['ok'])
        self.wait()
        self.assertEqual(self.service._cfg['hotword_files'], defaults)
        self.assertEqual(self.service._cfg['hotword_manual'], '')
        self.assertEqual(self.service._cfg['presets'][ident]['hotword_files'], [])
        self.assertEqual(self.service._cfg['presets'][ident]['hotword_manual'], 'Keep my term')

    def test_bundled_default_state_and_preset_snapshots_are_independently_owned(self):
        defaults = self.restart_with_bundled_vocabulary()
        expected = deepcopy(defaults)
        self.assertEqual(set(defaults[0]), {'id', 'name', 'words'})
        self.assertNotIn(str(self.root), json.dumps(defaults, ensure_ascii=False))
        defaults[0]['words'].append('Snapshot caller mutation')
        defaults[0]['name'] = 'Changed.txt'
        self.assertEqual(self.service.get_state()['data']['default_hotword_files'], expected)
        result = self.service.save_preset({'name': 'Default ownership'})
        self.assertTrue(result['ok'], result)
        self.wait()
        result['data']['config']['hotword_files'][0]['words'].append('Save response mutation')
        (self.root / 'vocabularies/uiux-terms.txt').write_text('Later disk edit', encoding='utf-8')
        state = self.service.get_state()['data']
        self.assertEqual(state['default_hotword_files'], expected)
        self.assertEqual(state['config']['hotword_files'], expected)

    def test_dictionary_picker_starts_in_vocabulary_directory_without_returning_paths(self):
        directory = self.root / 'vocabularies'
        directory.mkdir()
        file = directory / 'personal.txt'
        file.write_text('Personal term', encoding='utf-8')
        with patch.object(self.service, '_dialog', return_value=(str(file),)) as dialog:
            result = self.service.choose_hotword_files()
        dialog.assert_called_once_with('file', allow_multiple=True,
                                       file_types=('Hotword dictionaries (*.txt;*.scel)',),
                                       directory=str(directory))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['data']['files'][0]['name'], 'personal.txt')
        self.assertNotIn(str(self.root), json.dumps(result, ensure_ascii=False))

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

    def test_bailian_console_opens_only_fixed_url_and_reports_failure(self):
        self.service._cfg['game'] = 'Private project name'
        with patch.object(bridge.webbrowser, 'open', return_value=True) as browser:
            self.assertEqual(self.service.open_bailian_console(), {'ok': True, 'data': {'requested': True}})
        browser.assert_called_once_with('https://bailian.console.aliyun.com/')
        with patch.object(bridge.webbrowser, 'open', return_value=False):
            self.assertFalse(self.service.open_bailian_console()['ok'])
        with patch.object(bridge.webbrowser, 'open', side_effect=OSError('synthetic failure')):
            self.assertFalse(self.service.open_bailian_console()['ok'])

    def test_update_polling_is_read_only_and_startup_never_checks_network(self):
        self.service.set_update_lifecycle(lambda:2,MagicMock())
        self.updates.snapshot.return_value['state']='ready'
        before=deepcopy(self.service._readiness)
        with patch.object(self.service,'close_allowed',side_effect=AssertionError('poll changed close state')):
            for _ in range(3):
                state=self.service.get_state()['data']['updates']
                self.assertTrue(state['can_install'])
                self.assertEqual(state['review_count'],2)
        self.updates.check.assert_not_called()
        self.updates.download.assert_not_called()
        self.model.pause_download.assert_not_called()
        self.assertEqual(before,self.service._readiness)
        self.assertFalse(self.service._closed.is_set())
        self.assertFalse(self.service._exit_pending)

    def test_update_check_download_and_cancel_do_not_claim_recording_activity(self):
        session=self.session(state='录制中')
        self.service._active=session
        before=(deepcopy(self.service._activity),deepcopy(self.service._readiness))
        for payload in ({'action':'check'},{'action':'check','include_prerelease':True},
                        {'action':'download'},{'action':'cancel'}):
            self.assertTrue(self.service.update_action(payload)['ok'])
        self.assertEqual(self.updates.check.call_args_list[0].kwargs,{'include_prerelease':False})
        self.assertEqual(self.updates.check.call_args_list[1].kwargs,{'include_prerelease':True})
        self.updates.download.assert_called_once()
        self.updates.cancel.assert_called_once()
        self.assertEqual(before,(self.service._activity,self.service._readiness))
        self.assertIs(self.service._active,session)
        self.assertFalse(self.service.update_action({'action':'check','include_prerelease':'yes'})['ok'])

    def test_update_install_gate_covers_work_and_rechecks_server_side(self):
        self.service.set_update_lifecycle(lambda:1,MagicMock())
        self.updates.snapshot.return_value['state']='ready'
        cases=[('_active',self.session()),('_obs_uncertain',True),('_uncertain_ids',{'uncertain'}),
               ('_background_jobs',{'queued':{}}),('_dialog_open',True),('_review_opening',1)]
        for field,value in cases:
            with self.subTest(field=field),patch.object(self.service,field,value):
                self.assertFalse(self.service._update_snapshot()['can_install'])
                self.assertFalse(self.service.update_action({'action':'install'})['ok'])
        for kind in ('saving','processing','export','recovery'):
            with self.subTest(kind=kind),patch.dict(self.service._activity,busy=True,kind=kind):
                self.assertFalse(self.service.update_action({'action':'install'})['ok'])
        for state in ('downloading','verifying'):
            with self.subTest(model=state),patch.dict(self.model.status.return_value,state=state):
                self.assertFalse(self.service.update_action({'action':'install'})['ok'])
        self.model.wait.return_value=False
        self.assertFalse(self.service.update_action({'action':'install'})['ok'])
        self.updates.prepare_install.assert_not_called()
        self.assertFalse(self.service._exit_pending)

    def test_update_release_link_is_fixed_to_project_without_arbitrary_url(self):
        with patch.object(bridge.webbrowser,'open',return_value=True) as browser:
            self.assertTrue(self.service.update_action({'action':'open_release'})['ok'])
            browser.assert_called_once_with('https://github.com/Elkhiffa/think-aloud-recorder/releases')
        self.updates.snapshot.return_value['release_url']='https://example.org/collect'
        with patch.object(bridge.webbrowser,'open') as browser:
            self.assertFalse(self.service.update_action({'action':'open_release'})['ok'])
            browser.assert_not_called()

    def test_update_install_prepares_before_cleanup_and_closes_only_after_helper_launch(self):
        calls=[]
        prepared={'synthetic':'prepared-job'}
        self.updates.snapshot.return_value['state']='ready'
        self.updates.prepare_install.side_effect=lambda pid:(calls.append(('prepare',pid)) or prepared)
        self.updates.launch_install.side_effect=lambda plan:(calls.append(('launch',plan)) or {'ready':True})
        def close_windows():
            self.assertTrue(self.service.update_close_ready())
            self.assertFalse(self.service.close_allowed())
            self.assertTrue(self.service.close_allowed(for_update=True))
            calls.append(('close',None))
        self.service.set_update_lifecycle(lambda:2,close_windows)
        with patch.object(bridge.recorder,'shutdown_owned_obs',side_effect=lambda root:(calls.append(('obs',root)) or {'status':'closed'})):
            self.assertTrue(self.service.update_action({'action':'install'})['ok'])
            self.wait()
        self.assertEqual([call[0] for call in calls],['prepare','obs','launch','close'])
        self.assertEqual(calls[0][1],bridge.os.getpid())
        self.assertTrue(self.service._closed.is_set())
        self.updates.cancel_install.assert_not_called()

    def test_update_admission_atomically_blocks_new_work_and_double_install(self):
        entered,release=threading.Event(),threading.Event()
        self.updates.snapshot.return_value['state']='ready'
        self.updates.prepare_install.side_effect=lambda pid:(entered.set(),release.wait(3),{})[-1]
        self.service.set_update_lifecycle(lambda:0,MagicMock())
        with patch.object(bridge.recorder,'shutdown_owned_obs',return_value={'status':'not_owned'}):
            try:
                self.assertTrue(self.service.update_action({'action':'install'})['ok'])
                self.assertTrue(entered.wait(1))
                self.assertFalse(self.service.update_action({'action':'install'})['ok'])
                self.assertFalse(self.service.start_recording({})['ok'])
                self.assertFalse(self.service.model_action('download')['ok'])
                self.assertFalse(self.service.open_review('not-admitted')['ok'])
                self.assertFalse(self.service.close_allowed())
                self.model.start_download.assert_not_called()
                self.assertFalse(self.service._closed.is_set())
            finally:
                release.set();self.wait()

    def test_update_prepare_failure_keeps_windows_engine_and_app_available(self):
        self.updates.snapshot.return_value['state']='ready'
        self.updates.prepare_install.side_effect=RuntimeError('synthetic helper preparation failure')
        close=MagicMock()
        self.service.set_update_lifecycle(lambda:1,close)
        with patch.object(bridge.recorder,'shutdown_owned_obs') as shutdown:
            self.assertTrue(self.service.update_action({'action':'install'})['ok'])
            self.wait()
        shutdown.assert_not_called();close.assert_not_called()
        self.assertFalse(self.service._exit_pending)
        self.assertFalse(self.service._closed.is_set())
        self.assertIn('preparation failure',self.service.get_state()['data']['updates']['error'])

    def test_unconfirmed_obs_cleanup_cancels_update_and_reopens_app_connection_gate(self):
        self.updates.snapshot.return_value['state']='ready'
        prepared={'synthetic':'prepared-job'}
        self.updates.prepare_install.return_value=prepared
        close=MagicMock()
        self.service.set_update_lifecycle(lambda:1,close)
        with bridge.recorder._obs_process_lock:bridge.recorder._obs_closed_roots.add(self.root)
        with patch.object(bridge.recorder,'shutdown_owned_obs',return_value={'status':'close_unconfirmed'}):
            self.assertTrue(self.service.update_action({'action':'install'})['ok'])
            self.wait()
        self.updates.launch_install.assert_not_called();close.assert_not_called()
        self.updates.cancel_install.assert_called_once_with(prepared)
        self.assertNotIn(self.root,bridge.recorder._obs_closed_roots)
        self.assertFalse(self.service._closed.is_set())
        self.assertFalse(self.service._exit_pending)
        self.assertIn('未开始更新',self.service.get_state()['data']['updates']['error'])

    def test_failed_window_close_cancels_prepared_helper_before_later_normal_exit(self):
        self.updates.snapshot.return_value['state']='ready'
        prepared={'synthetic':'prepared-job'}
        self.updates.prepare_install.return_value=prepared
        self.service.set_update_lifecycle(lambda:1,MagicMock(side_effect=RuntimeError('synthetic review remains open')))
        with patch.object(bridge.recorder,'shutdown_owned_obs',return_value={'status':'already_exited'}):
            self.assertTrue(self.service.update_action({'action':'install'})['ok'])
            self.wait()
        self.updates.cancel_install.assert_called_once_with(prepared)
        self.assertFalse(self.service.update_in_progress())
        self.assertFalse(self.service._exit_pending)
        self.assertFalse(self.service._closed.is_set())
        self.assertIn('remains open',self.service.get_state()['data']['updates']['error'])

    def test_failed_durable_cancel_blocks_close_until_explicit_retry_succeeds(self):
        self.updates.snapshot.return_value['state']='ready'
        prepared={'synthetic':'prepared-job'}
        self.updates.prepare_install.return_value=prepared
        self.updates.cancel_install.side_effect=OSError('synthetic disk unavailable')
        self.service.set_update_lifecycle(lambda:1,MagicMock(side_effect=RuntimeError('viewer remains open')))
        with patch.object(bridge.recorder,'shutdown_owned_obs',return_value={'status':'closed'}):
            self.assertTrue(self.service.update_action({'action':'install'})['ok'])
            self.wait()
        self.assertIs(self.service._update_pending_cancel,prepared)
        self.assertTrue(self.service._exit_pending)
        self.assertTrue(self.service.update_in_progress())
        self.assertFalse(self.service.update_close_ready())
        self.assertFalse(self.service.close_allowed())
        self.assertEqual(self.service.shutdown(),{'status':'close_not_accepted'})
        self.assertFalse(self.service.start_recording({})['ok'])
        self.assertFalse(self.service.update_action({'action':'check'})['ok'])
        snapshot=self.service.get_state()['data']['updates']
        self.assertTrue(snapshot['cancel_pending'])
        self.assertFalse(snapshot['can_install'])
        self.assertIn('重试取消',snapshot['error'])
        # Retrying unsuccessfully must not clear the admission or descriptor.
        self.assertTrue(self.service.update_action({'action':'cancel'})['ok'])
        self.wait()
        self.assertFalse(self.service.close_allowed())
        self.updates.cancel_install.side_effect=None
        self.assertTrue(self.service.update_action({'action':'cancel'})['ok'])
        self.wait()
        self.assertFalse(self.service.get_state()['data']['updates']['cancel_pending'])
        self.assertIsNone(self.service._update_pending_cancel)
        self.assertFalse(self.service._exit_pending)
        self.assertTrue(self.service.close_allowed())

    def test_missing_helper_ack_never_closes_windows(self):
        self.updates.snapshot.return_value['state']='ready'
        self.updates.prepare_install.return_value={'synthetic':'prepared-job'}
        self.updates.launch_install.return_value={'ready':False}
        close=MagicMock()
        self.service.set_update_lifecycle(lambda:1,close)
        with patch.object(bridge.recorder,'shutdown_owned_obs',return_value={'status':'closed'}):
            self.assertTrue(self.service.update_action({'action':'install'})['ok'])
            self.wait()
        close.assert_not_called()
        self.updates.cancel_install.assert_called_once()
        self.assertFalse(self.service._exit_pending)

    def test_update_manual_main_close_cannot_remove_surface_before_failed_viewer_and_cancel(self):
        from window_manager import WindowManager
        class Event:
            def __iadd__(self,handler):
                self.handler=handler
                return self
        main=MagicMock()
        main.events=SimpleNamespace(closing=Event(),closed=Event())
        manager=WindowManager(self.service,MagicMock())
        manager.bind_main(main)
        viewer=MagicMock()
        manager._viewers['review']=viewer
        def try_manual_close():
            self.assertTrue(self.service.update_close_ready())
            self.assertFalse(main.events.closing.handler())
        viewer.destroy.side_effect=try_manual_close
        self.service.set_update_lifecycle(manager.review_count,lambda:manager.close_for_update(timeout=.01))
        self.updates.snapshot.return_value['state']='ready'
        self.updates.prepare_install.return_value={'synthetic':'prepared-job'}
        self.updates.cancel_install.side_effect=OSError('synthetic durable cancel failure')
        with patch.object(bridge.recorder,'shutdown_owned_obs',return_value={'status':'closed'}):
            self.assertTrue(self.service.update_action({'action':'install'})['ok'])
            self.wait()
        viewer.destroy.assert_called_once()
        main.destroy.assert_not_called()
        self.assertTrue(self.service.get_state()['data']['updates']['cancel_pending'])
        self.assertFalse(main.events.closing.handler())
        self.assertFalse(self.service._closed.is_set())
        # The last viewer later closing must still leave the main surface alive
        # and blocked until the durable cancellation has succeeded.
        manager._viewers.clear()
        self.assertFalse(main.events.closing.handler())
        self.updates.cancel_install.side_effect=None
        self.assertTrue(self.service.update_action({'action':'cancel'})['ok'])
        self.wait()
        self.assertTrue(main.events.closing.handler())

    def test_update_admission_between_native_close_reads_still_refuses_ordinary_close(self):
        from window_manager import WindowManager
        manager=WindowManager(self.service,MagicMock())
        manager.main=MagicMock()
        def raced_read():
            self.service._update_installing=True
            self.service._update_commit=True
            self.service._exit_pending=True
            return False
        with patch.object(self.service,'update_in_progress',side_effect=[raced_read(),True]):
            self.assertFalse(manager.close_main())
        manager.main.create_confirmation_dialog.assert_not_called()
        self.assertFalse(self.service._closed.is_set())

    def test_real_update_manager_check_uses_production_snapshot_without_recording_side_effects(self):
        import httpx
        (self.root/'portable.json').write_text(json.dumps({'version':'0.6.0'}),encoding='utf-8')
        calls=[]
        def response(request):
            calls.append(str(request.url))
            return httpx.Response(200,json=[])
        manager=RealUpdateManager(self.root,client_factory=lambda:httpx.Client(transport=httpx.MockTransport(response)))
        self.service._updates=manager
        self.service._active=self.session(state='录制中')
        before=(deepcopy(self.service._activity),deepcopy(self.service._readiness))
        self.assertEqual(self.service.get_state()['data']['updates']['state'],'idle')
        self.assertEqual(calls,[])
        self.assertTrue(self.service.update_action({'action':'check'})['ok'])
        self.assertTrue(manager.wait(2))
        snapshot=self.service.get_state()['data']['updates']
        self.assertEqual(snapshot['state'],'no_release')
        self.assertFalse(snapshot['include_prerelease'])
        self.assertFalse(snapshot['can_install'])
        self.assertEqual(len(calls),1)
        self.assertTrue(calls[0].startswith('https://api.github.com/repos/Elkhiffa/think-aloud-recorder/releases?'))
        self.assertEqual(before,(self.service._activity,self.service._readiness))

    @unittest.skipUnless(os.name=='nt','external helper uses Windows process handles and file locks')
    def test_real_manager_helper_handshake_and_cancel_after_viewer_close_failure(self):
        """Real helper/native wait; synthetic package, OBS, view and self-check.

        The borrowed test interpreter executes the copied helper outside the
        target. Full packaged-runtime install/restart is a separate smoke test.
        """
        from update_installer import atomic_json
        # The class was imported before the constructor mock. Its globals are
        # the production module, independent from setUp's sys.modules adapter.
        module_globals=RealUpdateManager.prepare_install.__globals__
        def package(folder,version,code):
            files={'app.py':code,'portable_entry.py':b'entry','ExperienceRecorder.exe':b'MZ synthetic',
                   'runtime/python.exe':b'MZ fixture','runtime/pythonw.exe':b'MZ fixture',
                   'ui/index.html':b'<p>fixture</p>',
                   'portable.json':json.dumps({'version':version,'platform':'windows-x64','release_status':'public'}).encode()}
            for name,content in files.items():
                path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)
            atomic_json(folder/'package-manifest.json',{'schema':1,'dependency_source_status':True,
                'files':[{'path':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()} for name,content in files.items()]})
        with TemporaryDirectory() as directory:
            base=Path(directory);root=base/'installation';work=base/'transaction';stage=work/'package'
            package(root,'0.6.0',b'old synthetic code');package(stage,'0.7.0',b'new synthetic code')
            manager=RealUpdateManager(root)
            manager._stage,manager._work=stage,work
            manager._set(state='ready',latest_version='0.7.0')
            self.service._updates=manager
            self.service.root=root
            def close_failed():
                attempt=Path(manager._prepared['job_path']).parent
                ready=json.loads((attempt/'helper-ready.json').read_text(encoding='utf-8'))
                self.assertEqual(ready['phase'],'waiting_parent')
                self.assertEqual(ready['pid'],manager._installer.pid)
                self.assertIsNone(manager._installer.poll())
                self.assertEqual((root/'app.py').read_bytes(),b'old synthetic code')
                raise RuntimeError('synthetic viewer remains open')
            self.service.set_update_lifecycle(lambda:1,close_failed)
            real_popen=subprocess.Popen
            def borrowed_runtime(command,**kwargs):
                self.assertEqual(Path(command[0]).resolve(),(stage/'runtime/pythonw.exe').resolve())
                return real_popen([sys.executable,*command[1:]],**kwargs)
            def fail_cancel_write(path,value):
                if Path(path).name=='cancel.json':raise OSError('synthetic disk failure writing cancel fence')
                return atomic_json(path,value)
            try:
                with patch.dict(module_globals,{'self_check':lambda *_:None,'atomic_json':fail_cancel_write}), \
                     patch.object(subprocess,'Popen',side_effect=borrowed_runtime), \
                     patch.object(bridge.recorder,'shutdown_owned_obs',return_value={'status':'not_owned'}):
                    self.assertTrue(self.service.update_action({'action':'install'})['ok'])
                    self.wait()
                self.assertIsNotNone(manager._installer,self.service._update_install_error)
                attempt=Path(manager._prepared['job_path']).parent
                self.assertEqual(attempt.parent,work)
                self.assertIsNone(manager._installer.poll())
                self.assertFalse((attempt/'cancel.json').exists())
                self.assertTrue(self.service.get_state()['data']['updates']['cancel_pending'])
                self.assertFalse(self.service.close_allowed())
                self.assertEqual((root/'app.py').read_bytes(),b'old synthetic code')
                # Retry the real durable cancellation while the original
                # parent is still alive. Only this fence restores normal X.
                self.assertTrue(self.service.update_action({'action':'cancel'})['ok'])
                self.wait()
                self.assertEqual(manager._installer.wait(timeout=5),1)
                self.assertTrue((attempt/'cancel.json').is_file())
                self.assertEqual(json.loads((attempt/'job.json').read_text(encoding='utf-8'))['state'],'failed')
                self.assertEqual((root/'app.py').read_bytes(),b'old synthetic code')
                self.assertFalse((attempt/'backup').exists())
                self.assertFalse(self.service.get_state()['data']['updates']['cancel_pending'])
                self.assertFalse(self.service._exit_pending)
                self.assertIn('已取消',self.service.get_state()['data']['updates']['error'])
                self.assertTrue(self.service.close_allowed())
            finally:
                # Cooperative only: leave the durable fence and wait for helper.
                if manager._prepared is not None:manager.cancel_install(manager._prepared)
                if manager._installer is not None:manager._installer.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
