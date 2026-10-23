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
                context, '_sample_frames', return_value=[(at, self.image, self.image) for at in times]):
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
                context, '_sample_frames', return_value=[(at, image, image) for at, image in frames]):
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
        self.assertEqual(track['frames'][0], dict(t=1, titles=[], items=[
            [70.0, 30.0, '世界', [[20, 20], [120, 20], [120, 40], [20, 40]]]]))
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


GREY, GOLD = (170, 170, 170), (90, 160, 200)   # BGR：灰白未激活字、金色激活字
RULES = dict(gold=dict(min_b=12, min_s=.25), top_max_y=.1, text_bands=[[.12, .26]])
LAYOUT = dict(tabs=RULES)


def tab_frame(rows):
    """A 960x540 dark frame plus its OCR result; rows are (top y, [(text, colour), ...])."""
    image = np.full((540, 960, 3), 20, np.uint8)
    result = []
    for y, tabs in rows:
        for index, (text, colour) in enumerate(tabs):
            x = 100 + 70 * index
            image[y:y + 16, x:x + 40:2] = colour
            result.append([[[x, y], [x + 40, y], [x + 40, y + 16], [x, y + 16]], text, .9])
    return image, result


class ActiveTabTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.folder = root / '场次' / 'session'
        self.folder.mkdir(parents=True)
        (self.folder / 'session.json').write_text(
            json.dumps(dict(game='合成游戏'), ensure_ascii=False), encoding='utf-8')
        (self.folder / '录像.mp4').write_bytes(b'synthetic-video')
        self.catalog = root / 'game-assets' / '合成游戏' / 'catalog.json'
        self.catalog.parent.mkdir(parents=True)
        self.write_rules(LAYOUT)

    def write_rules(self, rules):
        catalog = dict(version=1, game='合成游戏', screens=[])
        if rules is not None:
            catalog['layout'] = rules
        self.catalog.write_text(json.dumps(catalog, ensure_ascii=False), encoding='utf-8')

    def build(self, frames, ocr=True):
        """frames: (960-wide image, OCR result) or (960-wide image, OCR result, source-size image)."""
        engine = Mock(side_effect=[(frame[1], None) for frame in frames])
        samples = [(2.5 + 5 * index, frame[0], frame[-1] if len(frame) == 3 else frame[0])
                   for index, frame in enumerate(frames)]
        with patch.object(context, '_ocr_engine', return_value=engine), patch.object(
                context, '_sample_frames', return_value=samples):
            summary = context.build(self.folder)
        self.assertEqual(engine.called, ocr)
        return summary, context.load_track(self.folder)

    def shop(self):
        return tab_frame([
            (20, [('背包', GREY), ('商店', GOLD), ('任务', GREY)]),
            (90, [('精选', GOLD), ('月卡', GREY)]),
            (130, [('外观', GOLD), ('和鸣', GOLD), ('福利', GREY)]),
            (340, [('简介', GREY), ('教学', GOLD)]),
            (490, [('前往', GREY), ('开始匹配', GOLD)])])

    def test_gold_tab_reported_only_on_top_and_text_band_rows(self):
        """触发路径：agent 对燕云场次运行 context-build，目录有 layout.tabs → 顶部和横向页签报出亮着的那个；底部金色按钮、两个金色的推广字不报，否则时间线满是“激活：开始匹配”。"""
        _, track = self.build([self.shop()])
        frame = track['frames'][0]
        self.assertEqual(frame['tabs'], [
            dict(kind='top', active='商店', row=['背包', '商店', '任务'], level=1),
            dict(kind='text', active='精选', row=['精选', '月卡'], level=2)])
        self.assertEqual(len(frame['items'][0]), 4)
        self.assertEqual(track['layout'], LAYOUT)
        read = context.read_track(self.folder)['frames'][0]
        self.assertEqual(read['tabs'], frame['tabs'])
        self.assertEqual({len(item) for item in read['items']}, {3})

    def test_declared_text_row_outside_band_is_reported(self):
        """触发路径：用户在目录 layout.tabs.groups 声明某界面不在高度带内的横向页签 → context-build 应报出它，未声明的带外金色字仍不报。"""
        self.write_rules(dict(tabs=dict(RULES, groups=[dict(screen='流派指引/流派推荐', tabs=['简介', '教学'])])))
        _, track = self.build([self.shop()])
        self.assertIn('教学', [tab['active'] for tab in track['frames'][0]['tabs'] if tab['kind'] == 'group'])
        self.assertNotIn('开始匹配', [tab['active'] for tab in track['frames'][0]['tabs']])

    def test_rule_change_recomputes_tabs_without_ocr(self):
        """触发路径：用户调整目录 layout 门槛后对已建轨道的场次再运行 context-build → 字框已在轨道里，只应重新取色，不应重跑几十分钟 OCR。"""
        self.build([self.shop()])
        self.write_rules(dict(tabs=dict(RULES, text_bands=[])))
        summary, track = self.build([self.shop()], ocr=False)
        self.assertTrue(summary['recomputed'])
        self.assertEqual([tab['active'] for tab in track['frames'][0]['tabs']], ['商店'])
        self.assertEqual(track['layout']['tabs']['text_bands'], [])

    def test_old_track_without_corners_is_rebuilt(self):
        """触发路径：用户升级后在目录里加上 layout，对已有场次运行 context-build → 旧轨道只有中心点、算不了字色 → 应整段重跑并补上字框和页签。"""
        self.write_rules(None)
        _, old = self.build([self.shop()])
        for item in old['frames'][0]['items']:
            del item[3]
        (self.folder / context.TRACK).write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8')
        self.write_rules(LAYOUT)
        summary, track = self.build([self.shop()])
        self.assertFalse(summary['reused'])
        self.assertEqual(track['frames'][0]['tabs'][0]['active'], '商店')

    def test_compact_splits_when_active_tab_changes(self):
        """触发路径：agent 运行 context-read --compact → 同一标题下从“商店”切到“任务”是换了界面，应分成两段；规则沉默的帧不算切换。"""
        top = lambda active: tab_frame([(20, [(text, GOLD if text == active else GREY)
                                              for text in ('背包', '商店', '任务')])])
        silent = tab_frame([(20, [('背包', GREY), ('商店', GREY), ('任务', GREY)])])
        self.build([top('商店'), silent, top('商店'), top('任务')])
        frames = context.read_track(self.folder, compact=True)['frames']
        self.assertEqual([(row['t'], row['end'], row.get('tabs')) for row in frames],
                         [(2.5, 12.5, ['商店']), (17.5, 17.5, ['任务'])])

    HEADINGS = dict(main=dict(margin=[.04, .16], y=[.045, .085], height=[.033, .055]),
                    side=dict(y=[.055, .085], min_height=.043), icon_tabs=['道具', '培养', '任务'])

    def menu(self, side_title='选择心法', name_card=False, gold_tab=False):
        """Page title, a side panel (edge at x=600) with its title and a tooltip name without a panel edge;
        or a name card whose ID line sits right under the name; or a gold tab at the page-title position.
        Texts are kept > 7 heights apart so none of them chain into a tab row."""
        image = np.full((540, 960, 3), 20, np.uint8)
        image[:, 600:] = 60
        result = []

        def text(x, y, w, h, word, colour):
            image[y:y + h, x:x + w:2] = colour
            result.append([[[x, y], [x + w, y], [x + w, y + h], [x, y + h]], word, .9])
        white = (230, 230, 230)
        if name_card:
            text(610, 24, 72, 24, '余澄宇', white)
            text(610, 52, 120, 12, '角色编号', white)
            return image, result
        if gold_tab:
            text(50, 22, 40, 20, '装备', GOLD)
            return image, result
        text(50, 22, 40, 20, '心法', white)
        text(610, 26, 96, 24, side_title, white)
        text(330, 26, 96, 24, '鹿仙玉佩', white)
        return image, result

    def test_page_and_side_titles_reported(self):
        """触发路径：agent 对菜单场次运行 context-build，目录有 layout.headings → 记下左上页面标题和右侧面板标题；亮着的金字页签、没有面板边缘的浮窗物品名、下面紧跟角色编号的名字不算标题。"""
        self.write_rules(dict(LAYOUT, headings=self.HEADINGS))
        _, track = self.build([self.menu(), self.menu(name_card=True), self.menu(gold_tab=True)])
        self.assertEqual(track['frames'][0]['headings'], dict(main='心法', side=['选择心法']))
        self.assertNotIn('headings', track['frames'][1])
        self.assertNotIn('headings', track['frames'][2])
        self.assertEqual(context.read_track(self.folder, compact=True)['frames'][0]['headings'],
                         ['心法', '选择心法'])

    def test_bag_title_is_the_active_icon_tab(self):
        """触发路径：用户在背包里切图标页签，识别把标题左边的背包图标读成一个字（简培养）→ 侧窗标题应还原为“培养”，并记成亮着的一级图标页签。"""
        self.write_rules(dict(LAYOUT, headings=self.HEADINGS))
        _, track = self.build([self.menu(side_title='简培养')])
        frame = track['frames'][0]
        self.assertEqual(frame['headings']['side'], ['培养'])
        self.assertEqual(frame['tabs'][0], dict(kind='icon', active='培养', row=['培养'], level=1))

    def test_focus_frame_needs_its_triangle(self):
        """触发路径：agent 对手柄操作的场次运行 context-build，目录有 layout.focus → 记下带顶部小三角的金色焦点框和框里的字；没有小三角的金色品质边框不算焦点。"""
        import cv2
        full = np.full((1080, 1920, 3), 20, np.uint8)
        gold = (60, 170, 230)                                   # BGR，色相约 38°
        cv2.rectangle(full, (600, 400), (760, 560), gold, 4)
        cv2.fillPoly(full, [np.array([[672, 390], [688, 390], [680, 399]])], gold)
        cv2.rectangle(full, (1000, 380), (1220, 580), gold, 4)  # 更大的品质边框，没有小三角
        image = cv2.resize(full, (960, 540), interpolation=cv2.INTER_AREA)
        result = [[[[320, 250], [360, 250], [360, 266], [320, 266]], '铃铛', .9]]
        self.write_rules(dict(LAYOUT, focus=dict(hue=[26, 44], min_s=.31, levels=[.59, .35])))
        _, track = self.build([(image, result, full), (np.full((540, 960, 3), 20, np.uint8), [])])
        self.assertEqual(track['frames'][0]['focus']['text'], '铃铛')
        x0, y0, x1, y1 = track['frames'][0]['focus']['box']
        self.assertTrue(295 <= x0 <= 305 and 375 <= x1 <= 385)
        self.assertNotIn('focus', track['frames'][1])
        self.assertEqual(context.read_track(self.folder)['frames'][0]['focus'], track['frames'][0]['focus'])
        self.assertNotIn('focus', context.read_track(self.folder, compact=True)['frames'][0])

    def test_confirmed_group_column_reports_the_strongest_backdrop(self):
        """触发路径：agent 对商店场次运行 context-build，目录 layout.tabs.groups 有用户确认的“礼包/道具/外观”→ 左侧图文页签列按图标底块最亮的那个报出，层级排在顶部页签之后；没确认过的同样一列字不报。"""
        image = np.full((540, 960, 3), 20, np.uint8)
        result = []

        def label(x, y, word, backdrop):
            image[y - 37:y - 5, x:x + 32] = backdrop              # icon square (2 text heights) above the label
            image[y:y + 16, x:x + 32:2] = GREY
            result.append([[[x, y], [x + 32, y], [x + 32, y + 16], [x, y + 16]], word, .9])
        for row, (word, backdrop) in enumerate((('礼包', 28), ('道具', 230), ('外观', 28))):
            label(40, 120 + 70 * row, word, backdrop)
        for row, word in enumerate(('攻略', '图鉴', '排行')):
            label(700, 120 + 70 * row, word, 230 if row == 0 else 28)
        # 主菜单图标格：“道具”在“礼包”上方，顺序与确认的相反，不是这组页签。
        for row, word in enumerate(('道具', '礼包')):
            label(450, 120 + 70 * row, word, 230 if row == 0 else 28)
        image[20:36, 100:140:2] = GREY
        image[20:36, 170:210:2] = GOLD
        result += [[[[100, 20], [140, 20], [140, 36], [100, 36]], '推荐', .9],
                   [[[170, 20], [210, 20], [210, 36], [170, 36]], '精选', .9]]
        self.write_rules(dict(tabs=dict(RULES, groups=[dict(screen='商店/精选', tabs=['礼包', '道具', '外观'])])))
        _, track = self.build([(image, result)])
        self.assertEqual(track['frames'][0]['tabs'], [
            dict(kind='top', active='精选', row=['推荐', '精选'], level=1),
            dict(kind='group', active='道具', row=['礼包', '道具', '外观'], level=2)])

    def mail(self):
        return tab_frame([(20, [('收件箱', GOLD), ('藏信匣', GREY), ('发件箱', GREY)])])

    def check(self, instances, frames):
        engine = Mock(side_effect=[(result, None) for _, result in frames])
        grabs = {at: (image, image) for at, (image, _) in zip(sorted({i['evidence'][0]['start'] for i in instances}), frames)}
        with patch.object(context, '_ocr_engine', return_value=engine), patch.object(
                context, '_grab', side_effect=lambda folder, at: grabs[at]):
            return context.check_screens(self.folder, instances), engine

    @staticmethod
    def instance(ident, screen, at):
        return dict(id=ident, screen=screen, evidence=[dict(kind='video', start=at, end=at)])

    def test_submit_check_flags_a_screen_id_whose_tab_is_not_lit(self):
        """触发路径：外部 agent 提交单场整理，编号写成“邮件/藏信匣”，核对时刻画面上亮的是“收件箱”→ 提交回执里提醒 agent 再看一眼；写对的“邮件/收件箱”不提醒，画面上看不到的段不下结论。"""
        instances = [self.instance('i1', '邮件/藏信匣', 3), self.instance('i2', '邮件/收件箱/详情', 3),
                     # 组名与第一个页签同名、亮的是编号里更深一段：编号是对的，不提醒。
                     self.instance('i3', '藏信匣/收件箱', 3)]
        out, _ = self.check(instances, [self.mail()])
        self.assertEqual(out['checked'], 1)
        self.assertEqual(out['warnings'], [dict(instance='i1', at=3, screen='邮件/藏信匣', segment='藏信匣',
                                                lit='收件箱', row=['收件箱', '藏信匣', '发件箱'])])

    def test_resubmitted_moment_is_not_read_again(self):
        """触发路径：agent 收到提醒后改了编号再提交 → 同一核对时刻已在 screen-check.json 里，不应再花约 2 秒重新识别。"""
        instances = [self.instance('i1', '邮件/藏信匣', 3)]
        self.check(instances, [self.mail()])
        instances[0]['screen'] = '邮件/收件箱'
        out, engine = self.check(instances, [])
        engine.assert_not_called()
        self.assertEqual((out['checked'], out['warnings']), (1, []))

    def test_submit_check_without_ocr_says_unchecked(self):
        """触发路径：agent 经安装版的本地接口提交，安装版没有画面文字识别 → 回执写明未核对，提交本身不受影响。"""
        with patch.object(context, '_ocr_engine', side_effect=ValueError('OCR 依赖未安装')):
            out = context.check_screens(self.folder, [self.instance('i1', '邮件/藏信匣', 3)])
        self.assertEqual(out['checked'], 0)
        self.assertIn('OCR 依赖未安装', out['skipped'])

    def test_catalog_rejects_width_based_band(self):
        """触发路径：用户手填 layout 后运行 catalog-validate → 把像素或倒序区间写进高度带应报错，而不是静默不报任何页签。"""
        import game_catalog
        catalog = dict(version=1, game='合成游戏', screens=[], layout=dict(tabs=dict(RULES, text_bands=[[120, 260]])))
        with self.assertRaisesRegex(ValueError, 'text_bands'):
            game_catalog.validate_catalog(catalog)


if __name__ == '__main__':
    unittest.main()
