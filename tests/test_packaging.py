import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import tarfile
import unittest
from unittest.mock import patch
import zipfile

from scripts.build_portable import (ROOT_FILES, build, collect_files,
                                    launcher_bytes, read_sources, sha256)
from scripts.fetch_runtime import extract_webview_notices, supplement
from scripts.verify_runtime_seed import seed_managed_path


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'fixture'
        for path in ROOT_FILES:
            self.write(path, b'fixture source\n')
        for path in ('ui/index.html', 'ui/app.js', 'ui/review.js', 'ui/review.css',
                     'ui/vendor/plyr/plyr.min.js', 'ui/vendor/plyr/plyr.css', 'ui/vendor/plyr/plyr.svg', 'licenses/Plyr-MIT.txt', 'licenses/Python.txt',
                     'runtime/python.exe', 'runtime/pythonw.exe', 'runtime/python312._pth',
                     'runtime/Lib/site-packages/fixture-1.dist-info/licenses/LICENSE',
                     'runtime/Lib/site-packages/fixture-1.dist-info/METADATA',
                     'runtime/Lib/site-packages/fixture/config.json',
                     'tools/obs/bin/64bit/obs64.exe', 'tools/obs/data/locale/en-US.ini',
                     'tools/obs/portable_mode.txt', 'tools/input/SDL2.dll',
                     'tools/input/provenance.json', 'licenses/SDL2-zlib.txt'):
            self.write(path, b'fixture dependency\n')
        self.sources = self.root / 'build/dependency-sources'
        self.sources.mkdir(parents=True)
        source = self.sources / 'fixture-sources.tar.gz'
        source.write_bytes(b'synthetic source archive, not a real release')
        self.source_manifest = {'schema': 1, 'redistribution_ready': False,
            'gaps': ['synthetic incomplete source fixture'], 'files': [
                {'component': 'SDL2', 'filename': source.name, 'bytes': source.stat().st_size, 'sha256': sha256(source)}]}
        self.write('tools/input/provenance.json', json.dumps({'version': 'synthetic',
            'dll_sha256': sha256(self.root / 'tools/input/SDL2.dll'),
            'assets': [{'name': source.name, 'sha256': sha256(source)}]}).encode())
        binary = self.write('runtime/Lib/think_aloud_media/ffmpeg.exe', b'MZ synthetic CLI')
        media = self.write('runtime/Lib/think_aloud_media/provenance.json', json.dumps({
            'schema': 1, 'version': 'synthetic', 'executable': 'ffmpeg.exe', 'files': [
                {'filename': 'ffmpeg.exe', 'bytes': binary.stat().st_size, 'sha256': sha256(binary)}]}).encode())
        self.source_manifest['provenance'] = {'media_runtime_manifest_sha256': sha256(media)}
        seed = [{'path': name, 'bytes': file.stat().st_size, 'sha256': sha256(file)}
                for name, file in collect_files(self.root).items() if seed_managed_path(name)]
        self.write('scripts/runtime-seed.json', json.dumps({'schema': 1,
            'baseline': {'version': 'synthetic', 'package_manifest_sha256': 'a' * 64},
            'files': seed}).encode())
        self.save_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(data)
        return file

    def save_manifest(self):
        (self.sources / 'source-manifest.json').write_text(json.dumps(self.source_manifest), encoding='utf-8')

    def make(self, directory='out', candidate=True):
        return build(self.root, self.base / directory, candidate=candidate,
                     launcher=b'MZ synthetic launcher fixture')

    def test_excludes_credentials_models_obs_config_vault_caches_and_obsidian(self):
        contaminants = (
            'config.json', 'portable.json', '.env', 'secret.dpapi', 'state/models.json',
            'state/cloud-task.json', 'models/large-v3/model.bin', 'recordings/recording.mkv',
            'vault/secret.md', '体验资料库/secret.md', 'logs/app.log', 'custom-hotwords.txt',
            'vocabularies/personal.txt', 'vocabularies/personal.scel',
            'vocabularies/user/uiux-terms.txt', 'vocabularies/user/private.txt',
            'tools/obs/config/obs-studio/global.ini', 'tools/obs/config/obs-studio/basic/profiles/x/service.json',
            'tools/obs/bin/64bit/logs/secret.txt', 'tools/obs/bin/64bit/.env',
            'tools/obs/bin/64bit/crashes/dump.dmp', 'tools/obsidian/Obsidian.exe',
            'runtime/Lib/__pycache__/thing.pyc', 'runtime/Lib/site-packages/pip-cache/private.txt',
            'runtime/Lib/site-packages/example-1.dist-info/direct_url.json',
            'runtime/Scripts/pip.exe', 'runtime/private.txt', 'ui/config.json',
            'vault-template/.obsidian/plugins/media-transcript/private-note.md',
            'vault-template/private.md')
        for path in contaminants:
            self.write(path, b'PRIVATE_SENTINEL_12ab')
        result = self.make()
        with zipfile.ZipFile(self.base / 'out' / result[1]['filename']) as archive:
            names = set(archive.namelist())
            for path in contaminants:
                if path == 'portable.json':
                    self.assertNotIn(b'PRIVATE_SENTINEL', archive.read(path))
                else:
                    self.assertNotIn(path, names)
            for name in names:
                self.assertNotIn(b'PRIVATE_SENTINEL', archive.read(name), name)
            self.assertIn('runtime/Lib/site-packages/fixture-1.dist-info/licenses/LICENSE', names)
            self.assertIn('runtime/Lib/site-packages/fixture/config.json', names)
            self.assertEqual(json.loads(archive.read('portable.json'))['models'], 'optional')

    def test_only_fixed_bundled_vocabulary_is_packaged_with_exact_bytes(self):
        bundled = '用户体验\nUX\n交互设计\n'.encode('utf-8')
        self.write('vocabularies/uiux-terms.txt', bundled)
        self.write('vocabularies/personal.txt', b'private personal words')
        self.write('vocabularies/user/uiux-terms.txt', b'private nested words')
        result = self.make()
        with zipfile.ZipFile(self.base / 'out' / result[1]['filename']) as archive:
            vocabulary_names = [name for name in archive.namelist() if name.startswith('vocabularies/')]
            self.assertEqual(vocabulary_names, ['vocabularies/uiux-terms.txt'])
            self.assertEqual(archive.read(vocabulary_names[0]), bundled)

    def test_missing_bundled_vocabulary_fails_before_build_output(self):
        (self.root / 'vocabularies/uiux-terms.txt').rename(self.root / 'vocabularies/renamed.txt')
        with self.assertRaisesRegex(ValueError, 'Missing package input: vocabularies/uiux-terms.txt'):
            self.make()
        self.assertFalse((self.base / 'out').exists())

    def test_same_inputs_create_identical_archives(self):
        first = self.make('one')
        second = self.make('two')
        self.assertEqual(first, second)
        for item in first:
            self.assertEqual((self.base / 'one' / item['filename']).read_bytes(),
                             (self.base / 'two' / item['filename']).read_bytes())

    def test_legacy_ffmpeg_binary_never_ships(self):
        legacy = 'runtime/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
        self.write(legacy, b'MZ legacy CLI must not ship')
        results = self.make()
        with zipfile.ZipFile(self.base / 'out' / results[1]['filename']) as archive:
            self.assertNotIn(legacy, archive.namelist())
            self.assertIn('runtime/Lib/think_aloud_media/ffmpeg.exe', archive.namelist())

    def test_media_runtime_must_match_bound_inventory(self):
        self.write('runtime/Lib/think_aloud_media/ffmpeg.exe', b'changed')
        with self.assertRaisesRegex(ValueError, 'Media runtime mismatch'):
            self.make()
        self.assertFalse((self.base / 'out').exists())

    def test_media_inventory_is_bound_to_source_manifest(self):
        self.source_manifest['provenance']['media_runtime_manifest_sha256'] = '0' * 64
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'dependency-source provenance'):
            self.make()

    def test_modified_prepared_python_dependency_cannot_be_repackaged(self):
        self.write('runtime/Lib/site-packages/fixture/config.json', b'changed seed')
        with self.assertRaisesRegex(ValueError, 'Runtime seed content mismatch'):
            self.make()

    def test_package_version_uses_the_update_protocol_semver(self):
        for version in ('01.0.0', '1.0.0-01', '1.0.0-a..b', '1.0.0-', 'v1.0.0'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                build(self.root, self.base / 'invalid-version', candidate=True,
                      version=version, launcher=b'MZ synthetic launcher fixture')
        self.assertFalse((self.base / 'invalid-version').exists())
        results = build(self.root, self.base / 'valid-version', candidate=True,
                        version='1.0.0-RC.1+build.2', launcher=b'MZ synthetic launcher fixture')
        with zipfile.ZipFile(self.base / 'valid-version' / results[1]['filename']) as archive:
            self.assertEqual(json.loads(archive.read('portable.json'))['version'], '1.0.0-RC.1+build.2')

    def test_existing_checksum_prevents_partial_release_set(self):
        output = self.base / 'existing-sums'
        output.mkdir()
        sums = output / 'ExperienceRecorder-0.3.0-windows-x64-candidate-SHA256SUMS.txt'
        sums.write_bytes(b'previous release evidence')
        with self.assertRaises(FileExistsError):
            self.make('existing-sums')
        self.assertEqual(list(output.iterdir()), [sums])
        self.assertEqual(sums.read_bytes(), b'previous release evidence')

    def test_inventory_matches_every_shipped_byte(self):
        result = self.make()
        with zipfile.ZipFile(self.base / 'out' / result[1]['filename']) as archive:
            manifest = json.loads(archive.read('package-manifest.json'))
            self.assertEqual(set(archive.namelist()) - {'package-manifest.json'},
                             {item['path'] for item in manifest['files']})
            for item in manifest['files']:
                data = archive.read(item['path'])
                self.assertEqual(len(data), item['bytes'])
                self.assertEqual(hashlib.sha256(data).hexdigest(), item['sha256'])
            self.assertFalse(manifest['dependency_source_status'])
            metadata=json.loads(archive.read('portable.json'))
            self.assertEqual(metadata['update_protocol'],1)
            self.assertEqual(metadata['update_repository'],'Elkhiffa/think-aloud-recorder')
            for name in ('updater.py','update_installer.py','docs/updates.md'):
                self.assertIn(name,archive.namelist())

    def test_generated_ffmpeg_license_supersedes_seed_once(self):
        self.write('licenses/FFmpeg-GPL-3.0.txt', b'previous seed notice')
        source = self.sources / 'synthetic-ffmpeg.tar.gz'
        content = b'synthetic pinned license fixture'
        with tarfile.open(source, 'w:gz') as archive:
            item = tarfile.TarInfo('ffmpeg/COPYING.GPLv3')
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
        self.source_manifest['files'].append({'component': 'FFmpeg core',
            'filename': source.name, 'bytes': source.stat().st_size, 'sha256': sha256(source)})
        self.save_manifest()
        result = self.make()
        with zipfile.ZipFile(self.base / 'out' / result[1]['filename']) as archive:
            records = json.loads(archive.read('package-manifest.json'))['files']
            names = [r['path'].casefold() for r in records]
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(archive.read('licenses/FFmpeg-GPL-3.0.txt'), content)

    def test_public_build_rejects_known_source_gap_before_output(self):
        with self.assertRaisesRegex(ValueError, 'source review is incomplete'):
            self.make(candidate=False)
        self.assertFalse((self.base / 'out').exists())

    def test_reviewed_source_manifest_can_build_public_name(self):
        # Synthetic protocol fixture only, not evidence of real release approval.
        self.source_manifest.update(redistribution_ready=True, gaps=[])
        self.save_manifest()
        results = self.make(candidate=False)
        self.assertNotIn('candidate', results[1]['filename'])

    def test_modified_source_archive_rejected(self):
        (self.sources / 'fixture-sources.tar.gz').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'source mismatch'):
            self.make()

    def test_controller_runtime_and_corresponding_source_must_match(self):
        self.write('tools/input/SDL2.dll', b'changed runtime')
        with self.assertRaisesRegex(ValueError, 'SDL2 differs'):
            self.make()
        self.write('tools/input/SDL2.dll', b'fixture dependency\n')
        self.source_manifest['files'][0]['component'] = 'unrelated'
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'Matching SDL2 source'):
            self.make()

    def test_source_path_traversal_rejected(self):
        self.source_manifest['files'][0]['filename'] = '../secret'
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, 'source filename'):
            read_sources(self.sources, True)

    def test_unlisted_source_directory_files_not_archived(self):
        (self.sources / 'private-token.txt').write_text('secret')
        results = self.make()
        with zipfile.ZipFile(self.base / 'out' / results[0]['filename']) as archive:
            self.assertNotIn('private-token.txt', archive.namelist())
            self.assertIn('fixture-sources.tar.gz', archive.namelist())

    def test_required_runtime_missing_fails(self):
        (self.root / 'runtime/pythonw.exe').unlink()
        with self.assertRaisesRegex(ValueError, 'Required runtime'):
            self.make()

    def test_output_never_overwrites_existing_archive(self):
        results = self.make()
        prior = (self.base / 'out' / results[0]['filename']).read_bytes()
        with self.assertRaises(FileExistsError):
            self.make()
        self.assertEqual((self.base / 'out' / results[0]['filename']).read_bytes(), prior)

    def test_symlink_cannot_pull_external_file_into_allowlist(self):
        external = self.base / 'external.py'
        external.write_text('private')
        file = self.root / 'app.py'
        file.unlink()
        try:
            file.symlink_to(external)
        except OSError:
            self.skipTest('OS has not granted symlink creation')
        with self.assertRaisesRegex(ValueError, 'escape'):
            collect_files(self.root)

    @unittest.skipUnless(os.name == 'nt', 'Windows native launcher resource')
    def test_native_launcher_is_deterministic_and_relative(self):
        one = launcher_bytes()
        self.assertEqual(one, launcher_bytes())
        self.assertTrue(one.startswith(b'MZ'))
        self.assertIn(b'#!<launcher_dir>\\runtime\\pythonw.exe\n', one)
        with zipfile.ZipFile(io.BytesIO(one)) as archive:
            self.assertIn(b'from portable_entry import main', archive.read('__main__.py'))
            self.assertEqual(archive.getinfo('__main__.py').date_time, (1980, 1, 1, 0, 0, 0))

    def test_webview_notices_come_from_matching_package_bytes(self):
        self.write('runtime/Lib/site-packages/webview/lib/Microsoft.Web.WebView2.Core.dll', b'fixture dll')
        package = self.base / 'sdk.nupkg'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('lib/net462/Microsoft.Web.WebView2.Core.dll', b'fixture dll')
            archive.writestr('LICENSE.txt', b'exact upstream license\r\n')
            archive.writestr('NOTICE.txt', b'exact upstream notices\r\n')
        result = extract_webview_notices(package, self.root)
        self.assertEqual(result['Microsoft-WebView2-SDK-LICENSE.txt'], b'exact upstream license\r\n')
        self.assertEqual(result['Microsoft-WebView2-SDK-NOTICE.txt'], b'exact upstream notices\r\n')
        matches = json.loads(result['webview2-binary-match.json'])
        self.assertEqual(matches[0]['official_package_members'], ['lib/net462/Microsoft.Web.WebView2.Core.dll'])
        self.assertNotIn(str(self.root), result['webview2-binary-match.json'].decode())

    def test_mismatched_sdk_does_not_establish_notice_provenance(self):
        self.write('runtime/Lib/site-packages/webview/lib/Microsoft.Web.WebView2.Core.dll', b'changed local dll')
        package = self.base / 'sdk.nupkg'
        with zipfile.ZipFile(package, 'w') as archive:
            archive.writestr('lib/net462/Microsoft.Web.WebView2.Core.dll', b'upstream dll')
            archive.writestr('LICENSE.txt', b'license')
            archive.writestr('NOTICE.txt', b'notice')
        with self.assertRaisesRegex(ValueError, 'differs from the official SDK'):
            extract_webview_notices(package, self.root)

    def test_supplement_never_overwrites_previous_manifest(self):
        before = (self.sources / 'source-manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):
            supplement(self.root, self.sources, self.sources)
        self.assertEqual((self.sources / 'source-manifest.json').read_bytes(), before)

    def test_microsoft_supplement_keeps_unresolved_component_reviews(self):
        self.source_manifest['gaps'] = ['Synthetic OBS dependency review remains open']
        self.save_manifest()
        before = (self.sources / 'source-manifest.json').read_bytes()
        with patch('scripts.fetch_runtime.download_definition'), patch(
                'scripts.fetch_runtime.extract_webview_notices', return_value={}):
            result = supplement(self.root, self.sources, self.base / 'successor')
        self.assertIn('Synthetic OBS dependency review remains open', result['gaps'])
        self.assertTrue(any('native-wheel' in gap for gap in result['gaps']))
        self.assertFalse(result['redistribution_ready'])
        self.assertEqual((self.sources / 'source-manifest.json').read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
