"""Synthetic live vocabulary bridge; no real user configuration or audio."""
from copy import deepcopy
import contextlib
import http.client
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from desktop_service import DesktopService
from hotword_files import compile_hotword_snapshots, dictionary_id
import recorder
import vocabulary_agent as vocab
from vocabulary_ipc import VocabularyServer, request, ENDPOINT


class VocabularyAgentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.directory = self.root / 'vocabularies'
        self.directory.mkdir()
        self.names = ['synthetic-game.txt', 'synthetic-ux.txt']
        files = []
        for name, word in zip(self.names, ['合成场景', '交互反馈']):
            files.append(dict(name=name, words=[word], id=dictionary_id([word])))
            (self.directory / name).write_text(word + '\n新增词\n', encoding='utf-8')
        compiled = compile_hotword_snapshots(files, '手动词\n', qwen=True)
        preset = dict(name='Synthetic game', game='Synthetic game', transcription_provider='qwen',
                      configured=True, vault=str(self.root / 'library'), **compiled)
        cfg = dict(preset, active_preset_id='one', password='synthetic-private-password',
                   port=12345, presets={'one': deepcopy(preset), 'two': deepcopy(preset)},
                   games={'legacy': {'hotwords': '历史词'}})
        recorder.write(self.root / 'config.json', cfg)
        recorder.write(self.root / 'portable.json', {'version': '0.7.5'})
        service = self.service = DesktopService.__new__(DesktopService)
        service.root, service._cfg = self.root, deepcopy(cfg)
        service._lock, service._operation_lock = threading.RLock(), threading.RLock()
        service._closed = threading.Event()
        service._exit_pending = service._dialog_open = service._obs_uncertain = False
        service._active, service._uncertain_ids = None, set()
        service._activity = dict(busy=False)
        service._config_file_revision = vocab.file_digest(self.root / 'config.json')
        self.original = deepcopy(cfg)

    def preview(self):
        result = self.service._vocabulary_request(dict(action='preview', preset_id='one', sources=self.names))
        self.assertTrue(result['ok'], result)
        return result['data']

    def apply(self, plan):
        return self.service._vocabulary_request(dict(action='apply', plan=plan))

    def test_refresh_preserves_manual_other_settings_sources_and_history(self):
        historical = self.root / 'session.json'
        recorder.write(historical, dict(settings=deepcopy(self.original), state='转写中'))
        before = historical.read_bytes()
        config_bytes = (self.root / 'config.json').read_bytes()
        sources = {name: (self.directory / name).read_bytes() for name in self.names}
        plan = self.preview()
        self.assertEqual((self.root / 'config.json').read_bytes(), config_bytes)
        self.assertEqual(plan['after']['total_words'], 4)
        result = self.apply(plan)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['data']['saved'], result['data']['effective'])
        self.assertEqual(result['data']['saved']['total_words'], 4)
        after = recorder.read(self.root / 'config.json')
        self.assertEqual(after['hotword_manual'], '手动词\n')
        self.assertEqual(after['presets']['two'], self.original['presets']['two'])
        for key in ('games', 'password', 'port', 'active_preset_id'):
            self.assertEqual(after[key], self.original[key])
        self.assertEqual(historical.read_bytes(), before)
        self.assertEqual(sources, {name: (self.directory / name).read_bytes() for name in self.names})
        self.assertFalse(result['data']['transcription_started'])

    def test_lost_response_retry_is_noop_and_does_not_write(self):
        plan = self.preview()
        self.assertTrue(self.apply(plan)['ok'])
        with patch.object(self.service, '_persist_vocabulary', side_effect=AssertionError('must not write')):
            result = self.apply(plan)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['data']['changed'])

    def test_truncated_source_only_adds_never_removes_snapshot_terms(self):
        (self.directory / self.names[0]).write_text('仅新增\n', encoding='utf-8')
        plan = self.preview()
        self.assertEqual(plan['sources'][0]['retained_missing_words'], 1)
        self.assertTrue(self.apply(plan)['ok'])
        self.assertIn('合成场景', self.service._cfg['hotwords'])

    def test_source_and_preset_changes_make_preview_stale(self):
        plan = self.preview()
        (self.directory / self.names[0]).write_text('又新增\n', encoding='utf-8')
        self.assertEqual(self.apply(plan)['code'], 'CONFLICT')
        plan = self.preview()
        self.service._cfg['presets']['one']['mic'] = 'changed-device'
        self.assertEqual(self.apply(plan)['code'], 'CONFLICT')
        self.assertEqual(recorder.read(self.root / 'config.json'), self.original)

    def test_external_config_change_is_not_overwritten(self):
        plan = self.preview()
        external = deepcopy(self.original)
        external['presets']['two']['name'] = 'External edit'
        recorder.write(self.root / 'config.json', external)
        self.assertEqual(self.apply(plan)['code'], 'CONFIG_CHANGED')
        self.assertEqual(recorder.read(self.root / 'config.json'), external)

    def test_busy_recording_dialog_and_closing_leave_everything_intact(self):
        plan = self.preview()
        for attr, value, code in [('_active', object(), 'BUSY'), ('_dialog_open', True, 'BUSY'),
                                  ('_activity', {'busy': True}, 'BUSY'), ('_exit_pending', True, 'APP_CLOSING')]:
            with self.subTest(attr=attr), patch.object(self.service, attr, value):
                self.assertEqual(self.apply(plan)['code'], code)
        self.assertEqual(recorder.read(self.root / 'config.json'), self.original)
        self.assertTrue(self.apply(plan)['ok'])

    def test_operation_in_progress_returns_busy_without_waiting(self):
        plan = self.preview()
        entered, release = threading.Event(), threading.Event()
        def holding():
            with self.service._operation_lock:
                entered.set()
                release.wait(5)
        worker = threading.Thread(target=holding)
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.apply(plan)['code'], 'BUSY')
        finally:
            release.set()
            worker.join(2)

    def test_failed_persist_does_not_update_live_snapshot(self):
        plan = self.preview()
        with patch.object(self.service, '_persist_vocabulary', side_effect=PermissionError('locked')):
            self.assertFalse(self.apply(plan)['ok'])
        self.assertEqual(self.service._cfg, self.original)
        self.assertEqual(recorder.read(self.root / 'config.json'), self.original)

    def test_invalid_lengths_and_combined_limits_do_not_write(self):
        for text in ['过' * 16, '\n'.join('word' + str(i) for i in range(1999))]:
            (self.directory / self.names[0]).write_text(text, encoding='utf-8')
            result = self.service._vocabulary_request(dict(action='preview', preset_id='one', sources=self.names))
            self.assertFalse(result['ok'], result)
            self.assertEqual(self.service._cfg, self.original)

    def test_paths_ambiguous_names_wrong_install_and_tampered_plan(self):
        for name in ['../escape.txt', 'nested/a.txt', 'x.txt:stream', 'a.scel']:
            with self.subTest(name=name), self.assertRaises(vocab.VocabularyError):
                vocab.status(self.root, self.original, sources=[name])
        self.service._cfg['presets']['one']['hotword_files'].append(
            dict(name=self.names[0], words=['其他'], id=dictionary_id(['其他'])))
        result = self.service._vocabulary_request(dict(action='preview', preset_id='one', sources=self.names))
        self.assertEqual(result['code'], 'SOURCE_NOT_UNIQUE')
        self.service._cfg = deepcopy(self.original)
        plan = self.preview()
        plan['after']['total_words'] = 900
        self.assertEqual(self.apply(plan)['code'], 'INVALID_PLAN')
        plan = self.preview()
        plan['app_root'] = str(self.root.parent)
        plan['plan_id'] = vocab.digest({k: v for k, v in plan.items() if k != 'plan_id'})
        self.assertEqual(self.apply(plan)['code'], 'INVALID_PLAN')

    def test_inactive_preset_refresh_does_not_select_it(self):
        plan, _ = vocab.preview(self.root, self.original, 'two', self.names)
        result = self.apply(plan)
        self.assertTrue(result['ok'], result)
        self.assertFalse(result['data']['effective']['active'])
        self.assertEqual(self.service._cfg['hotwords'], self.original['hotwords'])
        self.assertEqual(self.service._cfg['active_preset_id'], 'one')

    def test_stale_open_settings_cannot_restore_old_vocabulary(self):
        old_revision = self.service._public_config()['vocabulary_revision']
        self.assertTrue(self.apply(self.preview())['ok'])
        with self.assertRaisesRegex(ValueError, '词库已被其他操作更新'):
            self.service._save(dict(expected_vocabulary_revision=old_revision,
                                    hotword_files=self.original['hotword_files']))

    def test_live_ipc_cli_preview_apply_authentication_and_shutdown(self):
        server = VocabularyServer(self.root, self.service._vocabulary_request).start()
        try:
            result = request(self.root, dict(action='status', preset_id='one', sources=self.names))
            self.assertTrue(result['ok'], result)
            self.assertNotIn('synthetic-private-password', json.dumps(result))
            self.assertNotIn('手动词', json.dumps(result, ensure_ascii=False))
            import agent_cli
            plan_file = self.root / 'plan.json'
            common = ['--app-root', str(self.root)]
            with contextlib.redirect_stdout(io.StringIO()) as output:
                code = agent_cli.main(['vocabulary-preview', *common, '--preset', 'one',
                                       '--source', self.names[0], '--source', self.names[1], '--output', str(plan_file)])
            self.assertEqual(code, 0, output.getvalue())
            process = subprocess.run([sys.executable, '-X', 'utf8', str(Path(agent_cli.__file__)),
                                      'vocabulary-apply', *common, '--plan', str(plan_file)],
                                     capture_output=True, text=True, encoding='utf-8', timeout=20)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(json.loads(process.stdout)['data']['saved']['total_words'], 4)
            for headers in [{}, {'Authorization': 'Bearer ' + server.token, 'Origin': 'https://example.com'}]:
                connection = http.client.HTTPConnection('127.0.0.1', server.server.server_port, timeout=3)
                connection.request('POST', '/vocabulary', '{}', headers=headers)
                response = connection.getresponse()
                self.assertEqual(response.status, 403)
                response.read()
                connection.close()
        finally:
            server.close()
        self.assertFalse((self.root / ENDPOINT).exists())
        self.assertEqual(request(self.root, dict(action='status'))['code'], 'APP_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
