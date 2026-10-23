import json
from pathlib import Path
import tempfile
import unittest

import game_catalog as catalog
from scripts.apply_layout import apply_layout


class ApplyLayoutTests(unittest.TestCase):
    def test_writes_the_game_layout_once_and_keeps_the_old_catalog(self):
        # 触发路径：用户在另一台电脑的资料库启用界面路径识别 → 运行 apply_layout → 目录带上燕云版式规则，旧目录留底。
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / '燕云十六声'
            path = catalog.catalog_path(vault, '燕云十六声')
            path.parent.mkdir(parents=True)
            original = dict(version=1, game='燕云十六声', screens=[
                dict(id='背包/道具', name='背包·道具', source='manual', match=dict(all_of=['背包'], any_of=[], none_of=[]), elements=[])])
            path.write_text(json.dumps(original, ensure_ascii=False), encoding='utf-8')
            self.assertFalse(apply_layout(vault, dry_run=True)['replaced'])
            self.assertNotIn('layout', json.loads(path.read_text(encoding='utf-8')))
            report = apply_layout(vault)
            written = json.loads(path.read_text(encoding='utf-8'))
            reference = json.loads((Path(__file__).resolve().parents[1] / 'docs/layouts/燕云十六声.json').read_text(encoding='utf-8'))
            self.assertEqual(written['layout'], reference)
            self.assertEqual(written['screens'], original['screens'])
            self.assertEqual(json.loads(Path(report['backup']).read_text(encoding='utf-8')), original)
            self.assertTrue(apply_layout(vault)['unchanged'])
            self.assertEqual(len(list(path.parent.glob('catalog.json.before-layout-*'))), 1)

    def test_unknown_game_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, '没有这个游戏的版式规则'):
                apply_layout(Path(tmp) / '另一个游戏')


if __name__ == '__main__':
    unittest.main()
