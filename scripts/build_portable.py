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
import tarfile
import zipfile

ROOT_FILES = (
    'app.py', 'desktop_service.py', 'hotword_files.py', 'hotword_ui.py',
    'model_manager.py', 'model-manifest.json', 'portable_check.py', 'portable_config.py',
    'portable_entry.py', 'processing_worker.py', 'processing.py', 'qwen_transcription.py',
    'recorder.py', 'review_runtime.py', 'scel_to_text.py', 'secret_store.py',
    'transcription_runtime.py', 'player.html', 'requirements-lock.txt',
    'LICENSE', 'THIRD_PARTY_NOTICES.md', 'docs/build.md',
    'scripts/build_portable.py', 'scripts/fetch_runtime.py',
)
OPTIONAL_ROOT_FILES = ('README.md',)
TEMPLATE_FILES = (
    '.obsidian/community-plugins.json',
    '.obsidian/plugins/experience-opener/main.js',
    '.obsidian/plugins/experience-opener/manifest.json',
    '.obsidian/plugins/media-transcript/main.js',
    '.obsidian/plugins/media-transcript/manifest.json',
    '.obsidian/plugins/media-transcript/styles.css',
    '.obsidian/plugins/media-transcript/data.json',
    '.obsidian/plugins/media-transcript/LICENSE',
)
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
    root = Path(root).resolve()
    entries = {}
    def add(relative, required=True):
        file = root / relative
        if not file.is_file():
            if required:
                raise ValueError('Missing package input: ' + relative)
            return
        if file.is_symlink() or not file.resolve().is_relative_to(root):
            raise ValueError('Symlink/path escape in package input: ' + relative)
        entries[Path(relative).as_posix()] = file
    for relative in ROOT_FILES:
        add(relative)
    for relative in OPTIONAL_ROOT_FILES:
        add(relative, False)
    for relative in TEMPLATE_FILES:
        add('vault-template/' + relative)
    for dirname in ('licenses', 'ui', 'runtime', 'tools/obs'):
        base = root / dirname
        if not base.is_dir():
            raise ValueError('Missing package directory: ' + dirname)
        for file in sorted(base.rglob('*')):
            relative = file.relative_to(root)
            local = file.relative_to(base)
            if excluded(relative) or not file.is_file():
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
    for required in ('ui/index.html', 'runtime/python.exe', 'runtime/pythonw.exe',
                     'runtime/python312._pth', 'tools/obs/bin/64bit/obs64.exe',
                     'tools/obs/portable_mode.txt'):
        if required not in entries:
            raise ValueError('Required runtime component missing: ' + required)
    return entries


def launcher_bytes():
    # Exact distlib GUI stub; the appended zip timestamp is fixed, unlike a
    # default ScriptMaker invocation. Relative shebang resolves beside launcher.
    from pip._vendor.distlib.scripts import ScriptMaker
    maker = ScriptMaker(None, '.')
    stub = maker._get_launcher('w')
    if not stub.startswith(b'MZ'):
        raise ValueError('Invalid Windows launcher resource')
    source = b'from portable_entry import main\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr(zipfile.ZipInfo('__main__.py', STAMP), source)
    return stub + b'#!<launcher_dir>\\runtime\\pythonw.exe\n' + buffer.getvalue()


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
        if 'package-manifest.json' in archive.namelist():
            inventory = json.loads(archive.read('package-manifest.json'))['files']
            if set(archive.namelist()) != {item['path'] for item in inventory} | {'package-manifest.json'}:
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


def build(root, outdir, source_dir=None, *, candidate=False, version='0.2.0', launcher=None):
    root, outdir = Path(root).resolve(), Path(outdir).resolve()
    source_dir = Path(source_dir or root / 'build/dependency-sources').resolve()
    if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?', version):
        raise ValueError('Invalid version')
    files = collect_files(root)
    sources, source_files = read_sources(source_dir, candidate)
    ffmpeg_name = 'runtime/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
    expected_ffmpeg = sources.get('provenance', {}).get('ffmpeg_binary_sha256')
    if expected_ffmpeg and (ffmpeg_name not in files or sha256(files[ffmpeg_name]) != expected_ffmpeg):
        raise ValueError('Bundled FFmpeg differs from dependency-source provenance')
    generated = {
        'ExperienceRecorder.exe': launcher if launcher is not None else launcher_bytes(),
        'portable.json': json_bytes({'name': 'Experience Recorder', 'version': version,
            'platform': 'windows-x64', 'models': 'optional',
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
    inventory = [{'path': name, 'bytes': value.stat().st_size, 'sha256': sha256(value)}
                 for name, value in sorted(files.items())]
    inventory.extend({'path': name, 'bytes': len(value), 'sha256': hashlib.sha256(value).hexdigest()}
                     for name, value in sorted(generated.items()))
    generated['package-manifest.json'] = json_bytes({'schema': 1, 'files': sorted(inventory, key=lambda x: x['path']),
        'reproducibility': 'Same prepared seed, source files, Python/zip implementation and launcher stub produce identical ZIP bytes.',
        'dependency_source_status': sources.get('redistribution_ready', False)})
    outdir.mkdir(parents=True, exist_ok=True)
    suffix = '-candidate' if candidate else ''
    base = 'ExperienceRecorder-' + version + '-windows-x64' + suffix
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
    parser.add_argument('--version', default='0.2.0')
    parser.add_argument('--candidate', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.root, args.outdir, args.source_dir,
                           candidate=args.candidate, version=args.version), indent=2))


if __name__ == '__main__':
    main()
