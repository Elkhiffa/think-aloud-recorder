"""Synthetic session files exercise real rendering and the restricted viewer API."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import recorder
from review_runtime import ReviewAPI, prepare_window, render_player, review_payload


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / '合成 资料库' / '场次' / 'synthetic'
        self.folder.mkdir(parents=True)
        self.meta = dict(id='synthetic', game='合成测试 <script> %%CSS%%', state='可回看', test=True)
        self.segments = [dict(start=0, end=5, text='测试 </script><script>alert(1)</script>'),
                         dict(start=15, end=20, text='第二段测试原话')]
        recorder.write(self.folder / 'session.json', self.meta)
        recorder.write(self.folder / '录像.whisper.json', {'segments': self.segments})
        (self.folder / '录像.mp4').write_bytes(b'synthetic placeholder, never claimed playable')
        (self.folder / '独立回看.html').write_text('old immutable review', encoding='utf-8')
        (self.folder / '复盘.md').write_text('user note sentinel', encoding='utf-8')

    def test_old_session_uses_new_renderer_without_rewriting_notes_or_transcript(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        # Application templates are real; only the temporary page directory is isolated.
        with patch('review_runtime.render_player', wraps=lambda root, payload: render_player(recorder.ROOT, payload)):
            page, payload = prepare_window(self.root, recorder.Session(self.folder))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir() if p.name != '.processing.lock'})
        self.assertTrue(page.is_relative_to(self.root / 'state/reviews'))
        self.assertTrue(payload['video'].startswith('file:///'))
        self.assertIn('%20', payload['video'])
        html = page.read_text(encoding='utf-8')
        self.assertIn('new Plyr', html)
        self.assertIn('合成测试 &lt;script&gt; %%CSS%%', html)
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('\\u003c/script>', html)

    def test_export_refreshes_player_and_contains_no_absolute_desktop_paths(self):
        archive = recorder.Session(self.folder).package()
        with zipfile.ZipFile(archive) as bundle:
            page = bundle.read('场次/synthetic/独立回看.html').decode('utf-8')
            self.assertIn('seekTime:15', page)
            self.assertNotIn(str(self.root), page)
            self.assertNotIn(self.folder.as_uri(), page)
            self.assertIn('Permission is hereby granted', page)
            self.assertFalse(any(name.startswith('.obsidian/') for name in bundle.namelist()))
        self.assertEqual((self.folder / '独立回看.html').read_text(encoding='utf-8'), 'old immutable review')

    def test_viewer_commands_remain_bound_to_original_session(self):
        api = ReviewAPI(self.folder, {})
        with patch('review_runtime.os.startfile') as start, patch('review_runtime.copy_text') as copy:
            self.assertTrue(api.open_folder()['ok'])
            start.assert_called_once_with(self.folder.resolve())
            self.assertTrue(api.copy_path('video')['ok'])
            copy.assert_called_once_with(str((self.folder / '录像.mp4').resolve()))
            self.assertFalse(api.copy_path('../outside')['ok'])
            self.assertFalse(api.open_document('../outside')['ok'])
            self.assertTrue(api.open_document('notes')['ok'])
        self.assertEqual({name for name in dir(api) if not name.startswith('_')},
                         {'ready', 'open_folder', 'copy_path', 'open_document', 'get_layout', 'save_layout'})

    def test_layout_preferences_merge_between_windows_without_changing_session(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        preferences = self.root / 'state/review-layout.json'
        first = ReviewAPI(self.folder, {}, preferences)
        second = ReviewAPI(self.folder, {}, preferences)
        self.assertEqual(first.get_layout()['data'], {})
        self.assertTrue(first.save_layout('columns', .7)['ok'])
        self.assertTrue(second.save_layout('rows', .45)['ok'])
        reopened = ReviewAPI(self.folder, {}, preferences)
        self.assertEqual(reopened.get_layout()['data'], {'columns': .7, 'rows': .45})
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})
        for axis, value in [('columns', float('nan')), ('rows', True), ('rows', .99), ('../config', .5)]:
            self.assertFalse(first.save_layout(axis, value)['ok'])
        self.assertEqual(reopened.get_layout()['data'], {'columns': .7, 'rows': .45})

    def test_corrupt_layout_preferences_do_not_block_review(self):
        preferences = self.root / 'layout.json'
        api = ReviewAPI(self.folder, {}, preferences)
        for content in ('invalid JSON', '[]', '{"columns":false,"rows":0.6,"other":0.2}'):
            preferences.write_text(content, encoding='utf-8')
            self.assertEqual(api.get_layout()['data'], {'rows': .6} if 'rows' in content else {})
        self.assertTrue(api.save_layout('columns', .5)['ok'])
        self.assertEqual(api.get_layout()['data'], {'columns': .5, 'rows': .6})

    def test_invalid_timestamps_fail_before_display(self):
        for start, end in [(float('nan'), 2), (-1, 2), (3, 2), (0, float('inf'))]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                review_payload(self.folder, self.meta, [{'start': start, 'end': end}])


if __name__ == '__main__':
    unittest.main()
