"""After an app update, the skills and OCR component the user already has follow the app; nothing else is touched."""
import json
from pathlib import Path
import tempfile
import unittest

import component_sync
import skill_install


class FakeOcr:
    def __init__(self, folder, current, recorded=None, state='missing'):
        self.registry = Path(folder) / 'state' / 'ocr-component.json'
        self.manifest = {'id': current}
        self.state = state
        self.started = 0
        if recorded:
            self.registry.parent.mkdir(parents=True, exist_ok=True)
            self.registry.write_text(json.dumps({'schema': 1, 'model': 'ocr', 'revision': recorded}), encoding='utf-8')

    def status(self):
        return {'state': self.state}

    def start_download(self):
        self.started += 1
        return {'ok': True}


class ComponentSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.app, self.home = base / 'app', base / 'home'
        for name in skill_install.SKILLS:
            folder = self.app / 'docs' / 'skills' / name
            folder.mkdir(parents=True)
            (folder / 'SKILL.md').write_text('new ' + name, encoding='utf-8')
        self.version('0.11.1')

    def version(self, value):
        (self.app / 'portable.json').write_text(json.dumps({'version': value}), encoding='utf-8')

    def installed(self, agent, name, text='old'):
        target = self.home / agent / 'skills' / name
        target.mkdir(parents=True, exist_ok=True)
        (target / 'SKILL.md').write_text(text, encoding='utf-8')
        return target

    def test_first_start_after_an_update_brings_the_installed_skills_along(self):
        """触发路径：同事在软件里点了更新，新版第一次启动 → 他装过的 skill 跟着变成新版，旧版备份，提示里写明同步到了哪。"""
        target = self.installed('.claude', 'think-aloud-judgments')
        note = component_sync.run(self.app, self.home, 'stamp', FakeOcr(self.app, 'ocr-2'))
        self.assertEqual((target / 'SKILL.md').read_text(encoding='utf-8'), 'new think-aloud-judgments')
        self.assertEqual((note['version'], note['skills']), ('0.11.1', ['Claude Code']))
        self.assertTrue((self.app / 'state' / 'skill-backups' / 'stamp' / 'claude' / 'think-aloud-judgments' / 'SKILL.md').is_file())

    def test_later_starts_leave_the_users_edits_alone(self):
        """触发路径：更新后用户自己改了 skill，再次打开软件 → 不再覆盖；直到下一次软件更新。"""
        target = self.installed('.claude', 'think-aloud-judgments')
        component_sync.run(self.app, self.home, 'first', None)
        (target / 'SKILL.md').write_text('my edit', encoding='utf-8')
        self.assertIsNone(component_sync.run(self.app, self.home, 'second', None))
        self.assertEqual((target / 'SKILL.md').read_text(encoding='utf-8'), 'my edit')
        self.version('0.11.2')
        self.assertEqual(component_sync.run(self.app, self.home, 'third', None)['skills'], ['Claude Code'])

    def test_skills_never_installed_are_not_added(self):
        """触发路径：电脑上有 Codex 但从没装过分析 skill → 更新后不往里装；只装过一份的，也不补另外两份。"""
        (self.home / '.codex').mkdir(parents=True)
        self.installed('.claude', 'think-aloud-export', 'new think-aloud-export')
        note = component_sync.run(self.app, self.home, 'stamp', None)
        self.assertFalse((self.home / '.codex' / 'skills').exists())
        self.assertFalse((self.home / '.claude' / 'skills' / 'think-aloud-judgments').exists())
        self.assertEqual(note['skills'], [])

    def test_no_agent_at_all_still_opens_quietly(self):
        """触发路径：不用 agent 的同事更新软件 → 什么都不装，也不报错。"""
        self.home.mkdir()
        note = component_sync.run(self.app, self.home, 'stamp', None)
        self.assertEqual((note['skills'], note['errors']), ([], []))

    def test_ocr_follows_only_when_an_older_one_was_downloaded(self):
        """触发路径：新版换了识别组件。以前下载过 → 后台重新下载；从没下载过 → 不动。"""
        self.home.mkdir()
        old = FakeOcr(self.app, 'ocr-2', recorded='ocr-1')
        self.assertEqual(component_sync.run(self.app, self.home, 'a', old)['ocr'], 'downloading')
        self.assertEqual(old.started, 1)
        other = Path(self.tmp.name) / 'other'
        (other / 'docs' / 'skills').mkdir(parents=True)
        (other / 'portable.json').write_text(json.dumps({'version': '0.11.1'}), encoding='utf-8')
        never = FakeOcr(other, 'ocr-2')
        self.assertIsNone(component_sync.run(other, self.home, 'b', never)['ocr'])
        self.assertEqual(never.started, 0)


if __name__ == '__main__':
    unittest.main()
