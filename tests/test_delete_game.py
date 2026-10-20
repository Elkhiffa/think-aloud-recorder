"""Deleting a game removes its settings and its place in the tabs and the desk; its data folder stays unless the
user ticks the (default off) data option and repeats the game's name, and then it only goes to the Recycle Bin.

Trigger path: settings → 游戏 → 删除这个游戏 → confirmation dialog → delete_preset(id, options).
"""
from pathlib import Path
import unittest
from unittest.mock import patch

from portable_config import default_vault_path
import recorder
from tests import test_desktop_service as base


class DeleteGameTests(unittest.TestCase):
    setUp = base.DesktopServiceTests.setUp
    shutdown = base.DesktopServiceTests.shutdown
    wait = base.DesktopServiceTests.wait

    def make_games(self):
        self.service._cfg.update(presets={}, active_preset_id=None)  # the base fixture starts with one game
        self.libraries = {name: self.root / ('library-' + name) for name in ('a', 'b')}
        for library in self.libraries.values():
            (library / '场次').mkdir(parents=True, exist_ok=True)
        first = self.service.save_preset({'name': '燕云十六声', 'vault': str(self.libraries['a'])})
        second = self.service.save_preset({'name': '逆水寒', 'vault': str(self.libraries['b']), 'window': 'other-window'})
        self.assertTrue(first['ok'] and second['ok'], (first, second))
        self.followed = []
        self.service.set_desk_hooks(lambda *args: None, self.followed.append)
        return first['data']['id'], second['data']['id']

    def stored(self):
        return recorder.read(self.root / 'config.json')

    def test_deleting_another_game_keeps_the_current_one_and_its_folder(self):
        first, second = self.make_games()  # second is current
        with patch.object(type(self.service), '_recycle') as recycle:
            result = self.service.delete_preset(first)
        self.assertTrue(result['ok'], result)
        self.assertEqual(list(self.service._cfg['presets']), [second])
        self.assertEqual(self.service._cfg['active_preset_id'], second)
        self.assertNotIn(first, self.stored()['presets'])
        self.assertTrue(self.libraries['a'].is_dir(), 'the data folder stays by default')
        recycle.assert_not_called()
        self.assertFalse(result['data']['recycled'])

    def test_deleting_the_current_game_switches_to_the_next_and_the_desk_follows(self):
        first, second = self.make_games()
        result = self.service.delete_preset(second)
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.service._cfg['active_preset_id'], first)
        self.assertEqual(Path(self.service._cfg['vault']).resolve(), self.libraries['a'].resolve())
        self.assertEqual(self.followed, [self.libraries['a'].resolve()])

    def test_deleting_the_last_game_returns_to_first_use_and_closes_the_desk(self):
        first, second = self.make_games()
        self.assertTrue(self.service.delete_preset(second)['ok'])
        self.assertTrue(self.service.delete_preset(first)['ok'])
        self.assertEqual(self.service._cfg['presets'], {})
        self.assertIsNone(self.service._cfg['active_preset_id'])
        self.assertFalse(self.service._cfg['configured'])
        self.assertEqual(Path(self.service._cfg['vault']), default_vault_path(self.root))
        self.assertEqual(self.followed[-1], None)
        self.assertEqual(self.service._session_paths(), {}, 'no sessions of a deleted game are listed')

    def test_a_second_click_finds_the_game_already_gone(self):
        _, second = self.make_games()
        self.assertTrue(self.service.delete_preset(second)['ok'])
        again = self.service.delete_preset(second)
        self.assertFalse(again['ok'])
        self.assertIn('已不在设置中', again['error'])

    def test_data_goes_to_the_recycle_bin_only_with_the_repeated_name(self):
        first, _ = self.make_games()
        with patch.object(type(self.service), '_recycle') as recycle:
            refused = self.service.delete_preset(first, {'delete_data': True, 'confirm_name': '燕云'})
            self.assertFalse(refused['ok'])
            self.assertIn(first, self.service._cfg['presets'], 'a refused request changes nothing')
            result = self.service.delete_preset(first, {'delete_data': True, 'confirm_name': '燕云十六声'})
        self.assertTrue(result['ok'], result)
        recycle.assert_called_once_with(self.libraries['a'].resolve())
        self.assertTrue(result['data']['recycled'])

    def test_a_recycle_failure_keeps_the_folder_and_reports_it(self):
        first, _ = self.make_games()
        with patch.object(type(self.service), '_recycle', side_effect=OSError('文件正在使用')):
            result = self.service.delete_preset(first, {'delete_data': True, 'confirm_name': '燕云十六声'})
        self.assertTrue(result['ok'], result)
        self.assertNotIn(first, self.service._cfg['presets'])
        self.assertFalse(result['data']['recycled'])
        self.assertIn('文件正在使用', result['data']['data_error'])
        self.assertTrue(self.libraries['a'].is_dir())

    def test_shared_or_protected_folders_are_never_recycled(self):
        first, second = self.make_games()
        nested = self.service.save_preset({'name': '子目录游戏', 'vault': str(self.libraries['a'] / 'nested')})
        self.assertTrue(nested['ok'], nested)
        with patch.object(type(self.service), '_recycle') as recycle:
            shared = self.service.delete_preset(first, {'delete_data': True, 'confirm_name': '燕云十六声'})
            self.assertFalse(shared['ok'])
            self.assertIn('也在使用', shared['error'])
            self.service._cfg['library_root'] = str(self.libraries['b'] / 'all-games')
            library = self.service.delete_preset(second, {'delete_data': True, 'confirm_name': '逆水寒'})
            self.assertFalse(library['ok'])
            self.assertIn('资料总库', library['error'])
            recycle.assert_not_called()
        self.assertEqual(len(self.service._cfg['presets']), 3)

    def test_a_game_with_background_transcription_cannot_be_deleted(self):
        first, _ = self.make_games()
        self.service._background_jobs['job'] = {'id': 'job', 'path': (self.libraries['a'] / '场次' / 'one').resolve()}
        result = self.service.delete_preset(first)
        self.assertFalse(result['ok'])
        self.assertIn('后台转写', result['error'])
        self.assertIn(first, self.service._cfg['presets'])


if __name__ == '__main__':
    unittest.main()
