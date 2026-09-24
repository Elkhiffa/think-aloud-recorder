import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app_paths import application_root, installation_root, vocabulary_dir
import portable_config
from portable_check import settings_for_check
from hotword_files import bundled_dictionary_snapshots
from scripts import migrate_layout as migration
from update_installer import atomic_json, sha256, UpdateError
from test_update_installer import fixture


def compact(root):
    flat = fixture(root / 'app', launcher='Think Aloud.exe')
    (flat / 'Think Aloud.exe').rename(root / 'Think Aloud.exe')
    (flat / 'vocabularies').rename(root / 'vocabularies')
    atomic_json(flat / 'portable.json', {'layout': 'compact-v1', 'version': '1.1.0',
                                       'platform': 'windows-x64', 'release_status': 'public'})
    files = [p for p in root.rglob('*') if p.is_file() and p.name != 'package-manifest.json']
    atomic_json(flat / 'package-manifest.json', {'schema': 1, 'dependency_source_status': True,
        'files': [{'path': p.relative_to(root).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha256(p)} for p in files]})
    return root


class PathContractTests(unittest.TestCase):
    def test_plain_app_named_source_directory_is_not_mistaken_for_compact_package(self):
        with TemporaryDirectory() as tmp:
            app = Path(tmp).resolve() / 'app'; app.mkdir()
            self.assertEqual(installation_root(app), app)
            self.assertEqual(portable_config.default_vault_path(app), app.parent / 'think-aloud-database')

    def test_compact_library_roundtrip_and_dictionary_stay_outside_app(self):
        with TemporaryDirectory() as tmp:
            root = compact(Path(tmp).resolve() / '安装目录')
            app = root / 'app'
            self.assertEqual(application_root(root), app)
            self.assertEqual(installation_root(app), root)
            self.assertEqual(vocabulary_dir(app), root / 'vocabularies')
            self.assertEqual(portable_config.default_vault_path(app), root.parent / 'think-aloud-database')
            settings = {'vault': str(root / 'my-library'), '_portable_root': str(root),
                        '_portable_machine': 'fixture', 'port': 4567, 'password': 'synthetic-only',
                        'presets': {'a': {'vault': str(root / 'my-library'), 'mic': 'fixture-mic', 'configured': True}}}
            saved = portable_config.stored_settings(app, settings)
            atomic_json(app / 'config.json', saved)
            before = (app / 'config.json').read_bytes()
            with patch.object(portable_config, '_setup_obs', side_effect=AssertionError('must not reset OBS')):
                portable_config._initialize_locked(app, 'fixture')
            with patch.object(portable_config, 'initialize'):
                loaded = portable_config.load_settings(app)
            self.assertEqual(loaded['vault'], settings['vault'])
            self.assertEqual(loaded['presets']['a']['vault'], settings['vault'])
            self.assertEqual(settings_for_check(app)['vault'], settings['vault'])
            self.assertEqual((app / 'config.json').read_bytes(), before)
            self.assertTrue(bundled_dictionary_snapshots(app))


class MigrationTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.root = fixture(self.base / 'installed', launcher='Think Aloud.exe')
        self.package = compact(self.base / 'package')
        self.work = self.base / 'backup'
        self.config = {'_portable_root': str(self.base / 'previous-name'), 'vault': str(self.base / 'library'),
                       'port': 9876, 'password': 'synthetic-only', '_portable_machine': 'same'}
        atomic_json(self.root / 'config.json', self.config)
        self.write('state/secrets/qwen.dpapi', b'synthetic encrypted sentinel')
        self.write('vocabularies/personal.txt', b'user words')
        self.write('tools/obs/config/obs-studio/basic/scenes/Experience.json', b'user-scene')
        self.write('tools/obs/config/obs-studio/basic/profiles/Experience/basic.ini',
                   ('[AdvOut]\nRecFilePath=' + str(self.root / 'staging') + '\nOther=user\n').encode())
        self.write('my-notes.txt', b'unknown root user content')
        self.write('runtime/custom-note.txt', b'unknown nested user content')
        # Tools is managed in real packages, include it in this synthetic inventory.
        manifest = json.loads((self.root / 'package-manifest.json').read_text())
        p = self.write('tools/obs/bin/64bit/obs64.exe', b'MZ fixture')
        manifest['files'].append({'path': 'tools/obs/bin/64bit/obs64.exe', 'bytes': p.stat().st_size, 'sha256': sha256(p)})
        atomic_json(self.root / 'package-manifest.json', manifest)
        self.guard = patch.object(migration, 'blockers', return_value=[]); self.guard.start(); self.addCleanup(self.guard.stop)

    def write(self, name, raw):
        p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(raw); return p

    def test_migration_preserves_data_and_records_only_location_adjustment(self):
        job = migration.prepare(self.root, self.package, self.work)
        migration.apply(job, checker=lambda root, work: None)
        cfg = json.loads((self.root / 'app/config.json').read_text())
        self.assertEqual(cfg, {**self.config, '_portable_root': str(self.root)})
        for name in ('state/secrets/qwen.dpapi', 'tools/obs/config/obs-studio/basic/scenes/Experience.json', 'runtime/custom-note.txt'):
            self.assertEqual((self.root / 'app' / name).read_bytes(), (self.work / 'original' / name).read_bytes())
        self.assertEqual((self.root / 'my-notes.txt').read_bytes(), b'unknown root user content')
        self.assertEqual((self.root / 'vocabularies/personal.txt').read_bytes(), b'user words')
        self.assertIn(str(self.root / 'app/staging'), (self.root / 'app/tools/obs/config/obs-studio/basic/profiles/Experience/basic.ini').read_text())
        self.assertEqual(json.loads((self.work / 'user-data/config.json').read_text()), self.config)

    def test_partial_move_and_failed_check_restore_every_original_byte(self):
        original = migration.fingerprint(self.root, [p.name for p in self.root.iterdir()])
        job = migration.prepare(self.root, self.package, self.work)
        def fail(*args): raise RuntimeError('synthetic failure')
        with self.assertRaises(RuntimeError): migration.apply(job, checker=fail)
        self.assertEqual(migration.fingerprint(self.root, [p.name for p in self.root.iterdir()]), original)
        self.assertFalse((self.root / 'app').exists())
        second = migration.prepare(self.root, self.package, self.base / 'second-backup')
        with self.assertRaises(RuntimeError): migration.apply(second, checker=lambda *a: None, after_move=fail)
        self.assertEqual(migration.fingerprint(self.root, [p.name for p in self.root.iterdir()]), original)

    def test_changed_config_after_preparation_is_not_overwritten(self):
        job = migration.prepare(self.root, self.package, self.work)
        self.write('config.json', b'new user change')
        with self.assertRaises(UpdateError): migration.apply(job, checker=lambda *a: None)
        self.assertEqual((self.root / 'config.json').read_bytes(), b'new user change')
        self.assertFalse((self.root / 'app').exists())

    def test_changed_vocabulary_after_preparation_stops_migration(self):
        job = migration.prepare(self.root, self.package, self.work)
        (self.root / 'vocabularies').rename(self.root / 'words-moved-by-user')
        with self.assertRaises(UpdateError): migration.apply(job, checker=lambda *a: None)
        self.assertFalse((self.root / 'app').exists())

    def test_recovery_rejects_unrelated_file_and_wrong_journal_location(self):
        job = migration.prepare(self.root, self.package, self.work)
        job.update(state='applying', published=['my-notes.txt'])
        with self.assertRaises(UpdateError): migration.recover(job)
        self.assertEqual((self.root / 'my-notes.txt').read_bytes(), b'unknown root user content')
        job['published'] = []
        with self.assertRaises(UpdateError): migration.recover(job, self.base / 'unrelated.json')

    def test_model_paths_keep_external_and_unmoved_user_directories(self):
        (self.root / 'custom-model').mkdir()
        atomic_json(self.root / 'state/models.json', {'path': 'custom-model', 'relative': True})
        job = migration.prepare(self.root, self.package, self.work)
        registry = json.loads((self.work / 'candidate/app/state/models.json').read_text())
        self.assertEqual(registry, {'path': str(self.root / 'custom-model'), 'relative': False})
        self.assertTrue((self.root / 'custom-model').is_dir())

    def test_missing_backup_is_not_reported_as_successful_recovery(self):
        job = migration.prepare(self.root, self.package, self.work)
        (self.root / 'config.json').rename(self.work / 'simulate-lost-backup.json')
        job.update(state='applying', moved=['config.json'])
        with self.assertRaises(UpdateError): migration.recover(job)
        self.assertEqual(job['state'], 'recovery_required')
        self.assertFalse((self.root / 'config.json').exists())


if __name__ == '__main__': unittest.main()
