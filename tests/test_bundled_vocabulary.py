"""Bundled defaults are real files, not personal dictionaries or mutable presets."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hotword_files import (BUNDLED_DICTIONARY, bundled_dictionary_snapshots,
                           compile_hotword_snapshots, read_words)

ROOT = Path(__file__).resolve().parents[1]


class BundledVocabularyTests(unittest.TestCase):
    def test_shipped_terms_cover_uiux_and_fit_both_transcription_providers(self):
        words = read_words(ROOT / BUNDLED_DICTIONARY, qwen=True)
        self.assertGreaterEqual(len(words), 80)
        self.assertLessEqual(len(words), 180)
        self.assertEqual(len(words), len(set(words)))
        self.assertTrue({'UI', 'UX', '心智模型', '认知负荷', '下拉菜单', '焦点',
                         '禁用状态', '操作反馈', '技能冷却'}.issubset(words))
        files = bundled_dictionary_snapshots(ROOT)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]['name'], BUNDLED_DICTIONARY.name)
        self.assertEqual(compile_hotword_snapshots(files, '', qwen=True)['hotwords'], '\n'.join(words))
        self.assertEqual(set(files[0]), {'id', 'name', 'words'})

    def test_only_bundled_file_is_used_and_each_read_has_its_own_words(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / BUNDLED_DICTIONARY
            path.parent.mkdir()
            path.write_bytes((ROOT / BUNDLED_DICTIONARY).read_bytes())
            (path.parent / 'personal.txt').write_text('私人项目名', encoding='utf-8')
            first = bundled_dictionary_snapshots(directory)
            original = first[0]['words'][:]
            first[0]['words'].append('修改快照')
            self.assertEqual(bundled_dictionary_snapshots(directory)[0]['words'], original)
            self.assertNotIn('私人项目名', original)

    def test_missing_or_invalid_bundle_has_no_fabricated_defaults(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(bundled_dictionary_snapshots(directory), [])
            path = Path(directory) / BUNDLED_DICTIONARY
            path.parent.mkdir()
            for content in ('', '# 仅说明', '过' * 16, '坏\x00词'):
                path.write_text(content, encoding='utf-8')
                self.assertEqual(bundled_dictionary_snapshots(directory), [])


if __name__ == '__main__':
    unittest.main()
