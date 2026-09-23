import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_runtime_seed import seed_managed_path, verify_runtime_seed


class RuntimeSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'package'
        self.root.mkdir()
        self.files = {}
        for name, data in (
                ('runtime/python.exe', b'MZ synthetic Python'),
                ('runtime/Lib/site-packages/small_module.py', b'VALUE = 1\n'),
                ('tools/obs/bin/64bit/obs64.exe', b'MZ synthetic OBS'),
                ('tools/input/SDL2.dll', b'MZ synthetic SDL')):
            self.files[name] = self.write(name, data)
        self.lock = {'schema': 1,
                     'baseline': {'version': '0.6.0-preview.4', 'package_manifest_sha256': 'a' * 64},
                     'files': [self.record(name) for name in self.files]}
        self.save_lock()
        self.save_package()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def record(self, name):
        data = (self.root / name).read_bytes()
        return {'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

    def save_lock(self):
        self.write('scripts/runtime-seed.json', json.dumps(self.lock).encode())

    def save_package(self, records=None):
        self.write('package-manifest.json', json.dumps({'schema': 1, 'files':
            records if records is not None else [self.record(name) for name in self.files]}).encode())

    def test_fixed_baseline_matches_both_call_modes(self):
        built = verify_runtime_seed(self.root, self.files)
        self.assertEqual(built, verify_runtime_seed(self.root))
        self.assertEqual(built['files'], 4)
        self.assertEqual(built['bytes'], sum(r['bytes'] for r in self.lock['files']))
        self.assertEqual(built['baseline_package_manifest_sha256'], 'a' * 64)
        self.assertFalse(built['upstream_signatures_or_rebuild_verified'])

    def test_small_python_module_tamper_fails_despite_regenerated_package_inventory(self):
        name = 'runtime/Lib/site-packages/small_module.py'
        self.write(name, b'VALUE = 2\n')
        self.save_package()
        for actual in (None, self.files):
            with self.subTest(mode=actual is None), self.assertRaisesRegex(ValueError, 'content mismatch'):
                verify_runtime_seed(self.root, actual)

    def test_added_dependency_fails_in_both_modes(self):
        name = 'runtime/Lib/site-packages/unreviewed.py'
        self.files[name] = self.write(name, b'extra')
        self.save_package()
        for actual in (None, self.files):
            with self.subTest(mode=actual is None), self.assertRaisesRegex(ValueError, 'extra:'):
                verify_runtime_seed(self.root, actual)

    def test_missing_inventory_entry_fails(self):
        self.files.pop('tools/input/SDL2.dll')
        self.save_package()
        for actual in (None, self.files):
            with self.subTest(mode=actual is None), self.assertRaisesRegex(ValueError, 'missing:'):
                verify_runtime_seed(self.root, actual)

    def test_missing_physical_file_fails(self):
        (self.root / 'runtime/python.exe').rename(self.root / 'runtime/python-renamed.exe')
        with self.assertRaisesRegex(ValueError, 'file missing'):
            verify_runtime_seed(self.root, self.files)

    def test_new_media_and_legacy_executables_are_excluded_but_not_their_neighbors(self):
        for name in ('runtime/Lib/think_aloud_media/ffmpeg.exe',
                     'runtime/Lib/think_aloud_media/provenance.json',
                     'runtime/Lib/site-packages/imageio_ffmpeg/binaries/legacy.EXE'):
            self.files[name] = self.write(name, b'separately verified or omitted')
            self.assertFalse(seed_managed_path(name))
        self.save_package()
        self.assertEqual(verify_runtime_seed(self.root, self.files)['files'], 4)
        self.assertEqual(verify_runtime_seed(self.root)['files'], 4)
        for name in ('runtime/Lib/think_aloud_media_unreviewed/x.py',
                     'runtime/Lib/site-packages/imageio_ffmpeg/binaries/README.md'):
            self.assertTrue(seed_managed_path(name))

    def test_unsafe_paths_rejected_in_lock_and_package_inventory(self):
        original = dict(self.lock['files'][0])
        for name in ('../escape', 'runtime/../escape', 'runtime//x', 'C:/runtime/x',
                     'runtime\\x', 'runtime/x.', 'runtime/CON', '/runtime/x'):
            with self.subTest(path=name):
                self.lock['files'][0] = dict(original, path=name)
                self.save_lock()
                with self.assertRaisesRegex(ValueError, 'Unsafe runtime seed path'):
                    verify_runtime_seed(self.root, self.files)
                self.lock['files'][0] = original
                self.save_lock()
                self.save_package([dict(original, path=name)])
                with self.assertRaisesRegex(ValueError, 'Unsafe runtime seed path'):
                    verify_runtime_seed(self.root)

    def test_mapping_cannot_substitute_a_different_or_outside_file(self):
        name = 'runtime/python.exe'
        for path in (self.write('runtime/copy.exe', self.files[name].read_bytes()),
                     self.root.parent / 'outside.exe'):
            path.write_bytes(self.files[name].read_bytes())
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'escapes or differs'):
                verify_runtime_seed(self.root, dict(self.files, **{name: path}))

    def test_case_alias_and_duplicate_records_rejected(self):
        original = self.lock['files'][0]
        for name in (original['path'], original['path'].upper()):
            with self.subTest(path=name):
                self.lock['files'].append(dict(original, path=name))
                self.save_lock()
                with self.assertRaisesRegex(ValueError, 'Duplicate or invalid'):
                    verify_runtime_seed(self.root)
                self.lock['files'].pop()
        self.save_lock()
        duplicate = dict(self.files, **{'RUNTIME/PYTHON.EXE': self.files['runtime/python.exe']})
        with self.assertRaisesRegex(ValueError, 'Duplicate runtime seed file path'):
            verify_runtime_seed(self.root, duplicate)
        self.save_package(self.lock['files'] + [original])
        with self.assertRaisesRegex(ValueError, 'Duplicate or invalid'):
            verify_runtime_seed(self.root)

    def test_invalid_size_hash_schema_and_baseline_fail(self):
        original = json.loads(json.dumps(self.lock))
        mutations = [lambda v: v.update(schema=True),
                     lambda v: v.update(files=[]),
                     lambda v: v['files'][0].update(bytes=True),
                     lambda v: v['files'][0].update(bytes=-1),
                     lambda v: v['files'][0].update(sha256='F' * 64),
                     lambda v: v['files'][0].update(sha256='bad'),
                     lambda v: v['baseline'].update(package_manifest_sha256='bad'),
                     lambda v: v['baseline'].update(version=None),
                     lambda v: v['files'][0].update(path='app.py')]
        for mutate in mutations:
            self.lock = json.loads(json.dumps(original))
            mutate(self.lock)
            self.save_lock()
            with self.assertRaises(ValueError):
                verify_runtime_seed(self.root, self.files)

    def test_duplicate_json_key_is_not_silently_overwritten(self):
        raw = json.dumps(self.lock).replace('"schema": 1', '"schema": 2, "schema": 1')
        self.write('scripts/runtime-seed.json', raw.encode())
        with self.assertRaisesRegex(ValueError, 'Duplicate runtime seed JSON key'):
            verify_runtime_seed(self.root, self.files)

    def test_seed_lock_symlink_is_rejected(self):
        lock = self.root / 'scripts/runtime-seed.json'
        target = self.root / 'scripts/original.json'
        lock.rename(target)
        try:
            lock.symlink_to(target)
        except OSError as error:
            self.skipTest('OS does not permit creating symlinks: ' + str(error))
        with self.assertRaisesRegex(ValueError, 'link or reparse point'):
            verify_runtime_seed(self.root, self.files)


if __name__ == '__main__':
    unittest.main()
