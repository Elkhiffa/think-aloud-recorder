"""Prepare the pinned portable SDL2 controller runtime; no global installation."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import Request, urlopen
import zipfile

VERSION = '2.32.10'
BASE = 'https://github.com/libsdl-org/SDL/releases/download/release-' + VERSION + '/'
ASSETS = {
    'SDL2-2.32.10-win32-x64.zip': '6cf9706eefd0a4a06dc764007934d428afaf029fabdd408a9e646048c91e18fb',
    'SDL2-2.32.10.tar.gz': '5f5993c530f084535c65a6879e9b26ad441169b3e25d789d83287040a9ca5165',
}


def verified_asset(cache, name):
    path = cache / name
    data = path.read_bytes() if path.is_file() else urlopen(Request(BASE + name, headers={'User-Agent': 'ThinkAloud-build'}), timeout=90).read()
    if hashlib.sha256(data).hexdigest() != ASSETS[name]:
        raise ValueError('SDL2 asset checksum differs from the pinned GitHub release: ' + name)
    if not path.exists():
        path.write_bytes(data)
    return data


def write_once(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Existing dependency differs; preserve it and choose a fresh root: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def prepare(root):
    root = Path(root).resolve()
    cache = root / 'build/input-dependencies'
    cache.mkdir(parents=True, exist_ok=True)
    binary_name, source_name = ASSETS
    with zipfile.ZipFile(io.BytesIO(verified_asset(cache, binary_name))) as archive:
        dll = archive.read('SDL2.dll')
    if dll[:2] != b'MZ':
        raise ValueError('SDL2 runtime is not a Windows binary')
    pe = int.from_bytes(dll[60:64], 'little')
    if dll[pe:pe + 6] != b'PE\0\0\x64\x86':
        raise ValueError('SDL2 runtime must be x64')
    with tarfile.open(fileobj=io.BytesIO(verified_asset(cache, source_name)), mode='r:gz') as source:
        member = source.getmember('SDL2-' + VERSION + '/LICENSE.txt')
        if not member.isfile() or member.size > 10000:
            raise ValueError('Unexpected SDL2 license entry')
        license_bytes = source.extractfile(member).read()
    write_once(root / 'tools/input/SDL2.dll', dll)
    write_once(root / 'licenses/SDL2-zlib.txt', license_bytes)
    provenance = {'version': VERSION, 'release': 'https://github.com/libsdl-org/SDL/releases/tag/release-' + VERSION,
                  'dll_sha256': hashlib.sha256(dll).hexdigest(),
                  'assets': [{'name': name, 'url': BASE + name, 'sha256': digest} for name, digest in ASSETS.items()]}
    write_once(root / 'tools/input/provenance.json', (json.dumps(provenance, indent=2) + '\n').encode())
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(prepare(parser.parse_args().root), indent=2))
