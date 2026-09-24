"""Verify the accepted prepared seed, not upstream signatures or a binary rebuild.

The checked-in lock must itself be bound to the release's target Git commit.
Never generate this lock from the package being verified: its package manifest
only supplies the actual file inventory, not trusted expected dependency hashes.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from update_installer import (MAX_ENTRIES, MAX_EXPANDED, MAX_FILE, MAX_MANIFEST,
                              UpdateError, reject_reparse, safe_name, sha256)

LOCK_PATH = 'scripts/runtime-seed.json'
NAMESPACES = ('runtime/', 'tools/obs/', 'tools/input/')
MEDIA_DIRECTORY = 'runtime/lib/think_aloud_media/'
LEGACY_BINARIES = 'runtime/lib/site-packages/imageio_ffmpeg/binaries/'


def _name(value):
    try:
        return safe_name(value)
    except UpdateError as error:
        raise ValueError('Unsafe runtime seed path: ' + repr(value)) from error


def seed_managed_path(name):
    """Match the fixed seed scope; new media has its own provenance verifier."""
    lower = _name(name).casefold()
    return (lower.startswith(NAMESPACES) and not lower.startswith(MEDIA_DIRECTORY)
            and not (lower.startswith(LEGACY_BINARIES) and lower.endswith('.exe')))


def _file(root, name):
    path = root / _name(name)
    try:
        reject_reparse(path)
    except UpdateError as error:
        raise ValueError('Runtime seed link or reparse point: ' + name) from error
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError('Runtime seed file missing or escapes root: ' + name)
    return path


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate runtime seed JSON key: ' + key)
        value[key] = item
    return value


def _read_json(path):
    if not 0 < path.stat().st_size <= MAX_MANIFEST:
        raise ValueError('Runtime seed metadata is empty or oversized: ' + str(path))
    def invalid_constant(value):
        raise ValueError('Invalid runtime seed JSON constant: ' + value)
    try:
        return json.loads(path.read_bytes(), object_pairs_hook=_unique_object,
                          parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Invalid runtime seed JSON: ' + str(path)) from error


def _records(document, *, lock=False):
    if (not isinstance(document, dict) or type(document.get('schema')) is not int
            or document['schema'] != 1 or not isinstance(document.get('files'), list)
            or not 1 <= len(document['files']) <= MAX_ENTRIES):
        raise ValueError('Invalid runtime seed inventory schema or file count')
    result, aliases = {}, set()
    for record in document['files']:
        if not isinstance(record, dict):
            raise ValueError('Invalid runtime seed record')
        name = _name(record.get('path'))
        size, digest = record.get('bytes'), record.get('sha256')
        if (name.casefold() in aliases or type(size) is not int or not 0 <= size <= MAX_FILE
                or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest)):
            raise ValueError('Duplicate or invalid runtime seed record: ' + name)
        if lock and not seed_managed_path(name):
            raise ValueError('Runtime seed lock contains an unmanaged path: ' + name)
        aliases.add(name.casefold())
        result[name] = record
    if sum(item['bytes'] for item in result.values()) > MAX_EXPANDED:
        raise ValueError('Runtime seed inventory exceeds expanded size limit')
    return result


def verify_runtime_seed(root, files=None):
    """Return verified identity/count/bytes or raise ValueError (I/O errors propagate).

    Build callers pass collect_files(root)'s path -> Path mapping. Preflight
    callers omit it after production extraction validates package-manifest.json.
    Only that selected package inventory is checked, not unrelated local files.
    Neither input inventory can override the checked-in lock's expected hashes.
    """
    from app_paths import application_root, installation_root
    root = application_root(root)
    try:
        reject_reparse(root)
    except UpdateError as error:
        raise ValueError('Runtime seed root is a link or reparse point') from error
    root = root.resolve()
    lock_file = _file(root, LOCK_PATH)
    lock = _read_json(lock_file)
    expected = _records(lock, lock=True)
    baseline = lock.get('baseline')
    if (not isinstance(baseline, dict) or not isinstance(baseline.get('version'), str)
            or not 0 < len(baseline['version']) <= 100
            or not isinstance(baseline.get('package_manifest_sha256'), str)
            or not re.fullmatch(r'[0-9a-f]{64}', baseline['package_manifest_sha256'])):
        raise ValueError('Runtime seed baseline identity is invalid')

    if files is None:
        inventory = _records(_read_json(_file(root, 'package-manifest.json')))
        if installation_root(root) != root:
            inventory = {name[4:]: record for name, record in inventory.items() if name.startswith('app/')}
        actual = {name: root / name for name in inventory if seed_managed_path(name)}
    else:
        if not isinstance(files, Mapping) or not 1 <= len(files) <= MAX_ENTRIES:
            raise ValueError('Runtime seed requires a bounded package file mapping')
        actual, aliases = {}, set()
        for name, path in files.items():
            _name(name)
            if name.casefold() in aliases:
                raise ValueError('Duplicate runtime seed file path: ' + name)
            aliases.add(name.casefold())
            if seed_managed_path(name):
                actual[name] = path

    missing, extra = set(expected) - set(actual), set(actual) - set(expected)
    if missing or extra:
        detail = []
        if missing:
            detail.append('missing: ' + ', '.join(sorted(missing)[:10]))
        if extra:
            detail.append('extra: ' + ', '.join(sorted(extra)[:10]))
        raise ValueError('Runtime seed file set mismatch; ' + '; '.join(detail))

    total = 0
    for name, record in expected.items():
        path = _file(root, name)
        try:
            supplied = Path(actual[name]).absolute()
            reject_reparse(supplied)
        except (TypeError, UpdateError) as error:
            raise ValueError('Invalid runtime seed mapped file: ' + name) from error
        if supplied.resolve() != path.resolve():
            raise ValueError('Runtime seed mapped file escapes or differs from its path: ' + name)
        before = path.stat()
        if before.st_size != record['bytes'] or sha256(path) != record['sha256']:
            raise ValueError('Runtime seed content mismatch: ' + name)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('Runtime seed file changed during verification: ' + name)
        total += record['bytes']
    return {'schema': 1, 'identity': 'accepted-prepared-seed',
            'baseline_version': baseline['version'],
            'baseline_package_manifest_sha256': baseline['package_manifest_sha256'],
            'seed_manifest_sha256': sha256(lock_file), 'files': len(expected), 'bytes': total,
            'upstream_signatures_or_rebuild_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path, help='Previously extracted and validated package root')
    args = parser.parse_args()
    try:
        result = verify_runtime_seed(args.root)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
