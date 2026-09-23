"""Synthetic, offline release-protocol checks; never evidence of runtime readiness."""
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import prepare_release as release


def digest(value):
    return hashlib.sha256(value).hexdigest()


class ReleasePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.shared.name).resolve() / 'synthetic-repository'
        cls.repo.mkdir()
        cls.code = {name: ('# synthetic source for ' + name + '\n').encode()
                    for name in release.KEY_APPLICATION_FILES}
        raw = b'MZ synthetic interpreter'
        cls.code['scripts/runtime-seed.json'] = release.json_bytes({'schema': 1,
            'baseline': {'version': 'synthetic', 'package_manifest_sha256': 'a' * 64},
            'files': [{'path': name, 'bytes': len(raw), 'sha256': digest(raw)}
                      for name in ('runtime/python.exe', 'runtime/pythonw.exe')]})
        cls.code['portable.json'] = release.json_bytes({'version': '0.2.0', 'models': 'optional'})
        for name, raw in cls.code.items():
            path = cls.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        def git(*args):
            result = subprocess.run(['git', '-C', str(cls.repo), *args], capture_output=True, check=True)
            return result.stdout.decode().strip()
        git('init', '--initial-branch=release-fixture')
        git('add', '.')
        git('-c', 'user.name=Protocol Fixture', '-c', 'user.email=fixture@example.invalid',
            '-c', 'commit.gpgsign=false', 'commit', '-m', 'Synthetic test fixture only')
        cls.commit = git('rev-parse', 'HEAD')

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.artifacts = self.base / 'artifacts'
        self.artifacts.mkdir()
        self.notes = self.base / 'notes.md'
        self.notes.write_text('# Synthetic release fixture\n\nNo runtime acceptance is claimed.\n', encoding='utf-8')
        self.out = self.base / 'new-preflight'
        self.source_data = b'Synthetic dependency source, not actual corresponding source.'
        self.source_manifest = {'schema': 1, 'redistribution_ready': True, 'gaps': [],
                                'files': [{'filename': 'fixture-source.tar.gz', 'bytes': len(self.source_data),
                                           'sha256': digest(self.source_data), 'component': 'Synthetic fixture'}]}
        self.media_manifest = {'schema': 1, 'version': 'synthetic', 'executable': 'ffmpeg.exe',
            'files': [{'filename': 'ffmpeg.exe', 'bytes': len(b'MZ synthetic media'),
                       'sha256': digest(b'MZ synthetic media')}]}
        self.media_json = release.json_bytes(self.media_manifest)
        self.source_manifest['provenance'] = {'media_runtime_manifest_sha256': digest(self.media_json)}
        self.version = '1.2.3'
        self.names = release.public_names(self.version)

    def write_zip(self, path, values):
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, value in values.items():
                archive.writestr(name, value)

    def sums(self):
        (self.artifacts / self.names[2]).write_text(''.join(
            release.sha256(self.artifacts / name) + '  ' + name + '\n'
            for name in self.names[:2]), encoding='utf-8')

    def make(self, *, version='1.2.3', candidate=False, portable=None,
             package_sources=None, source_manifest=None, source_values=None, code=None):
        self.version = version
        self.names = release.candidate_names(version) if candidate else release.public_names(version)
        metadata = {'version': version, 'platform': 'windows-x64',
                    'update_protocol': 1, 'update_repository': release.REPOSITORY,
                    'release_status': 'candidate-not-for-public-redistribution' if candidate else 'public'}
        metadata.update(portable or {})
        manifest = source_manifest if source_manifest is not None else self.source_manifest
        values = {'source-manifest.json': release.json_bytes(manifest), 'fixture-source.tar.gz': self.source_data}
        values.update(source_values or {})
        self.write_zip(self.artifacts / self.names[1], values)
        package = {**self.code, 'ExperienceRecorder.exe': b'MZ synthetic launcher',
                   'runtime/python.exe': b'MZ synthetic interpreter',
                   'runtime/pythonw.exe': b'MZ synthetic interpreter',
                   'runtime/Lib/think_aloud_media/ffmpeg.exe': b'MZ synthetic media',
                   'runtime/Lib/think_aloud_media/provenance.json': self.media_json,
                   'portable.json': release.json_bytes(metadata),
                   'dependency-source-manifest.json': release.json_bytes(
                       package_sources if package_sources is not None else manifest)}
        package.update(code or {})
        self.write_package(package, candidate=candidate)
        self.sums()

    def write_package(self, package, *, candidate=False):
        package = {key: value for key, value in package.items() if key != 'package-manifest.json'}
        package['package-manifest.json'] = release.json_bytes(
            {'schema': 1, 'dependency_source_status': not candidate,
             'files': [{'path': name, 'bytes': len(raw), 'sha256': digest(raw)}
                       for name, raw in package.items()]})
        self.write_zip(self.artifacts / self.names[0], package)

    def run_preflight(self, **changes):
        args = dict(tag='v' + self.version, commit=self.commit, artifacts=self.artifacts,
                    notes=self.notes, outdir=self.out, repo_root=self.repo)
        args.update(changes)
        return release.prepare_release(**args)

    def assert_blocked(self, report, check=None):
        self.assertEqual(report['status'], 'blocked')
        self.assertTrue((self.out / 'release-preflight.json').is_file())
        self.assertTrue((self.out / 'release-preflight.md').is_file())
        self.assertTrue((self.out / 'release-notes-draft.md').is_file())
        self.assertFalse((self.out / 'release-draft.json').exists())
        self.assertFalse((self.out / 'release-upload-manifest.json').exists())
        if check:
            self.assertIn(check, [item['check'] for item in report['blockers']])

    def test_synthetic_public_fixture_prepares_valid_draft_without_runtime_claim(self):
        self.make()
        with patch.object(release, 'extract_package', wraps=release.extract_package) as extractor:
            report = self.run_preflight()
        self.assertEqual(report['status'], 'ready_for_draft_review', report['blockers'])
        extractor.assert_called_once_with(self.artifacts / self.names[0], self.out / 'validated-package',
                                          expected_version='1.2.3', allow_candidate=False)
        request = json.loads((self.out / 'release-draft.json').read_bytes())
        self.assertEqual(set(request), {'tag_name', 'target_commitish', 'name', 'body', 'draft', 'prerelease'})
        self.assertTrue(request['draft'])
        self.assertFalse(request['prerelease'])
        self.assertEqual(request['target_commitish'], self.commit)
        self.assertEqual(request['body'], self.notes.read_bytes().decode('utf-8-sig'))
        self.assertEqual((self.out / 'release-notes-draft.md').read_bytes(), self.notes.read_bytes())
        uploads = json.loads((self.out / 'release-upload-manifest.json').read_bytes())
        self.assertEqual({item['name'] for item in uploads['assets']}, set(self.names))
        self.assertFalse(uploads['upload_performed'])
        self.assertEqual(report['runtime_evidence'], {'status': 'pending', 'verified': False})
        self.assertTrue(report['pending'])
        self.assertEqual(len(report['commit_binding']['files']), len(release.KEY_APPLICATION_FILES))

    def test_preview_flag_is_derived_from_the_explicit_tag(self):
        self.make(version='1.2.3-preview.4')
        report = self.run_preflight()
        self.assertEqual(report['status'], 'ready_for_draft_review')
        self.assertTrue(json.loads((self.out / 'release-draft.json').read_bytes())['prerelease'])

    def test_missing_assets_report_expected_names_and_exit_nonzero(self):
        with patch.object(release, 'REPO_ROOT', self.repo), patch('sys.stdout', new_callable=io.StringIO):
            code = release.main(['--tag', 'v1.2.3', '--commit', self.commit,
                                 '--artifacts', str(self.artifacts), '--notes', str(self.notes), '--outdir', str(self.out)])
        self.assertEqual(code, 1)
        report = json.loads((self.out / 'release-preflight.json').read_bytes())
        self.assert_blocked(report, 'exact_public_assets')
        self.assertEqual(report['required_assets'], list(self.names))

    def test_candidate_names_are_preserved_and_real_source_gaps_reported(self):
        self.source_manifest.update(redistribution_ready=False, gaps=['FFmpeg corresponding sources incomplete'])
        self.make(candidate=True)
        before = {path.name: path.read_bytes() for path in self.artifacts.iterdir()}
        report = self.run_preflight()
        self.assert_blocked(report, 'exact_public_assets')
        self.assertEqual(set(report['candidate_counterparts']), set(self.names))
        self.assertEqual(report['source_gaps'][0]['gaps'], self.source_manifest['gaps'])
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.artifacts.iterdir()})

    def test_candidate_metadata_cannot_be_admitted_using_public_filenames(self):
        self.make(portable={'release_status': 'candidate-not-for-public-redistribution'})
        self.assert_blocked(self.run_preflight(), 'production_public_package_validation')

    def test_public_filenames_do_not_bypass_source_gate(self):
        self.source_manifest.update(redistribution_ready=False, gaps=['Known source gap'])
        self.make()
        self.assert_blocked(self.run_preflight(), 'public_source_gate_source-manifest.json')

    def test_source_gaps_must_be_explicitly_empty(self):
        self.source_manifest.pop('gaps')
        self.make()
        self.assert_blocked(self.run_preflight(), 'public_source_gate_source-manifest.json')

    def test_duplicate_checksum_is_rejected_even_when_values_match(self):
        self.make()
        path = self.artifacts / self.names[2]
        path.write_text(path.read_text() + path.read_text().splitlines()[0] + '\n')
        self.assert_blocked(self.run_preflight(), 'release_checksums')

    def test_missing_source_checksum_is_rejected(self):
        self.make()
        path = self.artifacts / self.names[2]
        path.write_text(path.read_text().splitlines()[0] + '\n')
        self.assert_blocked(self.run_preflight(), 'release_checksums')

    def test_corrupted_archive_bytes_fail_checksum(self):
        self.make()
        path = self.artifacts / self.names[1]
        path.write_bytes(path.read_bytes() + b'changed after checksum')
        self.assert_blocked(self.run_preflight(), 'release_checksums')

    def test_corrupt_zip_with_fresh_checksum_is_rejected(self):
        self.make()
        (self.artifacts / self.names[0]).write_bytes(b'not a ZIP')
        self.sums()
        self.assert_blocked(self.run_preflight(), 'production_public_package_validation')

    def test_source_manifest_semantic_mismatch_is_rejected(self):
        different = copy.deepcopy(self.source_manifest)
        different['review_note'] = 'different declaration'
        self.make(package_sources=different)
        self.assert_blocked(self.run_preflight(), 'matching_public_source_manifests')

    def test_non_entrypoint_application_module_must_match_commit(self):
        self.make(code={'secret_store.py': b'# changed credential implementation\n'})
        self.assert_blocked(self.run_preflight(), 'key_application_commit_binding')

    def test_extra_executable_source_absent_from_commit_is_rejected(self):
        self.make(code={'ui/extra.js': b'window.unreviewed = true;\n'})
        self.assert_blocked(self.run_preflight(), 'key_application_commit_binding')

    def test_modified_runtime_fails_even_with_self_consistent_zip_inventory(self):
        self.make(code={'runtime/python.exe': b'MZ modified Python interpreter'})
        self.assert_blocked(self.run_preflight(), 'accepted_runtime_seed_binding')

    def test_modified_media_binary_fails_even_with_self_consistent_zip(self):
        self.make(code={'runtime/Lib/think_aloud_media/ffmpeg.exe': b'changed media'})
        self.assert_blocked(self.run_preflight(), 'media_runtime_source_binding')

    def test_media_and_inventory_tamper_cannot_override_source_binding(self):
        raw = b'changed media'
        modified = copy.deepcopy(self.media_manifest)
        modified['files'][0].update(bytes=len(raw), sha256=digest(raw))
        self.make(code={'runtime/Lib/think_aloud_media/ffmpeg.exe': raw,
                        'runtime/Lib/think_aloud_media/provenance.json': release.json_bytes(modified)})
        self.assert_blocked(self.run_preflight(), 'media_runtime_source_binding')

    def test_non_object_packaged_source_manifest_still_writes_blocked_report(self):
        self.make(package_sources=[])
        self.assert_blocked(self.run_preflight(), 'media_runtime_source_binding')

    def test_invalid_packaged_source_json_still_writes_blocked_report(self):
        self.make(code={'dependency-source-manifest.json': b'{invalid json'})
        self.assert_blocked(self.run_preflight(), 'media_runtime_source_binding')

    def test_non_object_media_manifest_still_writes_blocked_report(self):
        self.make(code={'runtime/Lib/think_aloud_media/provenance.json': b'[]'})
        self.assert_blocked(self.run_preflight(), 'media_runtime_source_binding')

    def test_extensionless_license_can_have_windows_line_endings(self):
        self.make(code={'LICENSE': self.code['LICENSE'].replace(b'\n', b'\r\n')})
        report = self.run_preflight()
        self.assertEqual(report['status'], 'ready_for_draft_review', report['blockers'])
        item = next(r for r in report['commit_binding']['files'] if r['path'] == 'LICENSE')
        self.assertEqual(item['comparison'], 'crlf_normalized_text')

    def test_source_manifest_formatting_does_not_change_semantic_equality(self):
        self.make(source_values={'source-manifest.json': json.dumps(self.source_manifest, separators=(',', ':')).encode()})
        self.assertEqual(self.run_preflight()['status'], 'ready_for_draft_review')

    def test_listed_source_digest_and_size_are_both_checked(self):
        for change in ('digest', 'size'):
            with self.subTest(change=change):
                manifest = copy.deepcopy(self.source_manifest)
                if change == 'digest':
                    manifest['files'][0]['sha256'] = '0' * 64
                else:
                    manifest['files'][0]['bytes'] += 1
                self.make(source_manifest=manifest)
                self.out = self.base / ('blocked-' + change)
                self.assert_blocked(self.run_preflight(), 'dependency_source_integrity')

    def test_source_archive_traversal_case_alias_and_symlink_are_blocked(self):
        for attack in ('../outside', 'FIXTURE-source.tar.gz', 'symlink'):
            with self.subTest(attack=attack):
                self.make()
                with zipfile.ZipFile(self.artifacts / self.names[1], 'a') as archive:
                    if attack == 'symlink':
                        info = zipfile.ZipInfo('link')
                        info.create_system = 3
                        info.external_attr = 0o120777 << 16
                        archive.writestr(info, b'../outside')
                    else:
                        archive.writestr(attack, b'invalid')
                self.sums()
                self.out = self.base / ('blocked-' + attack.replace('/', '').replace('.', ''))
                self.assert_blocked(self.run_preflight(), 'dependency_source_integrity')
                self.assertFalse((self.base / 'outside').exists())

    def test_duplicate_source_entry_is_rejected(self):
        self.make()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.artifacts / self.names[1], 'a') as archive:
                archive.writestr('fixture-source.tar.gz', self.source_data)
        self.sums()
        self.assert_blocked(self.run_preflight(), 'dependency_source_integrity')

    def test_source_expansion_limit_is_enforced(self):
        self.make()
        with patch.object(release, 'MAX_EXPANDED', 1):
            self.assert_blocked(self.run_preflight(), 'dependency_source_integrity')

    def test_source_json_duplicate_keys_and_nonfinite_values_are_rejected(self):
        for raw in (b'{"schema":1,"schema":1}', b'{"schema":1,"gaps":NaN}'):
            with self.subTest(raw=raw):
                self.make(source_values={'source-manifest.json': raw})
                self.out = self.base / ('bad-json-' + digest(raw)[:8])
                self.assert_blocked(self.run_preflight(), 'source_declaration_source-manifest.json')

    def test_invalid_tags_generate_blocked_reports_without_drafts(self):
        for tag in ('1.2.3', 'v01.2.3', 'v1.2.3-rc.1', 'v1.2.3-preview.01', 'v1.2.3+build', 'v1.2.3-candidate'):
            with self.subTest(tag=tag):
                self.out = self.base / ('bad-tag-' + digest(tag.encode())[:8])
                self.assert_blocked(self.run_preflight(tag=tag), 'tag')

    def test_short_and_missing_local_commit_are_rejected(self):
        for commit in (self.commit[:8], '0' * 40):
            with self.subTest(commit=commit):
                self.out = self.base / ('bad-commit-' + commit[:8])
                self.assert_blocked(self.run_preflight(commit=commit), 'local_target_commit')

    def test_application_source_must_match_the_target_commit(self):
        self.make(code={'app.py': b'# different application source\n'})
        self.assert_blocked(self.run_preflight(), 'key_application_commit_binding')

    def test_windows_line_ending_comparison_is_explicitly_reported(self):
        self.make(code={'app.py': self.code['app.py'].replace(b'\n', b'\r\n')})
        report = self.run_preflight()
        self.assertEqual(report['status'], 'ready_for_draft_review')
        item = next(item for item in report['commit_binding']['files'] if item['path'] == 'app.py')
        self.assertEqual(item['comparison'], 'crlf_normalized_text')
        self.assertNotEqual(item['package_sha256'], item['commit_blob_sha256'])

    def test_package_protocol_and_repository_are_explicit_requirements(self):
        for metadata in ({'update_repository': 'other/repo'}, {'update_protocol': None}, {'update_protocol': True}):
            with self.subTest(metadata=metadata):
                self.make(portable=metadata)
                self.out = self.base / ('bad-metadata-' + digest(json.dumps(metadata).encode())[:8])
                self.assert_blocked(self.run_preflight())

    def test_package_version_must_exactly_match_tag(self):
        self.make(portable={'version': '1.2.4'})
        self.assert_blocked(self.run_preflight(), 'production_public_package_validation')

    def test_existing_output_is_never_overwritten(self):
        self.out.mkdir()
        saved = self.out / 'release-preflight.json'
        saved.write_bytes(b'historical blocked evidence')
        with self.assertRaises(FileExistsError):
            self.run_preflight()
        self.assertEqual(saved.read_bytes(), b'historical blocked evidence')
        self.assertEqual(list(self.out.iterdir()), [saved])

    def test_output_cannot_overlap_input_directory(self):
        target = self.artifacts / 'preflight'
        with self.assertRaisesRegex(ValueError, 'overlaps'):
            self.run_preflight(outdir=target)
        self.assertFalse(target.exists())

    def test_missing_notes_still_generate_readable_blocked_report(self):
        self.make()
        self.assert_blocked(self.run_preflight(notes=self.base / 'missing.md'), 'release_notes')

    def test_supplied_runtime_evidence_is_retained_without_asserting_acceptance(self):
        self.make()
        evidence = self.base / 'runtime.md'
        evidence.write_text('Synthetic example: PASS', encoding='utf-8')
        report = self.run_preflight(runtime_evidence=evidence)
        self.assertEqual(report['status'], 'ready_for_draft_review')
        self.assertEqual(report['runtime_evidence']['status'], 'supplied_unreviewed')
        self.assertFalse(report['runtime_evidence']['verified'])
        self.assertEqual((self.out / 'runtime-evidence-supplied.txt').read_bytes(), evidence.read_bytes())


if __name__ == '__main__':
    unittest.main()
