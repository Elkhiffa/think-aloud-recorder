"""Prepare the pinned UI font (Sarasa UI SC, hinted, Regular and Bold); no global installation.

Sarasa Gothic publishes the hinted faces only inside TrueType collections. The script reads the two
collections it needs from the official zip with HTTP range requests (about 80 MB of the 414 MB archive),
or from a full local copy given with --archive, checks every input and output against fixed SHA256
values, and writes ui/fonts/*.ttf, the upstream OFL text and tools/fonts/provenance.json.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
from urllib.request import Request, urlopen
import zipfile

VERSION = '1.0.42'
RELEASE = 'https://github.com/be5invis/Sarasa-Gothic/releases/tag/v' + VERSION
ARCHIVE = 'Sarasa-TTC-' + VERSION + '.zip'
ARCHIVE_URL = 'https://github.com/be5invis/Sarasa-Gothic/releases/download/v' + VERSION + '/' + ARCHIVE
ARCHIVE_SHA256 = '23d8eb0e25c2d2a8628a829530763297b8f796d94e2e866df40139770afcbae8'
ARCHIVE_BYTES = 414186575
LICENSE_URL = 'https://raw.githubusercontent.com/be5invis/Sarasa-Gothic/v' + VERSION + '/LICENSE'
LICENSE_SHA256 = '32c932e0dbae4f6e6386964bbc2d04178707665a05ca65cf636241af13d50a53'
COLLECTIONS = {
    'Sarasa-Regular.ttc': 'caf3ec52ba1a8101ffc61317c4ab510b6ea2f24e611a50fd5edcb035107bc07f',
    'Sarasa-Bold.ttc': 'ee826883ccc7d8b37a00f351ac1d2b91ea7dafcc144af5101c2fbfd4aec8d8fd',
}
FACES = {
    'SarasaUiSC-Regular.ttf': ('Sarasa-Regular.ttc', 'Sarasa UI SC',
                               '5e658064c5dee925e15fcffa1c5a640de582fef716d1e0b6544b830785977b91'),
    'SarasaUiSC-Bold.ttf': ('Sarasa-Bold.ttc', 'Sarasa UI SC Bold',
                            '00da18c6059eb349b758be5324ecb0d3c325d5b4f4ad8dda5e6982375b3d3bdb'),
}
HEADERS = {'User-Agent': 'ThinkAloud-build'}


class RemoteFile(io.RawIOBase):
    """A read-only, seekable view of one HTTP resource, fetched in ranges (zipfile reads only what it needs)."""
    BLOCK = 4 * 1024 * 1024

    def __init__(self, url):
        with urlopen(Request(url, headers={**HEADERS, 'Range': 'bytes=0-0'}), timeout=90) as response:
            total = response.headers.get('Content-Range', '').rpartition('/')[2]
            if response.status != 206 or not total.isdigit():
                raise ValueError('The font archive host does not support range requests; use --archive.')
            self.url, self.size = response.geturl(), int(total)
        self.position, self.cache = 0, {}

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        self.position = {io.SEEK_SET: 0, io.SEEK_CUR: self.position, io.SEEK_END: self.size}[whence] + offset
        return self.position

    def block(self, index):
        if index not in self.cache:
            start = index * self.BLOCK
            end = min(start + self.BLOCK, self.size) - 1
            with urlopen(Request(self.url, headers={**HEADERS, 'Range': f'bytes={start}-{end}'}), timeout=90) as response:
                data = response.read()
            if len(data) != end - start + 1:
                raise ValueError('Incomplete range response from the font archive host')
            self.cache = {index: data}  # members are read sequentially; keep one block
        return self.cache[index]

    def read(self, size=-1):
        end = self.size if size is None or size < 0 else min(self.size, self.position + size)
        out = bytearray()
        while self.position < end:
            index, offset = divmod(self.position, self.BLOCK)
            chunk = self.block(index)[offset:offset + end - self.position]
            out += chunk
            self.position += len(chunk)
        return bytes(out)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)


def collections(archive):
    """The two pinned collections, read from a local full archive or remotely by range."""
    if archive:
        if archive.stat().st_size != ARCHIVE_BYTES or sha256_file(archive) != ARCHIVE_SHA256:
            raise ValueError('Font archive differs from the pinned GitHub release: ' + str(archive))
        source = archive.open('rb')
    else:
        source = RemoteFile(ARCHIVE_URL)
        if source.size != ARCHIVE_BYTES:
            raise ValueError('Remote font archive size differs from the pinned GitHub release')
    found = {}
    with source, zipfile.ZipFile(source) as bundle:
        for info in bundle.infolist():
            name = info.filename.rsplit('/', 1)[-1]
            if name in COLLECTIONS:
                data = bundle.read(info)
                if hashlib.sha256(data).hexdigest() != COLLECTIONS[name]:
                    raise ValueError('Font collection differs from the pinned release: ' + name)
                found[name] = data
    missing = set(COLLECTIONS) - set(found)
    if missing:
        raise ValueError('Font archive lacks ' + ', '.join(sorted(missing)))
    return found


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


# ---- One face out of a TrueType collection: the face's own tables, unchanged, in a standalone font. ----
def _tables(data, offset):
    _, count = struct.unpack('>IH', data[offset:offset + 6])
    return {struct.unpack('>4s', data[offset + 12 + 16 * i:offset + 16 + 16 * i])[0]:
            struct.unpack('>III', data[offset + 16 + 16 * i:offset + 28 + 16 * i]) for i in range(count)}


def _full_name(data, offset):
    _, start, _ = _tables(data, offset)[b'name']
    _, count, strings = struct.unpack('>HHH', data[start:start + 6])
    for i in range(count):
        platform, _, language, ident, length, pos = struct.unpack('>6H', data[start + 6 + 12 * i:start + 18 + 12 * i])
        if (platform, language, ident) == (3, 0x409, 4):
            return data[start + strings + pos:start + strings + pos + length].decode('utf-16-be')
    return ''


def _checksum(blob):
    blob += b'\0' * (-len(blob) % 4)
    return sum(struct.unpack(f'>{len(blob) // 4}I', blob)) & 0xFFFFFFFF


def extract_face(collection, name):
    tag, _, count = struct.unpack('>4sII', collection[:12])
    if tag != b'ttcf':
        raise ValueError('Not a TrueType collection')
    offsets = struct.unpack(f'>{count}I', collection[12:12 + 4 * count])
    matches = [offset for offset in offsets if _full_name(collection, offset) == name]
    if len(matches) != 1:
        raise ValueError('Font collection has no single face named ' + name)
    offset = matches[0]
    entries = sorted(_tables(collection, offset).items())
    total = len(entries)
    power = 1 << (total.bit_length() - 1)
    header = struct.pack('>4sHHHH', collection[offset:offset + 4], total, power * 16, power.bit_length() - 1, total * 16 - power * 16)
    directory, body, position, head_at = b'', b'', 12 + 16 * total, 0
    for table, (_, start, length) in entries:
        blob = collection[start:start + length]
        if table == b'head':
            blob = blob[:8] + b'\0\0\0\0' + blob[12:]
            head_at = position + len(body)
        directory += struct.pack('>4sIII', table, _checksum(blob), position + len(body), length)
        body += blob + b'\0' * (-len(blob) % 4)
    font = bytearray(header + directory + body)
    font[head_at + 8:head_at + 12] = struct.pack('>I', (0xB1B0AFBA - _checksum(bytes(font))) & 0xFFFFFFFF)
    return bytes(font)


def write_once(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Existing font file differs; preserve it and choose a fresh root: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def prepare(root, archive=None):
    root = Path(root).resolve()
    license_bytes = urlopen(Request(LICENSE_URL, headers=HEADERS), timeout=90).read()
    if hashlib.sha256(license_bytes).hexdigest() != LICENSE_SHA256:
        raise ValueError('Sarasa Gothic license differs from the pinned release')
    sources = collections(archive)
    fonts = {}
    for filename, (collection, face, digest) in FACES.items():
        font = extract_face(sources[collection], face)
        if hashlib.sha256(font).hexdigest() != digest:
            raise ValueError('Extracted font differs from the pinned result: ' + filename)
        fonts[filename] = font
    for filename, font in fonts.items():
        write_once(root / 'ui/fonts' / filename, font)
    write_once(root / 'licenses/Sarasa-Gothic-OFL.txt', license_bytes)
    provenance = {'version': VERSION, 'release': RELEASE,
                  'archive': {'name': ARCHIVE, 'url': ARCHIVE_URL, 'bytes': ARCHIVE_BYTES, 'sha256': ARCHIVE_SHA256},
                  'license': {'url': LICENSE_URL, 'sha256': LICENSE_SHA256},
                  'fonts': [{'filename': filename, 'collection': collection, 'collection_sha256': COLLECTIONS[collection],
                             'face': face, 'sha256': digest} for filename, (collection, face, digest) in FACES.items()]}
    write_once(root / 'tools/fonts/provenance.json', (json.dumps(provenance, indent=2) + '\n').encode())
    return provenance


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--archive', type=Path, help='a full local copy of ' + ARCHIVE)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.archive), indent=2))
