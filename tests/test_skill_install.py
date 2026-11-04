from pathlib import Path
import tempfile
import unittest

import skill_install

ROOT = Path(__file__).resolve().parents[1]


class SkillInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.app, self.home = base / 'app', base / 'home'
        for name in skill_install.SKILLS:
            folder = self.app / 'docs' / 'skills' / name / 'references'
            folder.mkdir(parents=True)
            (folder.parent / 'SKILL.md').write_text('new ' + name, encoding='utf-8')
            (folder / 'interface.md').write_text('commands', encoding='utf-8')

    def test_source_checkout_and_install_both_carry_the_skills(self):
        # 路径 1：源码检出直接运行时从 skills/ 读取。
        self.assertEqual(skill_install.source_root(ROOT), ROOT / 'skills')
        for name in skill_install.SKILLS:
            self.assertTrue((ROOT / 'skills' / name / 'SKILL.md').is_file())

    def test_installs_only_into_agents_the_user_has(self):
        # 路径 1：家里只装了 Claude Code，点“安装分析 skill”。
        (self.home / '.claude').mkdir(parents=True)
        result = skill_install.install(self.app, self.home, 'stamp')
        self.assertEqual({row['agent'] for row in result['results']}, {'Claude Code'})
        self.assertEqual({row['state'] for row in result['results']}, {'installed'})
        self.assertFalse((self.home / '.codex').exists())
        target = self.home / '.claude' / 'skills' / 'think-aloud-judgments'
        self.assertEqual((target / 'references' / 'interface.md').read_text(encoding='utf-8'), 'commands')

    def test_changed_copy_is_backed_up_outside_skills_and_user_files_are_kept(self):
        # 路径 1：更新软件后再点一次；旧副本里有用户自己加的文件。
        (self.home / '.codex').mkdir(parents=True)
        target = self.home / '.codex' / 'skills' / 'think-aloud-insight'
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('old', encoding='utf-8')
        (target / 'my-notes.md').write_text('mine', encoding='utf-8')
        rows = {row['skill']: row for row in skill_install.install(self.app, self.home, 'stamp')['results']}
        row = rows['think-aloud-insight']
        self.assertEqual(row['state'], 'updated')
        backup = self.app / 'state' / 'skill-backups' / 'stamp' / 'codex' / 'think-aloud-insight'
        self.assertEqual(row['backup'], str(backup))
        self.assertEqual((backup / 'SKILL.md').read_text(encoding='utf-8'), 'old')
        self.assertEqual((target / 'SKILL.md').read_text(encoding='utf-8'), 'new think-aloud-insight')
        self.assertEqual((target / 'my-notes.md').read_text(encoding='utf-8'), 'mine')
        self.assertEqual(row['extra_files'], ['my-notes.md'])
        again = {row['skill']: row for row in skill_install.install(self.app, self.home, 'later')['results']}
        self.assertEqual(again['think-aloud-insight']['state'], 'unchanged')
        self.assertFalse((self.app / 'state' / 'skill-backups' / 'later').exists())

    def test_codemaker_only_colleagues_get_the_skills_and_keep_their_profile(self):
        # 路径 1：同事只装了 CodeMaker（没有 .claude / .codex），点“准备分析”。
        (self.home / '.codemaker').mkdir(parents=True)
        result = skill_install.install(self.app, self.home, 'stamp')
        self.assertEqual({row['agent'] for row in result['results']}, {'CodeMaker'})
        target = self.home / '.codemaker' / 'skills' / 'think-aloud-export'
        self.assertEqual((target / 'SKILL.md').read_text(encoding='utf-8'), 'new think-aloud-export')
        # 路径 1：导出 skill 第一次用时记下反馈人；之后更新 skill 不能丢。
        (target / 'profile.json').write_text('{"反馈人": "方雨骁"}', encoding='utf-8')
        (self.app / 'docs' / 'skills' / 'think-aloud-export' / 'SKILL.md').write_text('newer', encoding='utf-8')
        rows = {row['skill']: row for row in skill_install.install(self.app, self.home, 'later')['results']}
        self.assertEqual((rows['think-aloud-export']['state'], rows['think-aloud-export']['extra_files']), ('updated', ['profile.json']))
        self.assertEqual((target / 'profile.json').read_text(encoding='utf-8'), '{"反馈人": "方雨骁"}')

    def test_no_agent_folder_is_a_clear_error(self):
        self.home.mkdir()
        with self.assertRaisesRegex(ValueError, '没有找到 CodeMaker、Claude Code 或 Codex'):
            skill_install.install(self.app, self.home, 'stamp')


if __name__ == '__main__':
    unittest.main()
