import json
from pathlib import Path
import tempfile
import unittest

import game_catalog as catalog
from unittest.mock import patch

import context_track
from game_catalog import apply_layout, layout_status


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
            self.assertEqual(layout_status(vault, '燕云十六声'),
                             dict(available=True, catalog=True, enabled=True, current=True))

    def test_status_before_enabling(self):
        # 路径 1：设置 → 游戏 打开时判断能不能显示“启用”。
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(layout_status(Path(tmp), '燕云十六声'),
                             dict(available=True, catalog=False, enabled=False, current=False))
            self.assertFalse(layout_status(Path(tmp), '另一个游戏')['available'])

    def test_rebuild_skips_tracks_built_with_the_current_layout_and_needs_a_layout(self):
        # 路径 1：重建中断后照原命令重跑；还没启用就先提示启用。
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp) / '燕云十六声'
            path = catalog.catalog_path(vault, '燕云十六声')
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(dict(version=1, game='燕云十六声', screens=[]), ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '界面路径识别'):
                context_track.rebuild(vault, progress=lambda line: None)
            apply_layout(vault)
            folder = vault / '场次' / '2026-10-01 第一场'
            folder.mkdir(parents=True)
            (folder / '录像.mp4').write_bytes(b'')
            layout = json.loads(path.read_text(encoding='utf-8'))['layout']
            (folder / 'context-track.json').write_text(json.dumps(dict(layout=layout), ensure_ascii=False), encoding='utf-8')
            with patch('ocr_component.ensure_importable', return_value=True), patch('subprocess.call') as call:
                result = context_track.rebuild(vault, progress=lambda line: None)
            call.assert_not_called()
            self.assertEqual((result['sessions'], result['skipped'], result['failed']), (1, 1, []))

    def test_unknown_game_is_refused_before_anything_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, '没有这个游戏的版式规则'):
                apply_layout(Path(tmp) / '另一个游戏')


if __name__ == '__main__':
    unittest.main()
