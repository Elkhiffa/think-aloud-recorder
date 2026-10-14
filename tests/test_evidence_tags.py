import json
import subprocess
import sys
import unittest
from pathlib import Path

import agent_protocol as protocol
import evidence_tags as tags
import game_catalog
import user_feedback as feedback
import tests.test_issue_registry as registry_tests

ROOT = Path(__file__).resolve().parents[1]


def table(**extra):
    data = dict(version=1, groups=[dict(id='system', name='系统'), dict(id='play', name='活动 / 玩法')],
                tags=[dict(id='jhy', name='江湖弈', group='play', keywords=['江湖弈']),
                      dict(id='wll', name='武林录', group='play', keywords=['武林录']),
                      dict(id='shop', name='商店', group='system', keywords=['商店']),
                      dict(id='partner', name='伙伴', group='system', keywords=['伙伴/'])],
                activities={}, assignments={})
    data.update(extra)
    return data


def row(instance, event='e1', screen=None, catalog=None, route=None, session='s1'):
    found = dict(session_id=session, instance_id=instance, event_id=event, screen=screen, catalog_screen=catalog)
    if route:
        found['route'] = route
    return found


class EvidenceTagTests(unittest.TestCase):
    setUp = registry_tests.IssueRegistryTests.setUp
    make_session = registry_tests.IssueRegistryTests.make_session

    def test_tags_follow_keywords_activities_and_manual_changes(self):
        """触发路径：用户在界面库点“江湖弈”“武林录”或“伙伴” → 写法不一的江湖弈界面都要命中；从武林录进入的副本战斗（没有界面名）和自带名字的结算界面靠活动标签找到；按旧写法“伙伴/萌主争锋/…”记录、已对应到“萌主争锋/…”的界面不带出“伙伴”；跳转路径不参与匹配；误命中可以逐条去掉。"""
        path = game_catalog.catalog_path(self.vault, '合成游戏')
        path.parent.mkdir(parents=True)
        protocol._write(path.parent, path.name, dict(version=1, game='合成游戏', screens=[
            dict(id='活动（燕语江湖）/活动/江湖弈', name='江湖弈', source='manual', aliases=['燕语江湖/活动/江湖弈'],
                 match=dict(all_of=[], any_of=[], none_of=[]), elements=[])]))
        data = table(activities={'s1/e2': ['wll']}, assignments={'s1/i5': {'remove': ['shop']}, 's1/i6': {'add': ['jhy']}})
        rows = [row('i1', screen='燕语江湖/活动/江湖弈', catalog='活动（燕语江湖）/活动/江湖弈'),
                row('i2', screen='江湖弈/对局', catalog='江湖弈/对局'),
                row('i3', event='e2'),
                row('i4', event='e2', screen='镇守结算', catalog='镇守结算'),
                row('i5', screen='商店/外观', catalog='商店/外观'),
                row('i6', screen='棋盘', route=['活动（燕语江湖）/活动/江湖弈', '棋盘']),
                row('i7', screen='背包/道具', catalog='背包/道具'),
                row('i8', screen='伙伴/萌主争锋/单打独逗/备战', catalog='萌主争锋/单打独逗/备战'),
                row('i9', screen='伙伴/同游', catalog=None),
                row('i10', screen='包裹/道具', route=['商店/外观', '包裹/道具'])]
        found = tags.instance_tags(self.vault, rows, data)
        self.assertEqual(found, {'s1/i1': ['jhy'], 's1/i2': ['jhy'], 's1/i3': ['wll'], 's1/i4': ['wll'], 's1/i6': ['jhy'],
                                 's1/i9': ['partner']})

    def test_write_validates_and_keeps_user_covers(self):
        """触发路径：agent 用 tags-write 整份重写标签表 → 写坏的表整份拒绝；用户在洞察窗口右键设好的封面不会被覆盖；用户能对某个标签提反馈。"""
        with self.assertRaisesRegex(ValueError, '维度不存在'):
            tags.write_tags(self.vault, table(tags=[dict(id='x', name='X', group='nope', keywords=[])]))
        with self.assertRaisesRegex(ValueError, '不存在的标签'):
            tags.write_tags(self.vault, table(activities={'s1/e1': ['missing']}))
        tags.write_tags(self.vault, table())
        tags.set_cover(self.vault, 'jhy', 's1', 12.5)
        file = self.vault / 'new-tags.json'
        file.write_text(json.dumps(table(), ensure_ascii=False), encoding='utf-8')
        subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'agent_cli.py'), 'tags-write', str(self.vault),
                        '--file', str(file)], capture_output=True, check=True)
        self.assertEqual(next(tag for tag in tags.read_tags(self.vault)['tags'] if tag['id'] == 'jhy')['cover'],
                         dict(session_id='s1', at=12.5))
        with self.assertRaisesRegex(ValueError, '标签不存在'):
            tags.set_cover(self.vault, 'none', 's1', 1)
        self.assertEqual(feedback.add_feedback(self.vault, dict(kind='tag', id='jhy'), '江湖弈漏了对局里的 HUD')['target'],
                         dict(kind='tag', id='jhy'))

    def test_report_lists_counts_untagged_evidence_and_activities(self):
        """触发路径：agent 运行 tags-report 检查打标签的结果 → 看到各标签条数、没有标签的证据和还没打标签的活动。"""
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [], screen=None)
        tags.write_tags(self.vault, table())
        before = tags.report(self.vault)
        self.assertEqual((before['untagged'], [row['activity'] for row in before['activities_without_tags']]),
                         (1, ['20261008-120000-aaaaaa/e1']))
        tags.write_tags(self.vault, table(activities={'20261008-120000-aaaaaa/e1': ['wll']}))
        after = tags.report(self.vault)
        self.assertEqual((after['untagged'], after['activities_without_tags']), (0, []))
        self.assertEqual(next(tag for tag in after['tags'] if tag['id'] == 'wll')['instances'], 1)


if __name__ == '__main__':
    unittest.main()
