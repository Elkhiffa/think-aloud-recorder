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

    def write_report(self, body):
        folder = self.vault / insight.REPORTS
        folder.mkdir(exist_ok=True)
        (folder / 'q.md').write_text(body, encoding='utf-8')
        return insight.validate_report(self.vault, 'q.md')

    def test_verbatim_quote_before_citation_passes(self):
        """触发路径：agent 按简报写完报告后运行 insight-validate → 引号里照抄转写原文（可省略号节选、标点不同）不报错，没跟引用的引号不核对。"""
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [],
                          segments=[dict(start=2, end=4, text='这个焦点老是会跑到下面来，为什么？', speaker_id=0)])
        checked = self.write_report(
            '他说“这个焦点老是会跑到下面来……为什么”[1008 i1](i:20261008-120000-aaaaaa/i1)。'
            '规则名‘焦点落点规则’和“没有引用的引号”都不核对。')
        self.assertEqual((checked['quotes_checked'], checked['quotes_unverified']), (1, []))

    def test_corrected_quote_passes_when_registered(self):
        """触发路径：agent 按上下文改正了引号里的转写错字，并登记在附录“转写修正”表 → insight-validate 套用登记的改字后认为一致。"""
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [],
                          segments=[dict(start=2, end=4, text='焦点又左交出去了。', speaker_id=0)])
        checked = self.write_report(
            '“焦点又走焦出去了。”[1008 i1](i:20261008-120000-aaaaaa/i1)\n\n'
            '## 转写修正\n\n| 原文 | 改成 | 依据 | 引用 |\n|---|---|---|---|\n'
            '| 左交 | 走焦 | 上下文在讲手柄焦点 | [1008 i1](i:20261008-120000-aaaaaa/i1) |\n')
        self.assertEqual((checked['quotes_checked'], checked['quotes_unverified']), (1, []))

    def test_unregistered_quote_change_is_listed(self):
        """触发路径：引号里改了字却没登记、或把原话没有的字加进引号 → insight-validate 在 quotes_unverified 里逐条列出，引用本身仍算解析成功。"""
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [],
                          segments=[dict(start=2, end=4, text='焦点又左交出去了。', speaker_id=0)])
        checked = self.write_report('“焦点又走焦出去了。”[1008 i1](i:20261008-120000-aaaaaa/i1)；'
                                    '“焦点又左交出去了，真烦”[1008 i1](i:20261008-120000-aaaaaa/i1)')
        self.assertEqual(checked['unresolved'], [])
        self.assertEqual(checked['quotes_checked'], 2)
        self.assertEqual([row['quote'] for row in checked['quotes_unverified']],
                         ['焦点又走焦出去了。', '焦点又左交出去了，真烦'])
        self.assertEqual(checked['quotes_unverified'][0]['instance_id'], 'i1')

    def test_consecutive_quotes_prefixed_heading_and_unlinked_anchor(self):
        """触发路径：报告里两段原话连写在同一个引用前、附录标题写成“### E. 转写修正”、引用的 # 议题并没挂着这条证据 → insight-validate 都要核到并列出。"""
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [],
                          segments=[dict(start=2, end=4, text='焦点又左交出去了。', speaker_id=0)])
        issues.link_instances(self.vault, [dict(issue='TA-01', session_id='20261008-120000-aaaaaa', instance_id='i1',
                                                reason='焦点', role='support')])
        cite = '[1008 i1](i:20261008-120000-aaaaaa/i1#{})'
        checked = self.write_report(
            '“焦点又走焦”和“编造的话”' + cite.format('TA-01') + '；“焦点又走焦出去了”' + cite.format('BUG') +
            '\n\n### E. 转写修正\n\n| 原文 | 改成 | 依据 | 引用 |\n|---|---|---|---|\n| 左交 | 走焦 | 上下文 | |\n')
        self.assertEqual(checked['quotes_checked'], 3)
        self.assertEqual([row['quote'] for row in checked['quotes_unverified']], ['编造的话'])
        self.assertEqual([row['issue'] for row in checked['anchors_unlinked']], ['BUG'])

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

    def test_insight_bridge_records_feedback_and_rejects_bad_times(self):
        """触发路径：洞察窗口里在议题或证据卡上点铅笔提反馈、右键证据卡设标签封面、点证据时间 → 反馈和封面写进资料库并随概览返回；无效时间不会去打开回看或解码画面。"""
        from insight_runtime import InsightAPI
        self.make_session('20261008-120000-aaaaaa', '2026-10-08T12:00:00+08:00', [])
        opened = []
        api = InsightAPI(self.vault, self.vault / 'app', lambda *args: opened.append(args) or {'ok': True})
        overview = api.get_overview()
        self.assertTrue(overview['ok'], overview)
        self.assertEqual(overview['data']['feedback'], [])
        self.assertNotIn('proposed', overview['data'])
        items = api.add_feedback(dict(target=dict(kind='issue', id='TA-01'), text='这条该并进操作路径'))['data']
        self.assertEqual([item['text'] for item in items], ['这条该并进操作路径'])
        self.assertFalse(api.add_feedback(dict(target=dict(kind='issue', id='TA-99'), text='不存在'))['ok'])
        self.assertEqual(api.edit_feedback(items[0]['id'], '改成并进路径')['data'][0]['text'], '改成并进路径')
        self.assertEqual(api.get_overview()['data']['feedback'][0]['text'], '改成并进路径')
        self.assertEqual(api.remove_feedback(items[0]['id'])['data'], [])
        import evidence_tags
        evidence_tags.write_tags(self.vault, dict(version=1, groups=[dict(id='play', name='玩法')], tags=[
            dict(id='wll', name='武林录', group='play', keywords=[])], activities={'20261008-120000-aaaaaa/e1': ['wll']},
            assignments={}))
        overview = api.get_overview()['data']
        self.assertEqual((overview['tags'][0]['name'], overview['instance_tags']), ('武林录', {'20261008-120000-aaaaaa/i1': ['wll']}))
        self.assertEqual(api.set_cover('wll', '20261008-120000-aaaaaa', 3)['data'][0]['cover'],
                         dict(session_id='20261008-120000-aaaaaa', at=3))
        self.assertFalse(api.open_review('20261008-120000-aaaaaa', -1)['ok'])
        self.assertFalse(api.thumbnail('20261008-120000-aaaaaa', float('nan'))['ok'])
        api.open_review('20261008-120000-aaaaaa', 2)
        self.assertEqual(opened, [('20261008-120000-aaaaaa', 2)])
        self.assertEqual(issues.query_instances(self.vault)[0]['frame_at'], 3)

    def test_dismissed_candidate_leaves_results_and_other_links(self):
        """触发路径：用户反馈某个疑似 bug 其实不是 bug，跨场次 agent 运行 issues-dismiss → 驳回候选，它的对应一起移除，其他议题的对应和场次结果不变；已确认的议题不能驳回。"""
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
