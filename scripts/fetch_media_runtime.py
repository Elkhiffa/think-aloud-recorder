"""Prepare the pinned OBS-project FFmpeg CLI in its own portable directory."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from urllib.request import Request, urlopen
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from media_runtime import MEDIA_DIRECTORY, verify_media

RELEASE = '2026-07-15'
REVISION = '8683107a02300923abe4f293920f4b5edc8cb624'
ARCHIVE = 'windows-deps-' + RELEASE + '-x64.zip'
URL = 'https://github.com/obsproject/obs-deps/releases/download/' + RELEASE + '/' + ARCHIVE
ARCHIVE_SHA256 = '6f90e9598fa10cff5ad23cdcfae49b87868c07bf896b02cd464582b4ce2f2ba9'
FILES = {
    'ffmpeg.exe': '3677b8ab492c67500d28acba9faec78acc9717151994363ef2771ee023122e2c',
    'avdevice-62.dll': 'fc5d09a6a3fc12b50c2dcf663078155c0042ad503a1031cb68aa9774978ae6cc',
    'avfilter-11.dll': '9a75810b93ab65662d62c486ee99fd26c56fdbc22ac055512dad2c80321d5dc2',
    'avformat-62.dll': 'b4f8baa89cd2b3e2e5b5366b6b512aa74af7f3770d81d9593070e0b48e7e6dd6',
    'avcodec-62.dll': 'da12863ac22e8bef3501eb7c0eb295519ccbacd26e838ea6dca0304a33461fc1',
    'swresample-6.dll': 'ee48662c8f5bddddf3198b00a405c5c2d020b170cb5fc86ca5032bedbb76857a',
    'swscale-9.dll': '2da2e686648e5e9bddaee0e94ff3aeff3f57cd6e3b143a7d85935820b875043a',
    'avutil-60.dll': 'c505649aacba350808ab507ed98e8fa57da24783f72290804aed86fdb87e712d',
    'zlib.dll': '0582ccf29d374553239ff14a8f77c91c8566a37ae5a3db00af205d654f0421b3',
    'librist.dll': 'e1c751b79ec5704a87758fbadfd2ccf223f96e7fd6e4818bde9002da02afcd75',
    'srt.dll': 'cd28bc7c79c45613cb8d3b707f910c592584823b49ecec5cf3867d253d8cbd57',
    'libx264-164.dll': '83473ef062ccb12679b614b19ba37d0eb8f437352d4b42776f841a67a8f3a549',
}
VC_FILES = ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def prepare(root, archive=None):
    root = Path(root).resolve()
    if archive is None:
        cache = root / 'build/media-dependencies'
        cache.mkdir(parents=True, exist_ok=True)
        archive = cache / ARCHIVE
        if not archive.exists():
            partial = archive.with_suffix('.zip.part')
            with partial.open('xb') as target, urlopen(Request(URL, headers={
                    'User-Agent': 'ThinkAloud-build'}), timeout=60) as response:
                shutil.copyfileobj(response, target, 1024 * 1024)
            if digest(partial) != ARCHIVE_SHA256:
                raise ValueError('Media archive checksum mismatch; partial evidence retained')
            partial.rename(archive)
    archive = Path(archive)
    if digest(archive) != ARCHIVE_SHA256:
        raise ValueError('Media archive differs from pinned official release')
    data, records = {}, []
    with zipfile.ZipFile(archive) as source:
        for name, expected in FILES.items():
            member = 'bin/' + name
            raw = source.read(member)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('Media archive member mismatch: ' + name)
            data[name] = raw
            records.append({'filename': name, 'bytes': len(raw), 'sha256': expected,
                            'source': URL, 'archive_member': member})
    # These same runtime files are already in the verified seed. The child CLI
    # needs its own loader-local copies; it must not depend on a system VC install.
    for name in VC_FILES:
        path = root / 'runtime' / name
        raw = path.read_bytes()
        data[name] = raw
        records.append({'filename': name, 'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'source': 'prepared-seed/runtime/' + name})
    manifest = {'schema': 1, 'version': 'n8.1.2', 'executable': 'ffmpeg.exe',
                'archive': {'url': URL, 'sha256': ARCHIVE_SHA256},
                'recipe_revision': REVISION,
                'ffmpeg_revision': '38b88335f99e76ed89ff3c93f877fdefce736c13',
                'license': 'GPL-3.0-or-later; bundled libraries retain their own terms',
                'files': sorted(records, key=lambda r: r['filename'])}
    data['provenance.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    destination = root / MEDIA_DIRECTORY
    for name, raw in data.items():
        target = destination / name
        if target.exists() and (target.is_symlink() or target.read_bytes() != raw):
            raise ValueError('Existing media runtime differs; choose a fresh stage: ' + str(target))
    destination.mkdir(parents=True, exist_ok=True)
    for name, raw in data.items():
        target = destination / name
        if not target.exists():
            target.write_bytes(raw)
    verify_media(root)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--archive', type=Path, help='Previously downloaded official archive (hash verified)')
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.archive), indent=2))
