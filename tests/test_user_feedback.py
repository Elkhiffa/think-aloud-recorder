import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import issue_registry as issues
import user_feedback as feedback


class UserFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        issues.add_issue(self.vault, '目标明确时，仍有执行摩擦', 'TA-01', 'confirmed')

    def tearDown(self):
        self.temp.cleanup()

    def test_marked_problem_reaches_the_next_agent_run(self):
        """触发路径：用户在洞察窗口点议题或证据卡上的“有问题”写一句怎么调 → 存进 feedback.json；下一轮 agent 用 feedback-list 读到，处理后 feedback-resolve 写明改了什么。"""
        on_issue = feedback.add_feedback(self.vault, dict(kind='issue', id='TA-01'), '这条应该并进操作路径')
        on_card = feedback.add_feedback(self.vault, dict(kind='instance', session_id='s1', instance_id='i3', issue='TA-01'),
                                        '界面名不对，应是包裹/道具')
        with self.assertRaisesRegex(ValueError, '议题不存在'):
            feedback.add_feedback(self.vault, dict(kind='issue', id='TA-99'), '不存在')
        with self.assertRaisesRegex(ValueError, '文字'):
            feedback.add_feedback(self.vault, dict(kind='issue', id='TA-01'), '  ')
        feedback.edit_feedback(self.vault, on_card['id'], '界面名不对，应是包裹/任务')
        listed = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'agent_cli.py'), 'feedback-list',
                                 str(self.vault), '--open'], capture_output=True, text=True, encoding='utf-8', check=True)
        items = json.loads(listed.stdout)['data']['items']
        self.assertEqual([item['text'] for item in items], ['这条应该并进操作路径', '界面名不对，应是包裹/任务'])
        self.assertEqual(items[1]['target'], dict(kind='instance', session_id='s1', instance_id='i3', issue='TA-01'))
        subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'agent_cli.py'), 'feedback-resolve',
                        str(self.vault), on_issue['id'], '--note', '已挪到 TA-01 下'], capture_output=True, check=True)
        self.assertEqual([item['id'] for item in feedback.list_feedback(self.vault, open_only=True)['items']], [on_card['id']])
        resolved = feedback.list_feedback(self.vault)['items'][0]
        self.assertEqual((resolved['status'], resolved['resolution']), ('resolved', '已挪到 TA-01 下'))
        feedback.remove_feedback(self.vault, on_card['id'])
        self.assertEqual(len(feedback.read_feedback(self.vault)['items']), 1)


if __name__ == '__main__':
    unittest.main()
