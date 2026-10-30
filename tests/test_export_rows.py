"""export-rows: one flat row per judgment for filling a team spreadsheet (skill think-aloud-export)."""
from copy import deepcopy
import unittest

import agent_protocol as protocol
from export_rows import export_rows
from tests import test_issue_registry as registry


class ExportRowsTests(unittest.TestCase):
    setUp = registry.IssueRegistryTests.setUp
    make_session = registry.IssueRegistryTests.make_session

    def test_rows_carry_what_a_table_needs(self):
        """触发路径：同事在 agent 里说“把这一场导出到手柄跑测表”→ agent 先取这一场的行再按表的列填。"""
        folder = self.make_session('s1', '2026-10-08T12:00:00+08:00', [], screen='同游/止戈')
        result = protocol._load(folder, protocol.RESULT)
        later = deepcopy(result['instances'][0])
        # A judgment about an earlier session has no referred moment here and no checked frame.
        later.update(id='i2', kind='observation', evidence=[], refers_to=dict(start=None, end=None, basis='earlier_session', note='上周那场'))
        result['instances'].append(later)
        protocol._write(folder, protocol.RESULT, result)
        data = export_rows(self.vault, ['s1'])
        self.assertEqual([row['session_id'] for row in data['sessions']], ['s1'])
        first, second = data['rows']
        self.assertEqual((first['screen'], first['screen_path'], first['kind'], first['problem']), ('同游/止戈', ['同游', '止戈'], 'confusion', True))
        self.assertEqual((first['quote'], first['frame_at'], first['refers_start'], first['event_title']), ('不知道应该去哪里。', 3, 2, '寻找目标'))
        self.assertEqual((second['problem'], second['frame_at'], second['refers_start']), (False, 2, None), 'falls back to when it was said')
        self.assertEqual(data['sessions'][0]['folder'], str(folder.resolve()))

    def test_acceptance_sessions_are_exported_and_unknown_ids_reported(self):
        """触发路径：版本验收场次不进跨场次分析，但它本身的问题要能导出到验收表。"""
        self.make_session('s1', '2026-10-08T12:00:00+08:00', [], acceptance=True, acceptance_target='摇摇马')
        self.make_session('s2', '2026-10-09T12:00:00+08:00', [], test=True)
        data = export_rows(self.vault, all_sessions=True)
        self.assertEqual([(row['session_id'], row['acceptance'], row['acceptance_target']) for row in data['sessions']], [('s1', True, '摇摇马')],
                         'a synthetic test session is left out of --all')
        missing = export_rows(self.vault, ['s1', 'nope'])
        self.assertEqual(missing['skipped'], [dict(session_id='nope', reason='资料库里没有这一场。')])
        with self.assertRaises(ValueError):
            export_rows(self.vault)

    def test_bug_marks_from_the_library_count_and_unorganized_sessions_are_skipped(self):
        """触发路径：洞察里挂到 BUG 下的判断，导出时同样算 bug；还没整理的场次说明原因。"""
        folder = self.make_session('s1', '2026-10-08T12:00:00+08:00', ['BUG'])
        result = protocol._load(folder, protocol.RESULT)
        result['instances'][0]['bug'] = 'explicit'
        protocol._write(folder, protocol.RESULT, result)
        raw = self.vault / '场次' / 'raw'
        raw.mkdir()
        protocol._write(raw, 'session.json', dict(id='raw', game='合成游戏', created='2026-10-10T12:00:00+08:00',
                                                  state='可回看', media=dict(duration=12)))
        data = export_rows(self.vault, all_sessions=True)
        self.assertEqual([(row['instance_id'], row['bug']) for row in data['rows']], [('i1', 'explicit')])
        self.assertEqual([row['session_id'] for row in data['skipped']], ['raw'])


if __name__ == '__main__':
    unittest.main()
