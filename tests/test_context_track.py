"""Synthetic OCR/frames only; no model, private source, or video decoder needed."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

import context_track as context


def row(text, confidence=.9, x=20, y=20):
    return [[[x, y], [x + 100, y], [x + 100, y + 20], [x, y + 20]],
            text, confidence]


class ContextTrackTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / '场次' / 'session'
        self.folder.mkdir(parents=True)
        (self.folder / 'session.json').write_text(
            json.dumps(dict(game='合成游戏'), ensure_ascii=False), encoding='utf-8')
        (self.folder / '录像.mp4').write_bytes(b'synthetic-video')
        self.image = SimpleNamespace(shape=(540, 960, 3))

    def build(self, results, times=None, **options):
        times = times or [2.5 + 5 * i for i in range(len(results))]
        engine = Mock(side_effect=[(result, None) for result in results])
        with patch.object(context, '_ocr_engine', return_value=engine), patch.object(
                context, '_sample_frames', return_value=[(at, self.image) for at in times]):
            summary = context.build(self.folder, **options)
        return summary, context.load_track(self.folder, output=options.get('output'))

    def test_low_confidence_text_is_discarded(self):
        """触发路径：3D 场景、粒子特效被 OCR 成大量乱码 → 情景文字被噪声淹没，agent 读到错误界面。"""
        _, track = self.build([[row('粒子乱码', .59), row('道具', .6)]])
        self.assertEqual([item[2] for item in track['frames'][0]['items']], ['道具'])
        self.assertEqual(track['screens'], [dict(start=2.5, end=2.5, screen=None, source='ocr')])

    def test_compact_merges_adjacent_title_prefixes(self):
        """触发路径：在同一界面停留十几分钟 → 上百帧重复文本塞满 agent 上下文。"""
        self.build([[row('背包道具普通道具养成材料甲'), row('长文本' * 60, y=200)],
                    [row('背包道具普通道具养成材料乙')], [row('任务')]])
        frames = context.read_track(self.folder, compact=True)['frames']
        self.assertEqual(len(frames), 2)
        self.assertEqual((frames[0]['t'], frames[0]['end']), (2.5, 7.5))
        self.assertLessEqual(len(frames[0]['text']), 120)
        self.assertEqual(frames[1]['text'], '任务')

    def test_existing_matching_track_is_reused(self):
        """触发路径：agent 或用户对同一场次再次运行 context-build → 不应重新 OCR 数分钟。"""
        output = Path(self.temp.name) / 'output'
        self.build([[row('道具')]], interval=5, start=0, end=10, output=output)
        with patch.object(context, '_ocr_engine') as engine, patch.object(
                context, '_sample_frames') as samples:
            reused = context.build(self.folder, interval=5, start=0, end=10, output=output)
        self.assertTrue(reused['reused'])
        engine.assert_not_called()
        samples.assert_not_called()
        changed, track = self.build([[row('新范围')]], times=[12.5], interval=5,
                                    start=10, end=20, output=output)
        self.assertFalse(changed['reused'])
        self.assertEqual((track['start'], track['end']), (10, 20))
        self.assertFalse((self.folder / context.TRACK).exists())

    def test_retranscription_does_not_invalidate_track(self):
        """触发路径：用户重新转写 → 录像.mp4 未变 → 情景轨道仍然有效。"""
        _, track = self.build([[row('道具')]])
        (self.folder / '录像.whisper.json').write_text(
            json.dumps(dict(segments=[dict(start=0, end=1, text='重新转写')])), encoding='utf-8')
        with patch.object(context, '_ocr_engine') as engine:
            summary = context.build(self.folder)
        self.assertTrue(summary['reused'])
        engine.assert_not_called()
        self.assertEqual(context.load_track(self.folder), track)

    def test_rematch_does_not_call_ocr(self):
        """触发路径：用户录了 20 场后修订目录 → 只重算界面分段，不应重跑几小时 OCR。"""
        catalog_path = Path(self.temp.name) / 'game-assets' / '合成游戏' / 'catalog.json'
        catalog_path.parent.mkdir(parents=True)
        catalog = dict(version=1, game='合成游戏', screens=[dict(
            id='bag', name='背包', source='manual', elements=[],
            match=dict(all_of=['道具'], any_of=[], none_of=[]))])
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
        _, before = self.build([[row('道具')], [row('道具')]], times=[12.5, 17.5],
                               interval=5, start=10, end=20)
        self.assertEqual(before['screens'], [dict(start=12.5, end=17.5, screen='bag', source='ocr')])
        catalog['screens'][0].update(id='bag.items', engine_id='inventory.items')
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')
        with patch.object(context, '_ocr_engine') as engine, patch.object(
                context, '_sample_frames') as samples:
            cached = context.build(self.folder, interval=5, start=10, end=20)
            self.assertTrue(cached['reused'])
            self.assertEqual(context.load_track(self.folder)['screens'], before['screens'])
            summary = context.build(self.folder, rematch=True)
        engine.assert_not_called()
        samples.assert_not_called()
        self.assertTrue(summary['rematched'])
        after = context.load_track(self.folder)
        self.assertEqual(after['screens'], [dict(start=12.5, end=17.5, screen='bag.items',
                                                 source='ocr', engine_id='inventory.items')])
        self.assertEqual({key: value for key, value in after.items() if key != 'screens'},
                         {key: value for key, value in before.items() if key != 'screens'})
        self.assertEqual((summary['interval'], summary['start'], summary['end']), (5, 10, 20))


    def write_catalog(self, regions=None):
        catalog = dict(version=1, game='合成游戏', screens=[
            dict(id='bag.items', name='背包·道具', source='manual', elements=[],
                 match=dict(all_of=['仓库'], any_of=[], none_of=[], title_any_of=['道具'])),
            dict(id='world', name='大世界', source='manual', elements=[],
                 match=dict(all_of=['世界'], any_of=[], none_of=[]))])
        if regions is not None:
            catalog['title_regions'] = regions
        path = Path(self.temp.name) / 'game-assets' / '合成游戏' / 'catalog.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')

    def build_layers(self, full_results, title_results, frames, **options):
        full_engine = Mock(side_effect=[(result, None) for result in full_results])
        title_engine = Mock(side_effect=[(result, None) for result in title_results])
        with patch.object(context, '_ocr_engine', side_effect=lambda title=False: (
                title_engine if title else full_engine)), patch.object(
                context, '_sample_frames', return_value=frames):
            summary = context.build(self.folder, **options)
        return summary, context.load_track(self.folder), full_engine, title_engine

    def test_title_regions_alone_identify_screen_without_full_ocr(self):
        """触发路径：用户对 1 小时场次运行 context-build → 按 2 秒一帧做整屏 OCR 要几十分钟 → 只识别标题区才能做到密集锚定。"""
        self.write_catalog([dict(id='screen_top_left', rect=[0, 0, .32, .11])])
        image = np.zeros((540, 960, 3), np.uint8)
        summary, track, full, title = self.build_layers(
            [[row('世界')], [row('道具'), row('自动使用道具', y=200)]],
            [[], [row('道具')], [row('道具')], [row('道具')], [row('任务')]],
            [(at, image) for at in (1, 3, 5, 7, 9)],
            title_interval=2, full_interval=6, start=0, end=10)
        self.assertEqual(full.call_count, 2)
        self.assertEqual(title.call_count, 5)
        self.assertEqual(title.call_args.args[0].shape, (59, 307, 3))
        self.assertEqual((track['version'], track['interval'], track['full_interval']), (2, 2, 6))
        self.assertEqual((summary['title_interval'], summary['full_interval']), (2, 6))
        self.assertEqual([sorted(frame) for frame in track['frames']],
                         [['items', 't', 'titles'], ['t', 'titles'], ['t', 'titles'],
                          ['items', 't', 'titles'], ['t', 'titles']])
        self.assertEqual(track['frames'][0], dict(t=1, titles=[], items=[[70.0, 30.0, '世界']]))
        self.assertEqual(track['frames'][1], dict(t=3, titles=[dict(
            region='screen_top_left', text='道具', x=0)]))
        self.assertEqual(track['screens'], [
            dict(start=1, end=1, screen='world', source='ocr'),
            dict(start=3, end=7, screen='bag.items', source='ocr')])
        compact = context.read_track(self.folder, compact=True)['frames']
        self.assertEqual([(row['t'], row['end'], row['text']) for row in compact],
                         [(1, 1, '世界'), (3, 7, '道具\n自动使用道具'), (9, 9, '任务')])

    def test_vertical_edge_follows_panel_width(self):
        """触发路径：用户在不同页面间切换 → 右侧面板宽度不同 → 固定坐标会切到场景或别的文字。"""
        self.write_catalog([dict(id='right_panel_top_left', rect=[.5, 0, .18, .11],
                                 detect=dict(type='vertical_edge', x_range=[.5, .85]))])
        noise = np.random.default_rng(7)

        def screen(edge):
            # 暗场景与半透明面板只差 6 级灰度；面板内道具格竖线更亮但只覆盖一半行。
            image = noise.integers(17, 24, (540, 960, 3)).astype(np.uint8)
            if edge is not None:
                image[:, edge:] += 6
            for left in range(edge or 700, 940, 60):
                image[130:400, left + 10:left + 50] = 200
            return image

        _, track, _, title = self.build_layers(
            [[], [], []], [[row('道具')], [row('培养')], [row('场景')]],
            [(1, screen(640)), (11, screen(700)), (21, screen(None))],
            title_interval=10, full_interval=10, start=0, end=30)
        self.assertEqual([frame['titles'][0]['x'] for frame in track['frames']],
                         [round(640 / 960, 4), round(700 / 960, 4), .5])
        crops = [call.args[0] for call in title.call_args_list]
        self.assertEqual([crop.shape for crop in crops], [(59, 173, 3)] * 3)
        self.assertTrue(all(crop[:, 0].mean() > 22 for crop in crops[:2]))

    def test_catalog_without_title_regions_stays_single_layer(self):
        """触发路径：用户升级后对已有 v1 目录的场次运行 context-build → 目录没有 title_regions → 应保持原单层行为与 version 1 轨道。"""
        self.write_catalog()
        summary, track, full, title = self.build_layers(
            [[row('仓库')], [row('世界')]], [], [(2.5, self.image), (7.5, self.image)],
            interval=5, title_interval=2, full_interval=10)
        title.assert_not_called()
        self.assertEqual(full.call_count, 2)
        self.assertEqual(track['version'], 1)
        self.assertNotIn('full_interval', track)
        self.assertEqual(summary['interval'], 5)
        self.assertEqual([sorted(frame) for frame in track['frames']], [['items', 't']] * 2)
        self.assertEqual([span['screen'] for span in track['screens']], ['bag.items', 'world'])


if __name__ == '__main__':
    unittest.main()
