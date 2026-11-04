"""Version acceptance (版本验收): a session keeps single-session analysis and export, and stays out of cross-session analysis."""
import json
import unittest

import agent_protocol as protocol
import insight_report
import issue_registry as issues
from session_metadata import set_acceptance
from tests import test_issue_registry as registry


class AcceptanceTests(unittest.TestCase):
    setUp = registry.IssueRegistryTests.setUp
    make_session = registry.IssueRegistryTests.make_session

    def link(self, session, instance='i1', issue='TA-01'):
        issues.link_instances(self.vault, [dict(issue=issue, session_id=session, instance_id=instance, reason='合成')])

    def test_the_mark_is_kept_in_session_json_and_its_target_survives_switching_off(self):
        """触发路径：场次库详情打开「版本验收」并填验收对象，之后关掉再打开。"""
        folder = self.make_session('s1', '2026-10-08T12:00:00+08:00', [])
        self.assertEqual(set_acceptance(folder, True, ' 摇摇马 '), dict(acceptance=True, acceptance_target='摇摇马'))
        self.assertEqual(set_acceptance(folder, False, '摇摇马'), dict(acceptance=False, acceptance_target=''))
        stored = json.loads((folder / 'session.json').read_text(encoding='utf-8'))
        self.assertEqual((stored['acceptance'], stored['acceptance_target']), (False, '摇摇马'))
        for on, target in ((1, ''), (True, 'x' * 121), (True, '换\n行'), (True, None)):
            with self.assertRaises(ValueError, msg=(on, target)):
                set_acceptance(folder, on, target)

    def test_cross_session_analysis_leaves_acceptance_sessions_out(self):
        """触发路径：跨场次整理按议题和 bug 取实例；验收场次的判断不能混进洞察和 Bug 汇总。"""
        self.make_session('daily', '2026-10-08T12:00:00+08:00', ['TA-01'])
        accepted = self.make_session('accepted', '2026-10-09T12:00:00+08:00', ['TA-01'],
                                     segments=[dict(start=2, end=4, text='这里有个 bug，按钮点不了。', speaker_id=0)])
        set_acceptance(accepted, True, '摇摇马')
        self.assertEqual([row['session_id'] for row in issues.query_instances(self.vault, issue=['TA-01'])], ['daily'])
        self.assertEqual({row['session_id'] for row in insight_report.bug_hits(self.vault)}, set())
        with self.assertRaisesRegex(ValueError, '版本验收'):
            self.link('accepted')
        # The session's own result is still complete and readable for review and export.
        self.assertEqual(protocol.preprocessing_status(accepted)['state'], 'complete')

    def test_links_made_before_the_mark_are_set_aside_not_stale(self):
        """触发路径：一场已经挂过议题，后来才标成版本验收；洞察 skill 不能把这些对应当失效对应解除。"""
        self.make_session('s1', '2026-10-08T12:00:00+08:00', [])
        folder = self.vault / '场次' / 's1'
        self.link('s1')
        set_acceptance(folder, True)
        row = next(row for row in issues.list_issues(self.vault)['issues'] if row['id'] == 'TA-01')
        self.assertEqual((row['links_active'], row['links_excluded'], row['links_stale']), (0, 1, 0))
        set_acceptance(folder, False)
        row = next(row for row in issues.list_issues(self.vault)['issues'] if row['id'] == 'TA-01')
        self.assertEqual((row['links_active'], row['links_excluded'], row['links_stale']), (1, 0, 0), 'switching back restores the link')


if __name__ == '__main__':
    unittest.main()
