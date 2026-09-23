"""Prepare an offline GitHub draft request; never publish, install or execute a ZIP.

Only public artifacts qualify. Candidate names and source-review gaps remain
blocking evidence. A successful run proves local structural checks, not runtime
acceptance, independent legal review, remote authenticity or publish approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.parse import quote
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from update_installer import (HIDDEN, MAX_ARCHIVE, MAX_ENTRIES, MAX_EXPANDED,
                              MAX_FILE, MAX_MANIFEST, MAX_PORTABLE_METADATA,
                              UpdateError, extract_package, reject_reparse,
                              safe_name, sha256)
from updater import REPOSITORY, SemVer, release_assets, tag_version
from scripts.build_portable import ROOT_FILES
from scripts.verify_runtime_seed import verify_runtime_seed
from media_runtime import MEDIA_DIRECTORY, verify_media

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT = 1024 ** 2
# Required application inputs plus every other application asset in the actual
# package. Dependency/runtime binaries are separately bound by their inventories.
KEY_APPLICATION_FILES = ROOT_FILES + ('ui/index.html',)
FAILURES = (OSError, ValueError, TypeError, KeyError, UpdateError,
            zipfile.BadZipFile, RuntimeError, subprocess.SubprocessError)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def parse_json(raw):
    def invalid_constant(value):
        raise ValueError('Non-finite JSON value: ' + value)
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)


def public_names(version):
    base = 'ExperienceRecorder-' + version + '-windows-x64'
    return (base + '.zip', base + '-dependency-sources.zip', base + '-SHA256SUMS.txt')


def candidate_names(version):
    base = 'ExperienceRecorder-' + version + '-windows-x64-candidate'
    return (base + '.zip', base + '-dependency-sources.zip', base + '-SHA256SUMS.txt')


def validate_tag(tag):
    if not isinstance(tag, str) or not re.fullmatch(
            r'v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)'
            r'(?:-preview\.(?:0|[1-9][0-9]*))?', tag):
        raise ValueError('Tag must be vX.Y.Z or vX.Y.Z-preview.N, without leading zeroes.')
    version, semantic = tag_version(tag)
    # Keep release preparation and the client semantic-version implementation aligned.
    if semantic != SemVer(version):
        raise ValueError('Updater version parsing mismatch.')
    return version, semantic


def safe_file(path, limit):
    reject_reparse(path)
    if not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise ValueError('Missing, empty or oversized input: ' + str(path))
    return path


def zip_json(path, name, limit=MAX_MANIFEST):
    safe_file(path, MAX_ARCHIVE)
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > MAX_ENTRIES + 1:
            raise ValueError('ZIP entry count exceeds the limit.')
        entries = [item for item in archive.infolist() if item.filename.casefold() == name.casefold()]
        if len(entries) != 1 or entries[0].filename != name:
            raise ValueError('ZIP metadata is missing or ambiguous: ' + name)
        item = entries[0]
        if item.file_size > limit or item.flag_bits & 1 or stat.S_ISLNK(item.external_attr >> 16):
            raise ValueError('ZIP metadata is oversized, encrypted or a link: ' + name)
        return parse_json(archive.read(item))


def verify_source_archive(path):
    safe_file(path, MAX_ARCHIVE)
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= MAX_ENTRIES or sum(item.file_size for item in infos) > MAX_EXPANDED:
            raise ValueError('Dependency source ZIP exceeds entry or expansion limits.')
        entries, aliases = {}, set()
        for item in infos:
            name = safe_name(item.filename)
            mode = item.external_attr >> 16
            if (item.is_dir() or item.flag_bits & 1 or stat.S_ISLNK(mode)
                    or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                    or item.external_attr & 0x400 or name.casefold() in aliases
                    or item.file_size > MAX_FILE):
                raise ValueError('Dependency source ZIP has duplicate, linked, encrypted or oversized entries.')
            aliases.add(name.casefold())
            entries[name] = item
        info = entries.get('source-manifest.json')
        if info is None or info.file_size > MAX_MANIFEST:
            raise ValueError('Dependency source ZIP lacks a bounded source-manifest.json.')
        manifest = parse_json(archive.read(info))
        if not isinstance(manifest, dict) or manifest.get('schema') != 1 or not isinstance(manifest.get('files'), list):
            raise ValueError('Dependency source manifest has an unsupported schema.')
        if not 1 <= len(manifest['files']) <= MAX_ENTRIES - 1:
            raise ValueError('Dependency source file inventory is empty or oversized.')
        expected, recorded, verified = {'source-manifest.json'}, set(), []
        for record in manifest['files']:
            if not isinstance(record, dict):
                raise ValueError('Invalid dependency source record.')
            name = safe_name(record.get('filename'))
            size, digest = record.get('bytes'), record.get('sha256')
            if (not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or name == 'source-manifest.json'
                    or name.casefold() in recorded or type(size) is not int or not 0 <= size <= MAX_FILE
                    or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
                raise ValueError('Invalid or duplicate dependency source file record: ' + name)
            recorded.add(name.casefold())
            expected.add(name)
            if name not in entries or entries[name].file_size != size:
                raise ValueError('Dependency source file is missing or differs in size: ' + name)
            actual, count = hashlib.sha256(), 0
            with archive.open(entries[name]) as source:
                for block in iter(lambda: source.read(1024 ** 2), b''):
                    count += len(block)
                    if count > size:
                        raise ValueError('Dependency source expansion exceeds its declared size: ' + name)
                    actual.update(block)
            if count != size or actual.hexdigest() != digest:
                raise ValueError('Dependency source digest mismatch: ' + name)
            verified.append({'name': name, 'bytes': count, 'sha256': actual.hexdigest()})
        # The packager may accompany the pinned archives with FFmpeg configuration.
        if 'ffmpeg-buildconf.txt' in entries and 'ffmpeg-buildconf.txt' not in expected:
            if entries['ffmpeg-buildconf.txt'].file_size > MAX_TEXT:
                raise ValueError('FFmpeg build configuration is oversized.')
            archive.read('ffmpeg-buildconf.txt')  # Also checks its CRC.
            expected.add('ffmpeg-buildconf.txt')
        if set(entries) != expected:
            raise ValueError('Dependency source ZIP contains files outside its source inventory.')
        return manifest, verified


def inspect_source_gate(manifest):
    if not isinstance(manifest, dict):
        raise ValueError('Dependency source manifest must be an object.')
    gaps = manifest.get('gaps')
    if manifest.get('redistribution_ready') is not True or gaps != []:
        raise ValueError('Public redistribution source review is incomplete: ' +
                         json.dumps(gaps, ensure_ascii=False))


def git_output(repo, *args, input=None):
    result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                            input=input, timeout=30, creationflags=HIDDEN, check=False)
    if result.returncode:
        raise ValueError('Local Git check failed: ' + result.stderr.decode('utf-8', errors='replace').strip()[:1000])
    return result.stdout


def verify_commit(repo, commit):
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', commit):
        raise ValueError('--commit must be a full 40-character hexadecimal commit SHA.')
    actual = git_output(repo, 'rev-parse', '--verify', commit + '^{commit}').decode('ascii').strip()
    if actual.lower() != commit.lower():
        raise ValueError('Target SHA does not identify the specified commit object.')
    return actual


def verify_commit_files(repo, commit, stage):
    records = []
    tracked = {}
    for entry in git_output(repo, 'ls-tree', '-r', '--long', '-z', commit).split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, oid, size = metadata.split()
        if kind == b'blob':
            tracked[name.decode('utf-8')] = (oid.decode('ascii'), int(size))
    packaged_names = {item['path'] for item in parse_json((stage / 'package-manifest.json').read_bytes())['files']}
    names = set(KEY_APPLICATION_FILES)
    for name in packaged_names:
        # The repository retains a historical portable.json template. The
        # builder generates release metadata; protocol/version checks above
        # validate it instead of comparing it to that development template.
        if name == 'portable.json':
            continue
        if (name in tracked or name.startswith(('ui/', 'scripts/'))
                or '/' not in name and name.endswith('.py')):
            names.add(name)
    names = sorted(names)
    for name in names:
        path = stage / name
        if not path.is_file():
            raise ValueError('Key application file missing from package: ' + name)
        if name not in tracked:
            raise ValueError('Packaged application file absent from target commit: ' + name)
        if path.stat().st_size > MAX_MANIFEST:
            raise ValueError('Key application source exceeds its comparison limit: ' + name)
        if tracked[name][1] > MAX_MANIFEST:
            raise ValueError('Committed application source exceeds its comparison limit: ' + name)
    # One bounded batch avoids spawning hundreds of Git processes for a package.
    blobs = git_output(repo, 'cat-file', '--batch',
                       input=''.join(tracked[name][0] + '\n' for name in names).encode('ascii'))
    offset = 0
    for name in names:
        path = stage / name
        end = blobs.index(b'\n', offset)
        oid, kind, size = blobs[offset:end].split()
        size = int(size)
        if (oid.decode('ascii'), size) != tracked[name] or kind != b'blob':
            raise ValueError('Unexpected Git blob response: ' + name)
        committed = blobs[end + 1:end + 1 + size]
        offset = end + size + 2
        packaged = path.read_bytes()
        if packaged == committed:
            method = 'exact_bytes'
        elif (b'\0' not in packaged and b'\0' not in committed
              and (path.suffix.lower() in ('.py', '.html', '.css', '.js', '.json', '.md', '.txt', '.svg')
                   or path.name in ('LICENSE', 'COPYING', 'NOTICE'))
              and packaged.replace(b'\r\n', b'\n') == committed.replace(b'\r\n', b'\n')):
            method = 'crlf_normalized_text'
        else:
            raise ValueError('Packaged application source differs from target commit: ' + name)
        records.append({'path': name, 'comparison': method,
                        'package_sha256': hashlib.sha256(packaged).hexdigest(),
                        'commit_blob_sha256': hashlib.sha256(committed).hexdigest()})
    return records


def prepare_release(*, tag, commit, artifacts, notes, outdir, runtime_evidence=None, repo_root=None):
    """Return the report; retain all diagnostic and staged files on a blocked run."""
    artifacts, notes, outdir = (Path(value).absolute() for value in (artifacts, notes, outdir))
    repo_root = Path(repo_root or REPO_ROOT).absolute()
    runtime_evidence = Path(runtime_evidence).absolute() if runtime_evidence is not None else None
    # Unsafe paths and output conflicts fail before any output is created.
    for path in (artifacts, notes, outdir, repo_root, *([runtime_evidence] if runtime_evidence else [])):
        reject_reparse(path)
    artifacts, notes, outdir, repo_root = (path.resolve() for path in (artifacts, notes, outdir, repo_root))
    if outdir.exists():
        raise FileExistsError('Output directory already exists; choose a new directory: ' + str(outdir))
    if (outdir.is_relative_to(artifacts) or artifacts.is_relative_to(outdir)
            or notes.is_relative_to(outdir) or repo_root.is_relative_to(outdir)
            or (runtime_evidence and runtime_evidence.resolve().is_relative_to(outdir))):
        raise ValueError('Output directory overlaps an input; choose a separate new directory.')
    outdir.mkdir(parents=True, exist_ok=False)
    report = {'schema': 1, 'repository': REPOSITORY, 'tag': tag, 'target_commit': commit,
              'status': 'blocked', 'checks': [], 'blockers': [], 'artifacts': [],
              'candidate_counterparts': [], 'source_gaps': [],
              'runtime_evidence': {'status': 'pending', 'verified': False},
              'pending': ['Human approval before any GitHub write or publication.',
                          'Real packaged-app runtime acceptance tied to these artifact hashes.',
                          'Human corresponding-source and redistribution review; flags are declarations.'],
              'scope': 'Offline structural verification only; no package code executed, no installation changed, no network requests.'}

    def check(name, operation):
        try:
            value = operation()
        except FAILURES as error:
            message = str(error)
            report['checks'].append({'name': name, 'status': 'blocked', 'detail': message})
            report['blockers'].append({'check': name, 'detail': message})
            return None
        report['checks'].append({'name': name, 'status': 'passed'})
        return value

    parsed = check('tag', lambda: validate_tag(tag))
    pinned_commit = check('local_target_commit', lambda: verify_commit(repo_root, commit))
    if pinned_commit:
        report['target_commit'] = pinned_commit

    def read_notes():
        raw = safe_file(notes, MAX_TEXT).read_bytes()
        value = raw.decode('utf-8-sig')
        if not value.strip():
            raise ValueError('Release notes must contain text.')
        (outdir / 'release-notes-draft.md').write_bytes(raw)
        return value

    notes_text = check('release_notes', read_notes)
    if notes_text is None:
        (outdir / 'release-notes-draft.md').write_text(
            '# Release notes draft\n\nBlocked: the supplied notes could not be copied. See release-preflight.json.\n', encoding='utf-8')
    if runtime_evidence:
        def record_runtime_evidence():
            raw = safe_file(runtime_evidence, MAX_TEXT).read_bytes()
            (outdir / 'runtime-evidence-supplied.txt').write_bytes(raw)
            return {'status': 'supplied_unreviewed', 'verified': False,
                    'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                    'detail': 'Retained as supplied; this tool does not infer runtime success from its contents.'}
        evidence = check('runtime_evidence_input', record_runtime_evidence)
        if evidence:
            report['runtime_evidence'] = evidence

    if parsed:
        version, semantic = parsed
        report['version'], report['prerelease'] = version, bool(semantic.pre)
        names, candidates = public_names(version), candidate_names(version)
        report['required_assets'] = list(names)
        report['candidate_counterparts'] = [name for name in candidates if (artifacts / name).exists()]

        def inspect_inputs():
            if not artifacts.is_dir():
                raise ValueError('Artifact directory does not exist: ' + str(artifacts))
            missing = [name for name in names if not (artifacts / name).is_file()]
            if missing:
                raise ValueError('Missing exact public assets: ' + ', '.join(missing) +
                                 ('. Candidate counterparts exist and cannot be renamed or admitted.' if report['candidate_counterparts'] else ''))
            for name in names:
                safe_file(artifacts / name, MAX_TEXT if name.endswith('.txt') else MAX_ARCHIVE)
            return True

        assets_present = check('exact_public_assets', inspect_inputs)
        # Diagnose actual candidate source gates even when the public assets are missing.
        for index, entry in ((0, 'dependency-source-manifest.json'), (1, 'source-manifest.json')):
            selected = next((artifacts / name for name in (names[index], candidates[index])
                             if (artifacts / name).is_file()), None)
            if selected:
                manifest = check('source_declaration_' + entry, lambda p=selected, n=entry: zip_json(p, n))
                if isinstance(manifest, dict):
                    report['source_gaps'].append({'asset': selected.name,
                                                 'redistribution_ready': manifest.get('redistribution_ready'),
                                                 'gaps': manifest.get('gaps')})
                    check('public_source_gate_' + entry, lambda m=manifest: inspect_source_gate(m))

        if assets_present:
            def verify_checksums():
                text = (artifacts / names[2]).read_text(encoding='utf-8')
                expected, checksums = set(names[:2]), {}
                for line in text.splitlines():
                    if not line.strip():
                        continue
                    match = re.fullmatch(r'([0-9a-fA-F]{64})[ \t]+\*?([^/\\]+)', line)
                    if not match or match[2] not in expected or match[2] in checksums:
                        raise ValueError('Checksums must uniquely list exactly the two public ZIP filenames.')
                    checksums[match[2]] = match[1].lower()
                if set(checksums) != expected:
                    raise ValueError('Checksum file does not list both public ZIPs.')
                inventory = []
                for name in names:
                    path = artifacts / name
                    before = path.stat()
                    digest = sha256(path)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError('Artifact changed during verification: ' + name)
                    if name in checksums and digest != checksums[name]:
                        raise ValueError('Release ZIP SHA-256 mismatch: ' + name)
                    inventory.append({'name': name, 'path': str(path), 'bytes': after.st_size, 'sha256': digest})
                return inventory

            inventory = check('release_checksums', verify_checksums)
            if inventory:
                report['artifacts'] = inventory
                def client_contract():
                    release = {'tag_name': tag, 'assets': [
                        {'name': item['name'], 'state': 'uploaded', 'size': item['bytes'],
                         'digest': 'sha256:' + item['sha256'],
                         'browser_download_url': 'https://github.com/' + REPOSITORY + '/releases/download/' +
                         quote(tag, safe='') + '/' + quote(item['name'], safe='')} for item in inventory]}
                    release_assets(release, version)
                    return True
                check('updater_asset_contract', client_contract)
            source_result = check('dependency_source_integrity', lambda: verify_source_archive(artifacts / names[1]))
            stage = outdir / 'validated-package'
            metadata = check('production_public_package_validation', lambda: extract_package(
                artifacts / names[0], stage, expected_version=version, allow_candidate=False))
            if metadata is not None:
                def package_metadata():
                    if metadata.get('update_repository') != REPOSITORY or type(metadata.get('update_protocol')) is not int or metadata['update_protocol'] != 1:
                        raise ValueError('portable.json must explicitly name the fixed repository and update_protocol 1.')
                    return True
                check('fixed_update_repository_protocol', package_metadata)
                packaged_sources = check('packaged_source_manifest', lambda: parse_json(
                    safe_file(stage / 'dependency-source-manifest.json', MAX_MANIFEST).read_bytes()))
                if source_result and packaged_sources is not None:
                    def same_sources():
                        if source_result[0] != packaged_sources:
                            raise ValueError('Source ZIP manifest differs semantically from the packaged dependency manifest.')
                        inspect_source_gate(source_result[0])
                        report['verified_source_files'] = source_result[1]
                        return True
                    check('matching_public_source_manifests', same_sources)
                if pinned_commit:
                    matching = check('key_application_commit_binding', lambda: verify_commit_files(repo_root, pinned_commit, stage))
                    if matching:
                        report['commit_binding'] = {'status': 'application_files_match', 'files': matching,
                            'limit': 'Required application files and every tracked packaged asset were compared; untracked UI/scripts/root Python are rejected. Text CRLF normalization is explicitly recorded. Runtime/dependency bytes use separate inventories. This is not proof of reproducible compilation or signed provenance.'}
                seed = check('accepted_runtime_seed_binding', lambda: verify_runtime_seed(stage))
                if seed:
                    report['runtime_seed_binding'] = seed
                def media_binding():
                    if not isinstance(packaged_sources, dict) or not isinstance(packaged_sources.get('provenance'), dict):
                        raise ValueError('Packaged dependency source provenance must be an object.')
                    try:
                        manifest = verify_media(stage)
                    except AttributeError as error:
                        raise ValueError('Media runtime provenance has an invalid object shape.') from error
                    expected = packaged_sources['provenance'].get('media_runtime_manifest_sha256')
                    if not expected or sha256(stage / MEDIA_DIRECTORY / 'provenance.json') != expected:
                        raise ValueError('Media runtime inventory differs from dependency source provenance.')
                    return {'version': manifest.get('version'), 'files': len(manifest['files']),
                            'manifest_sha256': expected}
                media = check('media_runtime_source_binding', media_binding)
                if media:
                    report['media_runtime_binding'] = media
            if inventory:
                def unchanged():
                    for item in inventory:
                        path = safe_file(Path(item['path']), MAX_TEXT if item['name'].endswith('.txt') else MAX_ARCHIVE)
                        if path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
                            raise ValueError('Release artifact changed after validation: ' + item['name'])
                    return True
                check('artifacts_unchanged_after_validation', unchanged)

    if not report['blockers']:
        report['status'] = 'ready_for_draft_review'
        request = {'tag_name': tag, 'target_commitish': pinned_commit,
                   'name': 'Experience Recorder ' + tag, 'body': notes_text,
                   'draft': True, 'prerelease': report['prerelease']}
        (outdir / 'release-draft.json').write_bytes(json_bytes(request))
        (outdir / 'release-upload-manifest.json').write_bytes(json_bytes(
            {'schema': 1, 'repository': REPOSITORY, 'tag': tag,
             'assets': report['artifacts'], 'upload_performed': False}))
    (outdir / 'release-preflight.json').write_bytes(json_bytes(report))
    lines = ['# Local release preflight', '', 'Status: **' + report['status'] + '**', '',
             'Repository: `' + REPOSITORY + '`', 'Tag: `' + str(tag) + '`',
             'Target commit: `' + str(commit) + '`', '', report['scope'], '', '## Checks', '']
    lines += ['- ' + item['status'] + ': ' + item['name'] +
              (' — ' + item['detail'] if 'detail' in item else '') for item in report['checks']]
    if report['candidate_counterparts']:
        lines += ['', '## Existing candidate files', '', *['- ' + name for name in report['candidate_counterparts']]]
    lines += ['', '## Still pending', '', *['- ' + item for item in report['pending']], '',
              'Runtime evidence: ' + report['runtime_evidence']['status'] + '.', '',
              'Draft and upload JSON exist only when all local checks pass. No GitHub write is performed.', '']
    (outdir / 'release-preflight.md').write_text('\n'.join(lines), encoding='utf-8')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--artifacts', required=True, type=Path)
    parser.add_argument('--notes', required=True, type=Path)
    parser.add_argument('--outdir', required=True, type=Path)
    parser.add_argument('--runtime-evidence', type=Path)
    args = parser.parse_args(argv)
    try:
        report = prepare_release(**vars(args))
    except FAILURES as error:
        print('Preflight input/output rejected: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps({'status': report['status'], 'outdir': str(args.outdir.resolve()),
                      'blockers': report['blockers']}, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'ready_for_draft_review' else 1


if __name__ == '__main__':
    raise SystemExit(main())
