"""Fetch pinned dependency source materials, never install into the host.

The current Gyan FFmpeg dependency/build-script gap is deliberately recorded.
This is not a claim that core FFmpeg sources alone are corresponding source.
"""
import argparse
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import urllib.request
import zipfile

WEBVIEW_PACKAGE = {
    'component': 'Microsoft WebView2 SDK license and binary identity evidence',
    'version': '1.0.3856.49',
    'filename': 'Microsoft.Web.WebView2.1.0.3856.49.nupkg',
    'url': 'https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/1.0.3856.49/microsoft.web.webview2.1.0.3856.49.nupkg',
    'bytes': 9025251, 'sha256': 'bc0f76eb911b569838dc4aa8f8d325269b966bedb592863d26211aef3a099f1a',
}
MICROSOFT_TERMS = [
    {'component': 'Microsoft Visual C++ Runtime end-user terms',
     'filename': 'Visual-C-Runtime-2015-2022-License.docx',
     'url': 'https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx',
     'bytes': 39644, 'sha256': 'f1e3d56ceb2ad68aae0711b910375009e651ac5530fa0760f0dea6e81e54fae1'},
    {'component': 'Visual Studio Community 2022 distributor terms',
     'filename': 'Visual-Studio-2022-Community-License.docx',
     'url': 'https://visualstudio.microsoft.com/wp-content/uploads/2021/11/Visual-Studio-2022-Community-License-EN.docx',
     'bytes': 62859, 'sha256': '41a207b10c8ab91d0d2f10a854715f73dca54509581692d2fe179aa3ffcb8540'},
]

SOURCES = [
    {'component': 'OBS Studio', 'version': '32.2.2',
     'filename': 'OBS-Studio-32.2.2-Sources.tar.gz',
     'url': 'https://github.com/obsproject/obs-studio/releases/download/32.2.2/OBS-Studio-32.2.2-Sources.tar.gz',
     'bytes': 16660601, 'sha256': 'ec81fb66b03e75ddb3076b576f62679c39262e0e9960cef3e17a40dc5d68e6b4'},
    {'component': 'FFmpeg core', 'version': '7.1',
     'revision': 'b08d7969c550a804a59511c7b83f2dd8cc0499b8',
     'filename': 'FFmpeg-b08d7969c550a804a59511c7b83f2dd8cc0499b8.tar.gz',
     'url': 'https://codeload.github.com/FFmpeg/FFmpeg/tar.gz/b08d7969c550a804a59511c7b83f2dd8cc0499b8',
     'bytes': 15900622, 'sha256': '02fa6d9827da3b6786e4df821218cc036db2b4481e7f48267c2dcda695633afc'},
]


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as src:
        for block in iter(lambda: src.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def download_definition(definition, out):
    path = out / definition['filename']
    if not path.exists():
        partial = path.with_suffix(path.suffix + '.part')
        with urllib.request.urlopen(definition['url'], timeout=60) as response, partial.open('xb') as target:
            shutil.copyfileobj(response, target, 1024 * 1024)
        if (digest(partial) != definition['sha256']
                or partial.stat().st_size != definition['bytes']):
            raise ValueError('Downloaded evidence differs from pinned bytes: ' + path.name)
        partial.rename(path)
    if digest(path) != definition['sha256'] or path.stat().st_size != definition['bytes']:
        raise ValueError('Existing evidence differs from pinned bytes: ' + path.name)
    return path


def extract_webview_notices(package, root):
    """Match each shipped SDK DLL against its official package, then use its notices."""
    matches = []
    with zipfile.ZipFile(package) as archive:
        dlls = [name for name in archive.namelist() if name.lower().endswith('.dll')]
        for file in sorted((root / 'runtime/Lib/site-packages/webview/lib').rglob('*.dll')):
            if 'WebView2' not in file.name:
                continue
            local_hash = digest(file)
            members = [name for name in dlls if name.rsplit('/', 1)[-1] == file.name
                       and hashlib.sha256(archive.read(name)).hexdigest() == local_hash]
            if not members:
                raise ValueError('WebView2 DLL differs from the official SDK: ' + file.name)
            matches.append({'local': file.relative_to(root).as_posix(),
                            'sha256': local_hash, 'official_package_members': members})
        if not matches:
            raise ValueError('No WebView2 SDK DLLs found in the prepared runtime')
        return {'Microsoft-WebView2-SDK-LICENSE.txt': archive.read('LICENSE.txt'),
                'Microsoft-WebView2-SDK-NOTICE.txt': archive.read('NOTICE.txt'),
                'webview2-binary-match.json': (json.dumps(matches, indent=2) + '\n').encode('utf-8')}


def supplement(root, existing, out):
    """Write a successor evidence bundle. Never mutate the earlier source manifest."""
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'source-manifest.json'
    if target.exists():
        raise FileExistsError('Choose a new output directory for successor source evidence')
    manifest = json.loads((existing / 'source-manifest.json').read_text(encoding='utf-8'))
    for record in manifest['files']:
        file = existing / record['filename']
        if file.resolve().parent != existing.resolve() or digest(file) != record['sha256']:
            raise ValueError('Invalid predecessor source evidence')
        dest = out / file.name
        if not dest.exists():
            shutil.copyfile(file, dest)
        if digest(dest) != record['sha256']:
            raise ValueError('Successor source artifact mismatch')
    if (existing / 'ffmpeg-buildconf.txt').exists() and not (out / 'ffmpeg-buildconf.txt').exists():
        shutil.copyfile(existing / 'ffmpeg-buildconf.txt', out / 'ffmpeg-buildconf.txt')
    for definition in [WEBVIEW_PACKAGE, *MICROSOFT_TERMS]:
        download_definition(definition, out)
        manifest['files'].append(definition)
    extracted = extract_webview_notices(out / WEBVIEW_PACKAGE['filename'], root)
    for name, data in extracted.items():
        dest = out / name
        if dest.exists() and dest.read_bytes() != data:
            raise ValueError('Existing derived evidence differs: ' + name)
        if not dest.exists():
            dest.write_bytes(data)
        manifest['files'].append({'component': 'Microsoft WebView2 SDK extracted notice/identity',
            'filename': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
            'derived_from': WEBVIEW_PACKAGE['filename']})
    manifest['predecessor_manifest_sha256'] = digest(existing / 'source-manifest.json')
    manifest['resolved_evidence'] = {
        'webview2_sdk': 'All bundled WebView2 DLLs match official NuGet 1.0.3856.49. BSD-style LICENSE and third-party NOTICE are archived verbatim.',
        'microsoft_vc_terms': 'Full runtime end-user terms and VS Community 2022 distributor terms archived. VS section 4 is the redistribution grant; the runtime EULA alone is not.',
    }
    manifest['redistribution_ready'] = False
    # Adding Microsoft notices is not evidence that other upstream dependency
    # reviews have completed. Preserve inherited gaps in the successor bundle.
    manifest['gaps'] = list(dict.fromkeys([*manifest.get('gaps', []),
        'Exact Gyan FFmpeg 7.1 external-library source snapshots and build scripts are not supplied by its release assets; the archived FFmpeg core is not complete corresponding source.',
        'OBS binary dependencies and bundled native-wheel source/license coverage still require component-level review; top-level source archives and package labels do not close this review.',
    ]))
    manifest['release_conditions'] = [
        'Preserve WebView2 SDK LICENSE and NOTICE with the binaries.',
        'VC runtime redistribution must follow the applicable Visual Studio license and unmodified redistributable-file list; merely possessing the runtime does not establish the distributor grant.',
        'The supplied OBS release source and Python package notices are retained. This evidence update does not claim an exhaustive independent audit of every upstream binary dependency.',
    ]
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def fetch(out, root):
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for definition in SOURCES:
        path = out / definition['filename']
        if not path.exists():
            part = path.with_suffix(path.suffix + '.part')
            # Never overwrite a failed acquisition; its evidence stays available.
            with urllib.request.urlopen(definition['url'], timeout=60) as response, part.open('xb') as target:
                while block := response.read(1024 * 1024):
                    target.write(block)
            actual = digest(part)
            if definition.get('sha256') and actual != definition['sha256']:
                raise ValueError('Source digest mismatch: ' + definition['filename'])
            if definition.get('bytes') and part.stat().st_size != definition['bytes']:
                raise ValueError('Source size mismatch: ' + definition['filename'])
            part.rename(path)
        actual = digest(path)
        if definition.get('sha256') and actual != definition['sha256']:
            raise ValueError('Existing source digest mismatch: ' + definition['filename'])
        records.append({**definition, 'bytes': path.stat().st_size, 'sha256': actual})
    binary = root / 'runtime/Lib/site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
    if not binary.is_file():
        raise ValueError('Expected imageio FFmpeg 7.1 binary missing')
    version = subprocess.check_output([str(binary), '-version'], text=True, encoding='utf-8', errors='replace')
    if '7.1-essentials_build-www.gyan.dev' not in version:
        raise ValueError('FFmpeg seed differs from source manifest')
    (out / 'ffmpeg-buildconf.txt').write_text(version, encoding='utf-8')
    manifest = {
        'schema': 1, 'redistribution_ready': False,
        'gaps': ['Gyan FFmpeg 7.1 external library source snapshots and the exact build scripts are not yet archived.',
                 'OBS binary dependencies and bundled Python binary-wheel source/license obligations require release review.'],
        'provenance': {
            'obs_release': 'https://api.github.com/repos/obsproject/obs-studio/releases/tags/32.2.2',
            'ffmpeg_release': 'https://api.github.com/repos/GyanD/codexffmpeg/releases/tags/7.1',
            'ffmpeg_release_source_commit': 'b08d7969c550a804a59511c7b83f2dd8cc0499b8',
            'imageio_version': '0.6.0',
            'ffmpeg_binary_sha256': digest(binary),
        },
        'files': records,
    }
    target = out / 'source-manifest.json'
    if target.exists():
        previous = json.loads(target.read_text(encoding='utf-8'))
        if previous != manifest:
            raise ValueError('Source manifest already exists and differs; choose a new output directory')
    else:
        target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--outdir', type=Path)
    parser.add_argument('--supplement-existing', type=Path,
                        help='Create a successor source bundle with exact WebView2 notices and VC terms')
    args = parser.parse_args()
    out = args.outdir or args.root / 'build/dependency-sources'
    if args.supplement_existing:
        if not args.outdir:
            parser.error('--supplement-existing requires a new --outdir')
        result = supplement(args.root.resolve(), args.supplement_existing.resolve(), out.resolve())
    else:
        result = fetch(out.resolve(), args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
