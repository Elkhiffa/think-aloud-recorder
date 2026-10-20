"""Build preparation path: scripts/fetch_fonts.py pulls one face out of a pinned collection and refuses
anything that differs from the pins. Synthetic collections only; no network."""
import hashlib
import io
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from scripts import fetch_fonts


def name_table(full_name):
    text = full_name.encode('utf-16-be')
    return struct.pack('>HHH', 0, 1, 18) + struct.pack('>6H', 3, 1, 0x409, 4, len(text), 0) + text


def collection(faces):
    """A TrueType collection whose faces share one 'glyf' table, like the real ones."""
    shared = b'shared glyph data'
    blobs, directories = [], []
    for full_name in faces:
        directories.append({b'head': b'\0' * 54, b'name': name_table(full_name), b'glyf': shared})
    header_size = 12 + 4 * len(faces)
    dir_size = 12 + 16 * 3
    data_start = header_size + dir_size * len(faces)
    body, offsets, placed = b'', [], {}
    for tables in directories:
        for tag, blob in tables.items():
            if (tag, blob) not in placed:
                placed[(tag, blob)] = data_start + len(body)
                body += blob + b'\0' * (-len(blob) % 4)
    for i, tables in enumerate(directories):
        offsets.append(header_size + dir_size * i)
        directory = struct.pack('>IHHHH', 0x00010000, 3, 32, 1, 16)
        for tag, blob in sorted(tables.items()):
            directory += struct.pack('>4sIII', tag, 0, placed[(tag, blob)], len(blob))
        blobs.append(directory)
    return struct.pack('>4sII', b'ttcf', 0x00010000, len(faces)) + struct.pack(f'>{len(faces)}I', *offsets) + b''.join(blobs) + body


def tables_of(font):
    _, count = struct.unpack('>IH', font[:6])
    out = {}
    for i in range(count):
        tag, _, start, length = struct.unpack('>4sIII', font[12 + 16 * i:28 + 16 * i])
        out[tag] = font[start:start + length]
    return out


class ExtractFaceTests(unittest.TestCase):
    def test_extracts_only_the_named_face_with_its_own_tables(self):
        ttc = collection(['Sarasa Gothic SC', 'Sarasa UI SC'])
        font = fetch_fonts.extract_face(ttc, 'Sarasa UI SC')
        tables = tables_of(font)
        self.assertEqual(sorted(tables), [b'glyf', b'head', b'name'])
        self.assertEqual(tables[b'name'], name_table('Sarasa UI SC'))
        self.assertEqual(tables[b'glyf'], b'shared glyph data')
        # A standalone font: the whole file sums to the OpenType magic once checkSumAdjustment is set.
        self.assertEqual(fetch_fonts._checksum(font), 0xB1B0AFBA)

    def test_unknown_face_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'no single face'):
            fetch_fonts.extract_face(collection(['Sarasa Gothic SC']), 'Sarasa UI SC')


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        regular, bold = collection(['Sarasa UI SC']), collection(['Sarasa UI SC Bold'])
        self.archive = self.base / 'Sarasa-TTC.zip'
        with zipfile.ZipFile(self.archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr('Sarasa-Regular.ttc', regular)
            bundle.writestr('Sarasa-Bold.ttc', bold)
        digest = lambda data: hashlib.sha256(data).hexdigest()
        self.license = b'SIL Open Font License, synthetic copy\n'
        self.pins = {
            'ARCHIVE_SHA256': digest(self.archive.read_bytes()), 'ARCHIVE_BYTES': self.archive.stat().st_size,
            'LICENSE_SHA256': digest(self.license),
            'COLLECTIONS': {'Sarasa-Regular.ttc': digest(regular), 'Sarasa-Bold.ttc': digest(bold)},
            'FACES': {'SarasaUiSC-Regular.ttf': ('Sarasa-Regular.ttc', 'Sarasa UI SC', digest(fetch_fonts.extract_face(regular, 'Sarasa UI SC'))),
                      'SarasaUiSC-Bold.ttf': ('Sarasa-Bold.ttc', 'Sarasa UI SC Bold', digest(fetch_fonts.extract_face(bold, 'Sarasa UI SC Bold')))},
        }

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, root, **changes):
        pins = {**self.pins, **changes}
        with patch.multiple(fetch_fonts, **pins), patch.object(fetch_fonts, 'urlopen', lambda *a, **k: io.BytesIO(self.license)):
            return fetch_fonts.prepare(root, self.archive)

    def test_writes_fonts_license_and_provenance_once(self):
        root = self.base / 'stage'
        provenance = self.prepare(root)
        self.assertEqual(sorted(p.name for p in (root / 'ui/fonts').iterdir()), ['SarasaUiSC-Bold.ttf', 'SarasaUiSC-Regular.ttf'])
        self.assertEqual((root / 'licenses/Sarasa-Gothic-OFL.txt').read_bytes(), self.license)
        self.assertEqual([font['filename'] for font in provenance['fonts']], ['SarasaUiSC-Regular.ttf', 'SarasaUiSC-Bold.ttf'])
        self.prepare(root)  # a repeat over identical files is a no-op
        (root / 'ui/fonts/SarasaUiSC-Bold.ttf').write_bytes(b'someone else\'s font')
        with self.assertRaisesRegex(ValueError, 'Existing font file differs'):
            self.prepare(root)

    def test_any_differing_input_is_refused_before_writing(self):
        root = self.base / 'stage'
        with self.assertRaisesRegex(ValueError, 'archive differs'):
            self.prepare(root, ARCHIVE_SHA256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'collection differs'):
            self.prepare(root, COLLECTIONS={'Sarasa-Regular.ttc': '0' * 64, 'Sarasa-Bold.ttc': self.pins['COLLECTIONS']['Sarasa-Bold.ttc']})
        with self.assertRaisesRegex(ValueError, 'license differs'):
            self.prepare(root, LICENSE_SHA256='0' * 64)
        self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
