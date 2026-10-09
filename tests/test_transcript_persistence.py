"""Synthetic M1 persistence regressions; no recording or real library access."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

import recorder


class TranscriptPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'lib' / '场次' / 'fixture'
        self.folder.mkdir(parents=True)

    def test_permission_error_after_ready_preserves_transcript(self):
        """触发路径：用户录完一场 → 后台整理写完逐字稿并标为可回看 → 杀软/OneDrive/索引器正占用 `独立回看.html` → 替换抛 PermissionError → 已完成的转写被标“失败”，用户点重试又多存一份旧稿并重复转写。"""
        # Expected-behavior successor to review-20261009/repro_findings.py F1.
        meta = dict(id='fixture', game='合成体验', state='可回看', test=True,
                    transcription_state='ready', media=dict(duration=12),
                    settings=dict(transcription_provider='local', model='large-v3'),
                    created='2026-10-09T20:00:00+02:00')
        recorder.write(self.folder / 'session.json', meta)
        recorder.write(self.folder / '录像.whisper.json',
                       dict(segments=[dict(start=2, end=4, text='按钮状态看不懂', speaker_id=0)]))
        (self.folder / '录像.mp4').write_bytes(b'synthetic')
        (self.folder / '复盘.md').write_text('note', encoding='utf-8')
        session = recorder.Session(self.folder)
        generated = {}
        player_attempts = []
        replace = recorder.os.replace

        def fail_player_replace(source, target):
            if Path(target) == self.folder / '独立回看.html':
                self.assertGreater(Path(source).stat().st_size, 0)
                player_attempts.append(Path(source))
                if not generated:
                    generated.update({name: (self.folder / name).read_bytes()
                                      for name in ('录像.whisper.json', '录像.srt', '逐字稿.md')})
                raise PermissionError(32, '另一个程序正在使用此文件', '独立回看.html')
            return replace(source, target)

        with patch.object(recorder.Session, 'adopt_recording', lambda self: None), \
             patch.object(recorder.Session, 'prepare_video', lambda self, progress: None), \
             patch('recorder.run', lambda *args, **kwargs: (self.folder / '口述.flac').write_bytes(b'x')), \
             patch('recorder.microphone_is_silent', lambda path: True), \
             patch('transcription_runtime.profile', lambda settings: dict(provider='local', model='large-v3')), \
             patch('transcription_runtime.resume_profile', lambda path, cache, options, audio: options), \
             patch('speaker_roles.analyze_speakers', lambda path, segments: dict(speakers=[])), \
             patch('recorder.os.replace', side_effect=fail_player_replace), \
             patch('recorder.time.sleep') as sleep:
            session.process()
        self.assertEqual(len(player_attempts), 40)
        self.assertEqual(sleep.call_count, 39)
        saved = recorder.read(self.folder / 'session.json')
        self.assertEqual(saved['state'], '可回看')
        self.assertEqual(saved['transcription_state'], 'ready')
        self.assertTrue(saved['review_page_warning'])
        self.assertIsNone(saved.get('error'))
        self.assertEqual({name: (self.folder / name).read_bytes() for name in generated}, generated)
        self.assertEqual(list(self.folder.glob('*.tmp')), [])

    def test_write_permission_error_removes_temporary_file(self):
        """触发路径：资料库放在同步盘或被杀软长时间锁住 → 40 次重试后仍替换失败 → 每次失败在场次目录留下一个 `.tmp`，越积越多且可能被误当成数据。"""
        with patch('recorder.os.replace', side_effect=PermissionError('文件被占用')) as replace, \
             patch('recorder.time.sleep') as sleep:
            with self.assertRaises(PermissionError):
                recorder.write(self.folder / 'session.json', {'state': '可回看'})
        self.assertEqual(replace.call_count, 40)
        self.assertEqual(sleep.call_count, 39)
        self.assertEqual(list(self.folder.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
