import copy
import json
from pathlib import Path
import tempfile
import unittest

import game_catalog as catalog


def sample_catalog():
    return dict(version=1, game='合成游戏', screens=[
        dict(id='bag.items', name='背包·道具', source='manual', engine_id='BagItems',
             match=dict(all_of=['仓库'], any_of=['道具', '材料'], none_of=['任务']),
             elements=[dict(id='bag.items.use', name='使用', aliases=['使用道具', '使用'], notes='')]),
        dict(id='bag.quest', name='背包·任务', source='engine',
             match=dict(all_of=['仓库', '任务'], any_of=[], none_of=[]), elements=[]),
        dict(id='bag.fallback', name='仓库', source='ocr_cluster',
             match=dict(all_of=['仓库'], any_of=[], none_of=[]), elements=[]),
    ])


def frame(at, text):
    return dict(t=at, items=[[100, 30, text]])


class GameCatalogTests(unittest.TestCase):
    def test_match_rules_and_catalog_order(self):
        """触发路径：目录里“背包·道具”和“背包·任务”都含“仓库”等共同字样 → 不加 none_of 和取舍规则就会互相误判。"""
        data = sample_catalog()
        self.assertEqual(catalog.match_frame(data, frame(0, '仓库 道具'))['id'], 'bag.items')
        self.assertEqual(catalog.match_frame(data, frame(0, '仓库 道具 任务'))['id'], 'bag.quest')
        self.assertEqual(catalog.match_frame(data, frame(0, '仓库'))['id'], 'bag.fallback')
        self.assertIsNone(catalog.match_frame(data, frame(0, '道具')))
        tied = copy.deepcopy(data['screens'][0])
        tied['id'] = 'bag.same'
        data['screens'].append(tied)
        self.assertEqual(catalog.match_frame(data, frame(0, '仓库 道具'))['id'], 'bag.items')
        tied['match']['all_of'].append('稀有')
        self.assertEqual(catalog.match_frame(data, frame(0, '仓库 道具 稀有'))['id'], 'bag.same')
        # 触发路径：用户只确认了界面名称、还没写匹配词 → 这类界面排在目录最前也不能认领任意一帧。
        data['screens'].insert(0, dict(id='named.only', name='只有名称', source='manual', elements=[],
                                       match=dict(all_of=[], any_of=[], none_of=[])))
        self.assertIsNone(catalog.match_frame(data, frame(0, '道具')))
        self.assertEqual(catalog.match_frame(data, frame(0, '仓库 道具'))['id'], 'bag.items')

    def test_adjacent_frames_merge(self):
        """触发路径：agent 读界面时间轴时需要的是区间，不是逐帧列表。"""
        spans = catalog.match_screens(sample_catalog(), [
            frame(0, '仓库 道具'), frame(5, '仓库 材料'),
            frame(10, '仓库 任务'), frame(15, '无匹配'), frame(20, '无匹配'),
            frame(25, '仓库 道具'),
        ])
        self.assertEqual(spans, [
            dict(start=0, end=5, screen='bag.items', source='ocr', engine_id='BagItems'),
            dict(start=10, end=10, screen='bag.quest', source='ocr'),
            dict(start=15, end=20, screen=None, source='ocr'),
            dict(start=25, end=25, screen='bag.items', source='ocr', engine_id='BagItems'),
        ])

    def test_validate_rejects_duplicate_ids(self):
        """触发路径：手工编辑 JSON 时复制条目忘了改 id → 实例引用指向不明确。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = catalog.catalog_path(tmp, '合成游戏')
            path.parent.mkdir(parents=True)
            for kind in ('screen', 'element'):
                with self.subTest(kind=kind):
                    data = sample_catalog()
                    if kind == 'screen':
                        data['screens'][1]['id'] = data['screens'][0]['id']
                    else:
                        data['screens'][1]['elements'] = copy.deepcopy(data['screens'][0]['elements'])
                    path.write_text(json.dumps(data), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, kind + ' id 重复'):
                        catalog.validate(tmp, '合成游戏')

    def test_hotwords_deduplicates_names_and_aliases(self):
        """触发路径：元素别名之间、别名与名称重复 → 导出的词表出现重复词条。"""
        with tempfile.TemporaryDirectory() as tmp:
            data = sample_catalog()
            data['screens'][0]['aliases'] = ['道具', '使用']
            data['screens'][1]['elements'] = [dict(id='bag.quest.use', name='使用', aliases=['道具'])]
            path = catalog.catalog_path(tmp, data['game'])
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(data), encoding='utf-8')
            before = path.read_bytes()
            output = Path(tmp) / 'work' / 'hotwords.txt'
            result = catalog.hotwords(tmp, data['game'], output)
            self.assertEqual(output.read_text(encoding='utf-8').splitlines(),
                             ['背包·道具', '道具', '使用', '使用道具', '背包·任务', '仓库'])
            self.assertEqual(result['count'], 6)
            self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
