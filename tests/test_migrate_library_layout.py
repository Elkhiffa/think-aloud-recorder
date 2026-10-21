"""The library layout migration (scripts/migrate_library_layout.py) on a temporary library.

Trigger path: the user runs the script once to move a flat library into <library>\\<game>\\ and repoint
the installed app; preview must change nothing, --apply must move everything except --keep entries,
refuse while an agent is processing, and rewrite only the presets that used the old folder.
"""
import json, subprocess, sys, time, unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'migrate_library_layout.py'


def run(*args):
    return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True, encoding='utf-8')


class MigrateLibraryLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.library = root / 'think-aloud-database'
        (self.library / '场次' / '20261016-002437-9122d7 燕云十六声').mkdir(parents=True)
        (self.library / '场次' / '20261016-002437-9122d7 燕云十六声' / 'session.json').write_text('{"id":"20261016-002437-9122d7"}', encoding='utf-8')
        (self.library / '洞察').mkdir()
        (self.library / '.obsidian').mkdir()
        (self.library / 'issues.json').write_text('{"version":1,"issues":[]}', encoding='utf-8')
        self.app = root / 'app'
        self.app.mkdir()
        other = str(root / 'competitor')
        (self.app / 'config.json').write_text(json.dumps({'vault': str(self.library), 'presets': {
            'a': {'name': '燕云十六声', 'vault': str(self.library)}, 'b': {'name': '逆水寒', 'vault': other}}}), encoding='utf-8')
        self.other = other

    def test_preview_changes_nothing(self):
        result = run('--library', self.library, '--game', '燕云十六声', '--app', self.app)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('这是预览', result.stdout)
        self.assertTrue((self.library / '场次').is_dir())
        self.assertFalse((self.library / '燕云十六声').exists())

    def test_apply_moves_everything_but_kept_entries_and_repoints_the_app(self):
        result = run('--library', self.library, '--game', '燕云十六声', '--app', self.app, '--keep', '.obsidian', '--apply')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        game = self.library / '燕云十六声'
        self.assertTrue((game / '场次' / '20261016-002437-9122d7 燕云十六声' / 'session.json').is_file())
        self.assertTrue((game / 'issues.json').is_file())
        self.assertTrue((self.library / '.obsidian').is_dir())
        self.assertEqual(sorted(p.name for p in self.library.iterdir()), ['.obsidian', '燕云十六声'])
        config = json.loads((self.app / 'config.json').read_text(encoding='utf-8'))
        self.assertEqual(Path(config['vault']).resolve(), game.resolve())
        self.assertEqual(Path(config['presets']['a']['vault']).resolve(), game.resolve())
        self.assertEqual(config['presets']['b']['vault'], self.other)
        self.assertEqual(Path(config['library_root']), self.library.resolve())
        self.assertEqual(len(list((self.app / 'state').glob('config.before-library-move-*.json'))), 1)

    def test_refuses_while_an_agent_is_processing(self):
        state = self.library / '场次' / '20261016-002437-9122d7 燕云十六声' / 'agent-state.json'
        state.write_text(json.dumps({'state': 'processing', 'expires_at': time.time() + 600}), encoding='utf-8')
        result = run('--library', self.library, '--game', '燕云十六声', '--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('正在被 agent 整理', result.stdout)
        self.assertTrue((self.library / '场次').is_dir())

    def test_refuses_an_existing_target(self):
        (self.library / '燕云十六声').mkdir()
        result = run('--library', self.library, '--game', '燕云十六声', '--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('已存在', result.stdout)


if __name__ == '__main__':
    unittest.main()
