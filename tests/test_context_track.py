"""Synthetic OCR/frames only; no model, private source, or video decoder needed."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

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

    def test_watermark_extracted_and_original_text_retained(self):
        """触发路径：用户要把某段问题连同 UID 和客户端时间发给 QA/程序 → context-read 必须能直接给出。"""
        source = 'ID:0156936254 0929 15:16'
        _, track = self.build([[row(source, x=750, y=500)],
                               [row('ID:0156936254 0929 15:17', x=750, y=500)],
                               [row('ID:0156936254 0929 15:18', x=750, y=500)]],
                              times=[2.5, 7.5, 62.5])
        self.assertEqual(track['watermark'], dict(uid='0156936254', client_time=[
            dict(t=2.5, text='0929 15:16'), dict(t=62.5, text='0929 15:18')]))
        self.assertEqual(track['frames'][0]['items'], [[800.0, 510.0, source]])
        read = context.read_track(self.folder)
        self.assertEqual(read['frames'][0]['text'], source)
        self.assertEqual(read['watermark'], track['watermark'])

    def test_joined_uid_date_and_time_are_split(self):
        """触发路径：用户要把问题连同 UID 和客户端时间发给 QA → 不同分辨率或字体下 OCR 把 UID、日期、时间连成一串 → UID 被识别成 16 位且取不到时间。"""
        source = 'ID:0156936254092916:28'
        _, track = self.build([[row(source, x=750, y=500)]])
        self.assertEqual(track['watermark'], dict(uid='0156936254', client_time=[
            dict(t=2.5, text='0929 16:28')]))
        self.assertEqual(track['frames'][0]['items'][0][2], source)

    def test_low_confidence_text_is_discarded(self):
        """触发路径：3D 场景、粒子特效被 OCR 成大量乱码 → 情景文字被噪声淹没，agent 读到错误界面。"""
        _, track = self.build([[row('粒子乱码', .59), row('道具', .6)]])
        self.assertEqual([item[2] for item in track['frames'][0]['items']], ['道具'])
        self.assertIsNone(track['watermark'])
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


if __name__ == '__main__':
    unittest.main()
