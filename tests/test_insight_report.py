import unittest

import agent_protocol as protocol
import game_catalog
import insight_report as insight
import issue_registry as issues
from speaker_roles import transcript_id
import tests.test_issue_registry as registry_tests


class InsightReportTests(unittest.TestCase):
    setUp = registry_tests.IssueRegistryTests.setUp
    make_session = registry_tests.IssueRegistryTests.make_session

    def write_catalog(self):
        path = game_catalog.catalog_path(self.vault, '合成游戏')
        path.parent.mkdir(parents=True)
        protocol._write(path.parent, path.name, dict(version=1, game='合成游戏', screens=[
            dict(id='bag', name='背包', source='manual', match=dict(all_of=[], any_of=[], none_of=[]), elements=[])]))

    def test_report_citations_resolve_against_vault(self):
        """触发路径：跨场次分析 agent 写完报告后运行 insight-validate → 写错的实例或议题引用要逐条列出，报告目录外的文件读不到。"""
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [])
        folder = self.vault / insight.REPORTS
        folder.mkdir()
        (folder / 'r.md').write_text(
            '清完提示后忘了目标 [1008 i1](i:20261008-120000-aaaaaa/i1#TA-01)，'
            '[1008 i9](i:20261008-120000-aaaaaa/i9)；见 [TA-01](issue:TA-01) 与 [TA-09](issue:TA-09)。',
            encoding='utf-8')
        checked = insight.validate_report(self.vault, 'r.md')
        self.assertEqual(checked['citations'], 4)
        self.assertEqual([row['label'] for row in checked['unresolved']], ['1008 i9', 'TA-09'])
        self.assertEqual([row['name'] for row in insight.list_reports(self.vault)], ['r.md'])
        with self.assertRaisesRegex(ValueError, '报告不存在'):
            insight.read_report(self.vault, '../issues.json')

    def test_bug_hits_only_recorder_and_mark_unorganized(self):
        """触发路径：记录者说“这是 bug”后，洞察界面的 BUG 栏要列出每一处：已挂 BUG 的、成了实例但没挂的、没成实例的；另一位说话人的不算。"""
        segments = [dict(start=2, end=4, text='这是个 BUG。', speaker_id=0),
                    dict(start=5, end=6, text='我这边也有bug。', speaker_id=1),
                    dict(start=7, end=8, text='又是那个bug。', speaker_id=0),
                    dict(start=9, end=10, text='可能是 Cocos 出啥问题，文字也重叠了。', speaker_id=0),
                    dict(start=10.5, end=11, text='那只能说偶现吧。', speaker_id=0),
                    dict(start=11.1, end=11.4, text='篮子太悬空了，价格还超框。', speaker_id=0),
                    dict(start=11.5, end=11.8, text='这个都看不全了，图标也标错了。', speaker_id=0)]
        role = dict(transcript_id=transcript_id(segments), speaker_id=0, source='manual')
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', ['BUG'],
                          segments=segments, recorder_speaker=role)
        self.make_session('20261009-120000-bbbbbb', '2026-10-09T12:00:00+08:00', [],
                          segments=[dict(start=2, end=4, text='估计是手柄的bug。')])
        rows = insight.bug_hits(self.vault)
        self.assertEqual([(row['session_id'][4:8], row['ref'], row['state']) for row in rows],
                         [('1008', 't000001', 'linked'), ('1008', 't000003', 'raw'), ('1008', 't000004', 'raw'), ('1008', 't000005', 'raw'),
                          ('1008', 't000006', 'raw'), ('1008', 't000007', 'raw'),
                          ('1009', 't000001', 'instance')])
        tree = insight.evidence(self.vault)
        self.assertEqual(len(tree['bug_unorganized']), 6)
        bug = next(node for node in tree['issues'] if node['id'] == 'BUG')
        self.assertEqual([row['instance_id'] for row in bug['support']], ['i1'])
        self.assertEqual(tree['session_labels'], {'20261008-120000-aaaaaa': '1008', '20261009-120000-bbbbbb': '1009'})

    def test_confirm_proposed_screen_without_rewriting_results(self):
        """触发路径：用户在洞察界面确认 agent 提议的界面名 → 只改目录，按正式界面查询能查到原来的提议写法，场次结果字节不变。"""
        self.write_catalog()
        first = self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [],
                                  screen='兑换选择', proposed=True)
        self.make_session('20261009-120000-bbbbbb', '2026-10-09T12:00:00+08:00', [],
                          screen='活动/新页', proposed=True)
        before = (first / protocol.RESULT).read_bytes()
        self.assertEqual([group['name'] for group in insight.proposed_screens(self.vault)], ['兑换选择', '活动/新页'])
        game_catalog.confirm_proposed(self.vault, '合成游戏', '兑换选择', into='bag')
        with self.assertRaisesRegex(ValueError, '已在目录中'):
            game_catalog.confirm_proposed(self.vault, '合成游戏', '兑换选择', new_id='兑换')
        game_catalog.confirm_proposed(self.vault, '合成游戏', '活动/新页', new_id='活动/新页面', name='新页面')
        self.assertEqual(insight.proposed_screens(self.vault), [])
        rows = issues.query_instances(self.vault, screen='bag')
        self.assertEqual([(row['screen'], row['catalog_screen']) for row in rows], [('兑换选择', 'bag')])
        self.assertEqual(issues.query_instances(self.vault, screen='活动/新页')[0]['catalog_screen'], '活动/新页面')
        self.assertEqual((first / protocol.RESULT).read_bytes(), before)
        self.assertEqual(protocol.preprocessing_status(first)['state'], 'complete')

    def test_rename_catalog_screen_keeps_old_names_as_aliases(self):
        """触发路径：按界面组规则统一目录时运行 catalog-rename → 旧编号和别名都还能查到同一界面；同一组的两个条目可以并成一个；场次结果字节不变。"""
        self.write_catalog()
        first = self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [], screen='bag')
        game_catalog.confirm_proposed(self.vault, '合成游戏', '伙伴/萌主争锋', new_id='伙伴/萌主争锋')
        before = (first / protocol.RESULT).read_bytes()
        game_catalog.rename_screen(self.vault, '合成游戏', 'bag', new_id='背包/道具')
        with self.assertRaisesRegex(ValueError, '已被占用'):
            game_catalog.rename_screen(self.vault, '合成游戏', '伙伴/萌主争锋', new_id='bag')
        game_catalog.rename_screen(self.vault, '合成游戏', '伙伴/萌主争锋', new_id='萌主争锋/单打独逗')
        game_catalog.confirm_proposed(self.vault, '合成游戏', '同游/萌主争锋', new_id='同游/萌主争锋')
        game_catalog.rename_screen(self.vault, '合成游戏', '同游/萌主争锋', into='萌主争锋/单打独逗')
        screens = {row['id']: row for row in game_catalog.load_catalog(self.vault, '合成游戏')['screens']}
        self.assertEqual(sorted(screens), ['背包/道具', '萌主争锋/单打独逗'])
        self.assertEqual(screens['背包/道具']['aliases'], ['bag'])
        self.assertEqual(screens['萌主争锋/单打独逗']['aliases'], ['伙伴/萌主争锋', '同游/萌主争锋'])
        self.assertEqual(issues.query_instances(self.vault, screen='背包/道具')[0]['catalog_screen'], '背包/道具')
        self.assertEqual((first / protocol.RESULT).read_bytes(), before)

    def test_insight_bridge_confirms_and_rejects_bad_times(self):
        """触发路径：洞察窗口里确认提议界面和候选议题、点证据时间 → 确认后列表刷新；有子议题的议题不能并入；无效时间不会去打开回看或解码画面。"""
        from insight_runtime import InsightAPI
        self.write_catalog()
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [], screen='兑换选择', proposed=True)
        opened = []
        api = InsightAPI(self.vault, self.vault / 'app', lambda *args: opened.append(args) or {'ok': True})
        overview = api.get_overview()
        self.assertTrue(overview['ok'], overview)
        self.assertEqual([group['games'] for group in overview['data']['proposed']], [['合成游戏']])
        confirmed = api.confirm_proposed(dict(game='合成游戏', proposed='兑换选择', into='bag'))
        self.assertEqual(confirmed['data']['proposed'], [])
        self.assertFalse(api.open_review('20261008-120000-aaaaaa', -1)['ok'])
        self.assertFalse(api.thumbnail('20261008-120000-aaaaaa', float('nan'))['ok'])
        api.open_review('20261008-120000-aaaaaa', 2)
        self.assertEqual(opened, [('20261008-120000-aaaaaa', 2)])
        sub = issues.add_issue(self.vault, '目标被替换', parent='TA-01')
        self.assertTrue(api.update_issue(dict(id=sub['id'], status='confirmed'))['ok'])
        self.assertEqual(issues.read_registry(self.vault)['issues'][-1]['status'], 'confirmed')
        self.assertFalse(api.merge_issue('TA-01', 'TA-02')['ok'])
        self.assertTrue(api.merge_issue(sub['id'], 'TA-02')['ok'])
        self.assertEqual(issues.query_instances(self.vault)[0]['frame_at'], 3)

    def test_dismissed_candidate_leaves_results_and_other_links(self):
        """触发路径：用户在议题确认里判断疑似 bug 其实不是 bug → 驳回候选，它的对应一起移除，其他议题的对应和场次结果不变；已确认的议题不能驳回。"""
        folder = self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [])
        before = (folder / protocol.RESULT).read_bytes()
        issues.add_issue(self.vault, '教学弹窗多出遮挡', parent='BUG')
        issues.link_instances(self.vault, [dict(issue='BUG.1', session_id='20261008-120000-aaaaaa', instance_id='i1'),
                                           dict(issue='TA-01', session_id='20261008-120000-aaaaaa', instance_id='i1')])
        with self.assertRaisesRegex(ValueError, '只能驳回候选'):
            issues.dismiss_issue(self.vault, 'TA-01')
        self.assertEqual(issues.dismiss_issue(self.vault, 'BUG.1'), dict(id='BUG.1', links_removed=1))
        self.assertNotIn('BUG.1', [row['id'] for row in issues.read_registry(self.vault)['issues']])
        self.assertEqual([link['issue'] for link in issues.read_links(self.vault)['links']], ['TA-01'])
        self.assertEqual((folder / protocol.RESULT).read_bytes(), before)

    def test_evidence_groups_sub_issue_support_and_counter(self):
        """触发路径：洞察界面右栏按 议题 → 子议题 → 证据 排列，反例单独成组。"""
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [])
        self.make_session('20261009-120000-bbbbbb', '2026-10-09T12:00:00+08:00', [])
        issues.add_issue(self.vault, '目标被替换', parent='TA-01')
        issues.link_instances(self.vault, [
            dict(issue='TA-01.1', session_id='20261008-120000-aaaaaa', instance_id='i1', reason='支持'),
            dict(issue='TA-01.1', session_id='20261009-120000-bbbbbb', instance_id='i1', reason='反例', role='counter'),
            dict(issue='TA-01', session_id='20261009-120000-bbbbbb', instance_id='i1', reason='未细分')])
        tree = insight.evidence(self.vault)
        top = next(node for node in tree['issues'] if node['id'] == 'TA-01')
        self.assertEqual([row['session_id'][4:8] for row in top['support']], ['1009'])
        child = top['children'][0]
        self.assertEqual((child['id'], len(child['support']), len(child['counter'])), ('TA-01.1', 1, 1))
        self.assertNotIn('TA-01.1', [node['id'] for node in tree['issues']])


if __name__ == '__main__':
    unittest.main()
