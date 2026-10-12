from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import agent_protocol as protocol
import event_edits
import issue_registry as issues


class IssueRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Path(self.temp.name)
        issues.add_issue(self.vault, '目标丢失', 'TA-01', 'confirmed')
        issues.add_issue(self.vault, '入口不明', 'TA-02', 'confirmed')

    def make_session(self, ident, created, tags, segments=None, screen=None, proposed=False, **meta):
        folder = self.vault / '场次' / ident
        folder.mkdir(parents=True)
        segments = segments or [dict(start=2, end=4, text='不知道应该去哪里。', speaker_id=0)]
        protocol._write(folder, 'session.json', dict(id=ident, game='合成游戏', created=created,
                        state='可回看', transcription_state='ready', media=dict(duration=12),
                        input_offset_seconds=1, settings=dict(record_inputs=False), **meta))
        protocol._write(folder, '录像.whisper.json', dict(segments=segments))
        (folder / '录像.mp4').write_bytes(b'synthetic video placeholder')
        manifest = protocol.publish_ready(folder)
        result = dict(version=2, session_id=ident, revision=manifest['revision'], summary='合成整理。',
                      coverage=dict(video_ranges=[dict(start=0, end=12)], transcript='full',
                                    inputs='none', limitations=['合成数据']),
                      events=[dict(id='e1', start=0, end=12, title='寻找目标', summary='表达方向疑惑。',
                                   context='', basis='explicit', kind='friction',
                                   evidence=[dict(kind='quote', ref='t000001')])],
                      questions=[], ideas=[], instances=[
                          dict(id='i1', event_id='e1', said=[dict(kind='quote', ref='t000001')],
                               refers_to=dict(start=2, end=4, basis='same_time'), screen=screen,
                               elements=[], kind='confusion', statement='不知道目标方向。',
                               issue_tags=tags, evidence=[dict(kind='video', start=3, end=3,
                                                               observation='合成目标按钮。')], confidence='high')])
        if proposed:
            result['instances'][0]['screen_proposed'] = True
        job = protocol.claim(folder, 'synthetic-worker')
        protocol.submit(folder, job['token'], result)
        return folder

    def test_query_filters_issue_across_complete_sessions(self):
        """触发路径：用户要处理“目标丢失”议题 → 需要列出所有场次中挂了该标签的实例，按时间排序依次回看。"""
        self.make_session('later', '2026-10-09T12:00:00+08:00', ['TA-01'])
        earlier = self.make_session('earlier', '2026-10-08T12:00:00+08:00', ['TA-01', 'TA-02'])
        self.make_session('other', '2026-10-07T12:00:00+08:00', ['TA-02'])
        stale = self.make_session('stale', '2026-10-06T12:00:00+08:00', ['TA-01'])
        protocol._write(stale, '录像.whisper.json', dict(segments=[dict(start=2, end=4, text='重新转写。')]))
        result = protocol._load(earlier, protocol.RESULT)
        second = deepcopy(result['instances'][0])
        second.update(id='i2', refers_to=dict(start=6, end=7, basis='unknown'))
        result['instances'].insert(0, second)
        protocol._write(earlier, protocol.RESULT, result)
        rows = issues.query_instances(self.vault, issue=['TA-01'])
        self.assertEqual([(row['session_id'], row['instance_id']) for row in rows],
                         [('earlier', 'i1'), ('earlier', 'i2'), ('later', 'i1')])
        self.assertEqual(rows[0]['said_start'], 2)
        self.assertEqual(rows[0]['refers_start'], 2)
        self.assertEqual(rows[0]['refers_end'], 4)

    def test_merge_rewrites_references_backs_up_and_preserves_calibration(self):
        """触发路径：用户发现两个标签说的是同一个问题 → 合并后旧标签的实例全部归到新标签，原结果可追溯。"""
        first = self.make_session('first', '2026-10-08T12:00:00+08:00', ['TA-01', 'TA-02'])
        second = self.make_session('second', '2026-10-09T12:00:00+08:00', ['TA-01'])
        state = protocol.preprocessing_status(first, include_result=True)
        request = dict(**state['editing'], event_id='e1', fields=event_edits.editable(state['result']['events'][0]))
        request['fields']['title'] = '用户校准后的标题'
        event_edits.save(first, request)
        original_corrections = event_edits._read(first)['history']
        # 同一合并路径包含旧旁车快照；合并必须保留其解释偏移的含义。
        raw = protocol._load(second, protocol.RESULT)
        context = raw.pop('analysis_context')
        protocol._write(second, protocol.RESULT, raw)
        protocol._write(second, protocol.ANALYSIS_CONTEXT,
                        dict(result_sha256=protocol._file_hash(second / protocol.RESULT), **context))
        originals = {folder: (folder / protocol.RESULT).read_bytes() for folder in (first, second)}
        merged = issues.merge_issues(self.vault, 'TA-01', 'TA-02')
        self.assertEqual((merged['sessions'], merged['instances'], merged['corrections_migrated']), (2, 2, 1))
        self.assertEqual([row['id'] for row in issues.list_issues(self.vault)['issues']], ['BUG', 'TA-02'])
        for folder in (first, second):
            raw = protocol._load(folder, protocol.RESULT)
            self.assertEqual(raw['instances'][0]['issue_tags'], ['TA-02'])
            self.assertEqual(next((folder / 'agent-history').glob('*.json')).read_bytes(), originals[folder])
            self.assertEqual(protocol.preprocessing_status(folder)['state'], 'complete')
        state = protocol.preprocessing_status(first, include_result=True)
        self.assertEqual(state['result']['events'][0]['title'], '用户校准后的标题')
        self.assertTrue(state['result']['events'][0]['manually_edited'])
        history = event_edits._read(first)['history']
        self.assertEqual(history[:len(original_corrections)], original_corrections)
        self.assertNotEqual(history[-1]['id'], original_corrections[0]['id'])
        self.assertEqual(history[-1]['base_result_sha256'], protocol._file_hash(first / protocol.RESULT))
        self.assertEqual(protocol._load(second, protocol.RESULT)['analysis_context'], context)


    def test_links_make_issue_query_work_across_sessions(self):
        """触发路径：跨场次分析 agent 把“议题 → 实例”的归类批量写入对应表 → 用户按议题查询，三场挂了该议题的实例都要列出来；只存在表里时查询为空。"""
        self.make_session('first', '2026-10-08T12:00:00+08:00', [])
        self.make_session('second', '2026-10-09T12:00:00+08:00', [])
        issues.add_issue(self.vault, '提示何时算看过')
        rows = [dict(issue='TA-01', session_id='second', instance_id='i1', reason='方向不明'),
                dict(issue='N-001', session_id='first', instance_id='i1', reason='红点'),
                dict(issue='TA-01', session_id='first', instance_id='i1', reason='方向不明')]
        with self.assertRaisesRegex(ValueError, '实例不存在'):
            issues.link_instances(self.vault, rows + [dict(issue='TA-01', session_id='first', instance_id='i9')])
        self.assertFalse((self.vault / issues.LINKS).exists())
        self.assertEqual(issues.link_instances(self.vault, rows), dict(added=3, updated=0, total=3))
        found = issues.query_instances(self.vault, issue=['TA-01'])
        self.assertEqual([(row['session_id'], row['instance_id']) for row in found],
                         [('first', 'i1'), ('second', 'i1')])
        self.assertEqual(found[0]['issue_tags'], ['N-001', 'TA-01'])
        self.assertEqual(found[0]['issue_links'][1], dict(issue='TA-01', reason='方向不明', role='support'))
        self.assertEqual((found[0]['event_id'], found[0]['event_title']), ('e1', '寻找目标'))
        for folder in ('first', 'second'):
            self.assertEqual(protocol._load(self.vault / '场次' / folder, protocol.RESULT)['instances'][0]['issue_tags'], [])

    def test_links_to_reanalysed_result_stop_applying(self):
        """触发路径：用户要求重新整理某场 → 新结果的内容变了，实例编号还可能被沿用 → 旧对应不能悄悄挂到新实例上，议题列表要显示它已过期。"""
        folder = self.make_session('only', '2026-10-08T12:00:00+08:00', [])
        issues.link_instances(self.vault, [dict(issue='TA-02', session_id='only', instance_id='i1')])
        self.assertEqual(len(issues.query_instances(self.vault, issue=['TA-02'])), 1)
        result = protocol._load(folder, protocol.RESULT)
        for key in ('receipt', 'analysis_context'):
            result.pop(key, None)
        result['instances'][0]['statement'] = '重新整理后的陈述。'
        job = protocol.reprocess(folder, 'synthetic-worker', '方法更新后重做')
        protocol.submit(folder, job['token'], result)
        self.assertEqual(issues.query_instances(self.vault, issue=['TA-02']), [])
        row = next(row for row in issues.list_issues(self.vault)['issues'] if row['id'] == 'TA-02')
        self.assertEqual((row['links_active'], row['links_stale']), (0, 1))

    def test_merge_moves_links_to_target_issue(self):
        """触发路径：用户决定把“红点何时算看过”并入“播报与注意力”议题 → 合并后对应表里的实例都要归到目标议题下。"""
        self.make_session('first', '2026-10-08T12:00:00+08:00', [])
        issues.link_instances(self.vault, [dict(issue='TA-01', session_id='first', instance_id='i1'),
                                           dict(issue='TA-02', session_id='first', instance_id='i1')])
        issues.merge_issues(self.vault, 'TA-01', 'TA-02')
        self.assertEqual(issues.read_links(self.vault)['links'][0]['issue'], 'TA-02')
        self.assertEqual(len(issues.read_links(self.vault)['links']), 1)
        self.assertEqual([row['instance_id'] for row in issues.query_instances(self.vault, issue=['TA-02'])], ['i1'])

    def test_merge_keeps_other_links_of_rewritten_session_active(self):
        """触发路径：实例上直接带着旧标签的场次被合并改写 → 同一场里挂在其他议题下的对应不能因结果摘要变化而失效。"""
        self.make_session('first', '2026-10-08T12:00:00+08:00', ['TA-01'])
        issues.add_issue(self.vault, '奖励效率', 'TA-03', 'confirmed')
        issues.link_instances(self.vault, [dict(issue='TA-02', session_id='first', instance_id='i1')])
        merged = issues.merge_issues(self.vault, 'TA-01', 'TA-03')
        self.assertEqual(merged['sessions'], 1)
        row = next(row for row in issues.list_issues(self.vault)['issues'] if row['id'] == 'TA-02')
        self.assertEqual((row['links_active'], row['links_stale']), (1, 0))

    def test_sub_issues_hold_support_and_counter_evidence(self):
        """触发路径：跨场次分析把议题下的模式写成子议题，并把反例和支持证据分开挂 → 按父议题查询能带出子议题的证据和角色。"""
        self.make_session('first', '2026-10-08T12:00:00+08:00', [])
        self.make_session('second', '2026-10-09T12:00:00+08:00', [])
        sub = issues.add_issue(self.vault, '代价：目标被替换', parent='TA-01')
        self.assertEqual((sub['id'], sub['parent']), ('TA-01.1', 'TA-01'))
        self.assertEqual(issues.add_issue(self.vault, '提示抢占操作', parent='TA-01')['id'], 'TA-01.2')
        with self.assertRaisesRegex(ValueError, '不能再建子议题'):
            issues.add_issue(self.vault, '更深一层', parent='TA-01.1')
        with self.assertRaisesRegex(ValueError, '指定父议题'):
            issues.add_issue(self.vault, '没有父议题', 'TA-02.1')
        with self.assertRaisesRegex(ValueError, 'support 或 counter'):
            issues.link_instances(self.vault, [dict(issue='TA-01.1', session_id='first', instance_id='i1', role='maybe')])
        issues.link_instances(self.vault, [
            dict(issue='TA-01.1', session_id='first', instance_id='i1', reason='清完红点忘了目标'),
            dict(issue='TA-01.1', session_id='second', instance_id='i1', reason='专注时少提示反而好', role='counter')])
        rows = issues.query_instances(self.vault, issue=['TA-01'])
        self.assertEqual([(row['session_id'], row['issue_links'][0]['issue'], row['issue_links'][0]['role'])
                          for row in rows], [('first', 'TA-01.1', 'support'), ('second', 'TA-01.1', 'counter')])
        with self.assertRaisesRegex(ValueError, '还有子议题'):
            issues.merge_issues(self.vault, 'TA-01', 'TA-02')

    def test_bug_is_a_fixed_issue_single_session_can_tag(self):
        """触发路径：记录者在原话里说“这是 bug” → 单场次整理直接挂 BUG，BUG 不能改名或被合并。"""
        self.make_session('first', '2026-10-08T12:00:00+08:00', ['BUG'])
        self.assertIn('BUG', [row['id'] for row in issues.list_issues(self.vault)['issues']])
        self.assertEqual(len(issues.query_instances(self.vault, issue=['BUG'])), 1)
        with self.assertRaisesRegex(ValueError, '固定议题'):
            issues.merge_issues(self.vault, 'BUG', 'TA-01')
        with self.assertRaisesRegex(ValueError, '固定议题'):
            issues.update_issue(self.vault, 'BUG', title='缺陷')
        self.assertEqual(issues.add_issue(self.vault, '手柄独占', parent='BUG')['id'], 'BUG.1')


if __name__ == '__main__':
    unittest.main()
