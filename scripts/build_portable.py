"""Deterministic allowlist packager; runtime/config/model data never join the ZIP.

This packages a prepared, verified Windows seed, not a source-to-binary rebuild.
Public builds require a reviewed complete corresponding-source manifest. Use
--candidate for private evaluation while documented source gaps remain.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tarfile
import zipfile

# Running this script with a prepared private runtime must use this checkout's
# protocol, rather than a neighbouring seed's application modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from updater import SemVer
from app_paths import application_root, installation_root
from media_runtime import MEDIA_DIRECTORY, verify_media
from scripts.verify_runtime_seed import verify_runtime_seed
from scripts.brand_launcher import branded_stub

ROOT_FILES = (
    'app.py', 'app_paths.py', 'desktop_service.py', 'hotword_files.py', 'hotword_ui.py',
    'model_manager.py', 'model-manifest.json', 'media_runtime.py', 'portable_check.py', 'portable_config.py',
    'portable_entry.py', 'processing_worker.py', 'processing.py', 'qwen_transcription.py',
    'recorder.py', 'window_manager.py', 'review_runtime.py', 'scel_to_text.py', 'secret_store.py',
    'transcription_runtime.py', 'player.html', 'requirements-lock.txt',
    'input_capture.py', 'input_capture_windows.py', 'input_capture_devices.py', 'session_metadata.py',
    'updater.py', 'update_installer.py',
    'LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/build.md', 'docs/updates.md',
    'scripts/build_portable.py', 'scripts/brand_launcher.py', 'scripts/fetch_runtime.py', 'scripts/fetch_input_runtime.py',
    'scripts/fetch_media_runtime.py',
    'scripts/verify_runtime_seed.py', 'scripts/migrate_layout.py', 'scripts/runtime-seed.json', 'docs/release-readiness.md',
    'vocabularies/uiux-terms.txt', 'docs/uiux-vocabulary.md', 'docs/input-capture-validation.md',
)
OPTIONAL_ROOT_FILES = ('README.md',)
BLOCKED_PARTS = {'__pycache__', '.git', '.cache', 'cache', 'caches', 'logs', 'log',
                 'crashes', 'crashdumps', 'pip-cache', 'wheelhouse', '.pytest_cache',
                 'gpucache', 'dawncache', 'code cache', 'local storage', 'session storage'}
UI_EXTENSIONS = {'.html', '.css', '.js', '.svg', '.png', '.ico', '.woff', '.woff2'}
STAMP = (1980, 1, 1, 0, 0, 0)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def excluded(path):
    parts = [p.lower() for p in path.parts]
    name = parts[-1]
    return (any(part in BLOCKED_PARTS for part in parts)
            or name.startswith('.env') or name.endswith(('.pyc', '.pyo', '.log', '.dpapi', '.lock'))
            or name == 'direct_url.json')


def collect_files(root):
    root = application_root(root)
    entries = {}
    def add(relative, required=True):
        file = (installation_root(root) if relative.startswith('vocabularies/') else root) / relative
        if not file.is_file():
            if required:
                raise ValueError('Missing package input: ' + relative)
            return
        if file.is_symlink() or not file.resolve().is_relative_to(installation_root(root)):
            raise ValueError('Symlink/path escape in package input: ' + relative)
        entries[Path(relative).as_posix()] = file
    for relative in ROOT_FILES:
        add(relative)
    for relative in OPTIONAL_ROOT_FILES:
        add(relative, False)
    for relative in ('tools/input/SDL2.dll', 'tools/input/provenance.json', 'licenses/SDL2-zlib.txt'):
        add(relative)
    for dirname in ('licenses', 'ui', 'runtime', 'tools/obs'):
        base = root / dirname
        if not base.is_dir():
            raise ValueError('Missing package directory: ' + dirname)
        for file in sorted(base.rglob('*')):
            relative = file.relative_to(root)
            local = file.relative_to(base)
            if excluded(relative) or not file.is_file():
                continue
            # Keep the Python package's notices but never ship its legacy CLI.
            if (relative.as_posix().startswith('runtime/Lib/site-packages/imageio_ffmpeg/binaries/')
                    and file.suffix.lower() == '.exe'):
                continue
            if dirname == 'ui' and file.suffix.lower() not in UI_EXTENSIONS:
                continue
            if dirname == 'runtime':
                if len(local.parts) == 1:
                    if file.suffix.lower() not in {'.dll', '.exe', '._pth'} and file.name != 'LICENSE.txt':
                        continue
                elif local.parts[0] not in {'Lib', 'DLLs', 'tcl'}:
                    continue
            if dirname == 'tools/obs':
                if local.as_posix() != 'portable_mode.txt' and local.parts[0] not in {'bin', 'data', 'obs-plugins'}:
                    continue
            add(relative.as_posix())
    for required in ('ui/index.html', 'ui/review.js', 'ui/review.css',
                     'ui/vendor/plyr/plyr.min.js', 'ui/vendor/plyr/plyr.css', 'ui/vendor/plyr/plyr.svg',
                     'licenses/Plyr-MIT.txt', 'runtime/python.exe', 'runtime/pythonw.exe',
                     'runtime/python312._pth', 'tools/obs/bin/64bit/obs64.exe',
                     'tools/obs/portable_mode.txt'):
        if required not in entries:
            raise ValueError('Required runtime component missing: ' + required)
    return entries


def compact_dependency_notices(files):
    """Keep original notice bytes under short Windows-update-safe paths."""
    prefix = 'licenses/dependency-materials/'
    notices = {name: value for name, value in files.items() if name.startswith(prefix)}
    if not notices:
        return files, {}
    index_name = prefix + 'index.json'
    # A prepared package can itself become a seed. Do not wrap its index again.
    if index_name in notices and all(name == index_name or re.fullmatch(
            re.escape(prefix) + r'f/[0-9a-f]{64}\.(txt|html|json)', name)
            for name in notices):
        return files, {}
    if index_name in notices:
        raise ValueError('Mixed compact and original dependency notices; use a clean prepared seed.')
    result = {name: value for name, value in files.items() if not name.startswith(prefix)}
    records = []
    for name, value in sorted(notices.items()):
        digest = sha256(value)
        extension = Path(name).suffix.lower()
        if extension not in {'.html', '.json'}:
            extension = '.txt'
        target = prefix + 'f/' + digest + extension
        result[target] = value
        records.append({'origin': name[len(prefix):], 'file': target[len(prefix):],
                        'bytes': value.stat().st_size, 'sha256': digest})
    return result, {index_name: json_bytes({'schema': 1,
        'description': 'Original upstream notice bytes; origin maps the acquisition path to its packaged file.',
        'files': records})}


def package_path(name):
    return name if name == 'Think Aloud.exe' or name.startswith('vocabularies/') else 'app/' + name


def launcher_bytes(version='0.0.0', icon_path=None):
    # Preserve distlib's GUI code/manifest, with the application's native icon
    # and version resources. Relative shebang resolves beside the launcher.
    from pip._vendor.distlib.scripts import ScriptMaker
    maker = ScriptMaker(None, '.')
    stub = maker._get_launcher('w')
    if not stub.startswith(b'MZ'):
        raise ValueError('Invalid Windows launcher resource')
    icon_path = Path(icon_path or Path(__file__).resolve().parents[1] / 'ui/brand.ico')
    stub = branded_stub(stub, icon_path.read_bytes(), version)
    source = b'from portable_entry import main\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(zipfile.ZipInfo('__main__.py', STAMP), source)
    return stub + b'#!<launcher_dir>\\app\\runtime\\pythonw.exe\n' + buffer.getvalue()


def read_sources(source_dir, candidate):
    manifest_file = source_dir / 'source-manifest.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if not candidate and (manifest.get('redistribution_ready') is not True or manifest.get('gaps')):
        raise ValueError('Public redistribution source review is incomplete; use --candidate for private review. '
                         + '; '.join(manifest.get('gaps', [])))
    entries = {'source-manifest.json': manifest_file}
    for record in manifest['files']:
        name = record['filename']
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', name) or name in ('.', '..'):
            raise ValueError('Invalid dependency source filename')
        file = source_dir / name
        if file.is_symlink() or file.resolve().parent != source_dir.resolve():
            raise ValueError('Source path escapes its directory')
        if file.stat().st_size != record['bytes'] or sha256(file) != record['sha256']:
            raise ValueError('Dependency source mismatch: ' + name)
        entries[name] = file
    for name in ('ffmpeg-buildconf.txt',):
        if (source_dir / name).is_file():
            entries[name] = source_dir / name
    return manifest, entries


def write_zip(path, entries):
    if path.exists() or path.with_suffix(path.suffix + '.partial').exists():
        raise FileExistsError('Output exists; select a new output directory: ' + str(path))
    partial = path.with_suffix(path.suffix + '.partial')
    with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for name, value in sorted(entries.items()):
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            if isinstance(value, bytes):
                archive.writestr(info, value)
            else:
                before = value.stat()
                with value.open('rb') as source, archive.open(info, 'w', force_zip64=True) as target:
                    shutil.copyfileobj(source, target, 1024 * 1024)
                after = value.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise ValueError('Package input changed during build: ' + name)
    with zipfile.ZipFile(partial) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP integrity verification failed')
        manifest_name = next((name for name in ('app/package-manifest.json', 'package-manifest.json') if name in archive.namelist()), None)
        if manifest_name:
            inventory = json.loads(archive.read(manifest_name))['files']
            if set(archive.namelist()) != {item['path'] for item in inventory} | {manifest_name}:
                raise ValueError('ZIP entries differ from package manifest')
            for item in inventory:
                digest = hashlib.sha256()
                with archive.open(item['path']) as source:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        digest.update(block)
                if archive.getinfo(item['path']).file_size != item['bytes'] or digest.hexdigest() != item['sha256']:
                    raise ValueError('Package changed since inventory: ' + item['path'])
    partial.rename(path)
    return {'filename': path.name, 'bytes': path.stat().st_size, 'sha256': sha256(path)}


def build(root, outdir, source_dir=None, *, candidate=False, version='0.3.0', launcher=None):
    root, outdir = application_root(root), Path(outdir).resolve()
    source_dir = Path(source_dir or root / 'build/dependency-sources').resolve()
    SemVer(version)
    files = collect_files(root)
    sources, source_files = read_sources(source_dir, candidate)
    verify_media(root)
    expected_media = sources.get('provenance', {}).get('media_runtime_manifest_sha256')
    if not expected_media or sha256(root / MEDIA_DIRECTORY / 'provenance.json') != expected_media:
        raise ValueError('Bundled media runtime differs from dependency-source provenance')
    sdl = json.loads(files['tools/input/provenance.json'].read_text(encoding='utf-8'))
    if sha256(files['tools/input/SDL2.dll']) != sdl.get('dll_sha256'):
        raise ValueError('Bundled SDL2 differs from binary provenance')
    source_assets = {item.get('name'): item.get('sha256') for item in sdl.get('assets', [])
                     if str(item.get('name', '')).endswith('.tar.gz')}
    if not any(item.get('component') == 'SDL2' and item.get('sha256') == source_assets.get(item.get('filename'))
               and item.get('filename') in source_assets for item in sources['files']):
        raise ValueError('Matching SDL2 source archive missing from dependency sources')
    verify_runtime_seed(root, files)
    files, compact_notices = compact_dependency_notices(files)
    generated = {
        **compact_notices,
        'Think Aloud.exe': launcher if launcher is not None else launcher_bytes(version, root / 'ui/brand.ico'),
        'portable.json': json_bytes({'name': 'Think Aloud', 'version': version,
            'platform': 'windows-x64', 'models': 'optional', 'layout': 'compact-v1',
            'update_protocol': 1, 'update_repository': 'Elkhiffa/think-aloud-recorder',
            'release_status': 'candidate-not-for-public-redistribution' if candidate else 'public'}),
        'dependency-source-manifest.json': json_bytes(sources),
    }
    for record in sources['files']:
        if record.get('component') == 'FFmpeg core':
            with tarfile.open(source_dir / record['filename'], 'r:gz') as source:
                license_file = next((item for item in source if item.name.endswith('/COPYING.GPLv3')), None)
                if license_file is None or not license_file.isfile() or license_file.size > 100000:
                    raise ValueError('FFmpeg GPLv3 license missing from pinned source')
                generated['licenses/FFmpeg-GPL-3.0.txt'] = source.extractfile(license_file).read()
    # Only the launcher and editable dictionaries stay beside the app folder.
    files = {package_path(name): value for name, value in files.items()}
    generated = {package_path(name): value for name, value in generated.items()}
    # Generated notices deliberately supersede an older seed's same-path copy.
    # Inventory the final ZIP mapping, never both versions of an overridden path.
    inventory = [{'path': name,
                  'bytes': len(value) if isinstance(value, bytes) else value.stat().st_size,
                  'sha256': hashlib.sha256(value).hexdigest() if isinstance(value, bytes) else sha256(value)}
                 for name, value in sorted({**files, **generated}.items())]
    generated['app/package-manifest.json'] = json_bytes({'schema': 1, 'files': sorted(inventory, key=lambda x: x['path']),
        'reproducibility': 'Same prepared seed, source files, Python/zip implementation and launcher stub produce identical ZIP bytes.',
        'dependency_source_status': sources.get('redistribution_ready', False)})
    suffix = '-candidate' if candidate else ''
    base = 'ExperienceRecorder-' + version + '-windows-x64' + suffix
    # Refuse the whole set before writing its first archive. Keep failed or
    # previous output untouched instead of leaving a mixed release directory.
    names = (base + '-dependency-sources.zip', base + '.zip', base + '-SHA256SUMS.txt')
    for name in names:
        target = outdir / name
        if target.exists() or target.with_suffix(target.suffix + '.partial').exists():
            raise FileExistsError('Release output exists; choose a new output directory: ' + str(target))
    outdir.mkdir(parents=True, exist_ok=True)
    # A sources archive accompanies every binary archive, including candidates.
    results = [write_zip(outdir / (base + '-dependency-sources.zip'), source_files),
               write_zip(outdir / (base + '.zip'), {**files, **generated})]
    checksums = outdir / (base + '-SHA256SUMS.txt')
    with checksums.open('x', encoding='utf-8', newline='\n') as target:
        target.write(''.join(item['sha256'] + '  ' + item['filename'] + '\n' for item in results))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--outdir', required=True, type=Path)
    parser.add_argument('--source-dir', type=Path)
    parser.add_argument('--version', default='0.3.0')
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.outdir, args.source_dir,
                           candidate=args.candidate, version=args.version), indent=2))


if __name__ == '__main__':
    main()
