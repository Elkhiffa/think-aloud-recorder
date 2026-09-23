import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from media_runtime import MEDIA_DIRECTORY, MEDIA_EXECUTABLE, resolve_ffmpeg, verify_media


class MediaRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_packaged_install_never_falls_back_to_environment_binary(self):
        (self.root / 'portable.json').write_text('{}')
        with patch('imageio_ffmpeg.get_ffmpeg_exe') as fallback:
            with self.assertRaisesRegex(RuntimeError, '音视频处理组件'):
                resolve_ffmpeg(self.root)
            fallback.assert_not_called()

    def test_selected_runtime_is_always_the_isolated_cli(self):
        path = self.root / MEDIA_EXECUTABLE
        path.parent.mkdir(parents=True)
        path.write_bytes(b'fixture')
        with patch('imageio_ffmpeg.get_ffmpeg_exe') as fallback:
            self.assertEqual(resolve_ffmpeg(self.root), str(path))
            fallback.assert_not_called()

    def test_source_worktree_template_can_use_development_dependency(self):
        (self.root / 'portable.json').write_text('{"version":"0.2.0"}')
        (self.root / '.git').write_text('gitdir: synthetic-worktree')
        with patch('imageio_ffmpeg.get_ffmpeg_exe', return_value='development.exe'):
            self.assertEqual(resolve_ffmpeg(self.root), 'development.exe')

    def test_inventory_checks_dlls_and_rejects_unlisted_binaries(self):
        base = self.root / MEDIA_DIRECTORY
        base.mkdir(parents=True)
        records = []
        for name, raw in (('ffmpeg.exe', b'fixture'), ('avcodec-62.dll', b'fixture DLL')):
            (base / name).write_bytes(raw)
            records.append({'filename': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        (base / 'provenance.json').write_text(json.dumps({'schema': 1, 'executable': 'ffmpeg.exe', 'files': records}))
        verify_media(self.root)
        (base / 'unexpected.dll').write_bytes(b'unlisted')
        with self.assertRaisesRegex(ValueError, 'Unlisted'):
            verify_media(self.root)
        (base / 'avcodec-62.dll').write_bytes(b'changed DLL')
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            verify_media(self.root)


if __name__ == '__main__':
    unittest.main()
