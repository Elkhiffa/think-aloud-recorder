"""General settings are shared by every game; a game keeps its name, window, folder and own vocabulary.

Trigger paths: the settings page 通用 tab calls save_general; the 游戏 tab and the new-game wizard call
save_preset with game_hotword_files. Recording keeps reading one merged preset.
"""
import unittest

from agent_protocol import _digest
from hotword_files import dictionary_id
from tests import test_desktop_service as base

NAMES = {}


def vocabulary(name, *words):
    """A vocabulary snapshot as the file picker returns it (the id is derived from the words)."""
    ident = dictionary_id(list(words))
    NAMES[name] = ident
    return {'id': ident, 'name': name + '.txt', 'words': list(words)}


def ids(files):
    reverse = {value: key for key, value in NAMES.items()}
    return [reverse.get(item['id'], item['id']) for item in files]


class SettingsSplitTests(unittest.TestCase):
    setUp = base.DesktopServiceTests.setUp
    shutdown = base.DesktopServiceTests.shutdown
    wait = base.DesktopServiceTests.wait

    def make_games(self):
        first = self.service.save_preset({'name': '燕云十六声', 'game_hotword_files': [vocabulary('yanyun', '奇术')]})
        self.assertTrue(first['ok'], first)
        other = self.root / 'other-library'
        second = self.service.save_preset({'name': '逆水寒', 'vault': str(other), 'window': 'other-window',
                                           'game_hotword_files': [vocabulary('nsh', '江湖')]})
        self.assertTrue(second['ok'], second)
        return first['data']['id'], second['data']['id']

    def test_general_settings_reach_every_game_and_keep_each_window(self):
        first, second = self.make_games()
        result = self.service.save_general({'preset': '流畅 1080p60', 'transcription_provider': 'local',
                                            'general_hotword_files': [vocabulary('uiux', '弹窗')]})
        self.assertTrue(result['ok'], result)
        presets = self.service._cfg['presets']
        self.assertEqual({presets[first]['preset'], presets[second]['preset']}, {'流畅 1080p60'})
        self.assertEqual({presets[first]['transcription_provider'], presets[second]['transcription_provider']}, {'local'})
        self.assertEqual(presets[first]['window'], 'window-id')
        self.assertEqual(presets[second]['window'], 'other-window')
        self.assertEqual(ids(presets[first]['hotword_files']), ['uiux', 'yanyun'])
        self.assertEqual(ids(presets[second]['hotword_files']), ['uiux', 'nsh'])
        self.assertIn('弹窗', presets[second]['hotwords'])
        # The active game's merged values are what recording reads.
        self.assertEqual(self.service._cfg['preset'], '流畅 1080p60')

    def test_replacing_the_general_vocabulary_keeps_game_vocabularies(self):
        first, _ = self.make_games()
        self.assertTrue(self.service.save_general({'general_hotword_files': [vocabulary('uiux', '弹窗')]})['ok'])
        self.assertTrue(self.service.save_general({'general_hotword_files': [vocabulary('terms', '页签')]})['ok'])
        self.assertEqual(ids(self.service._cfg['presets'][first]['hotword_files']), ['terms', 'yanyun'])

    def test_game_save_keeps_the_shared_vocabulary(self):
        first, _ = self.make_games()
        self.assertTrue(self.service.save_general({'general_hotword_files': [vocabulary('uiux', '弹窗')]})['ok'])
        result = self.service.save_preset({'name': '燕云十六声', 'game_hotword_files': []}, first)
        self.assertTrue(result['ok'], result)
        self.assertEqual(ids(self.service._cfg['presets'][first]['hotword_files']), ['uiux'])

    def test_first_setup_keeps_a_vocabulary_added_under_general_as_general(self):
        # First-use wizard: 通用词库 sits on 设备与转写, the whole setup is saved with the first game.
        self.service._cfg.update(presets={}, active_preset_id=None)
        shared = [vocabulary('uiux', '弹窗'), vocabulary('team', '页签')]
        result = self.service.save_preset({'name': '燕云十六声', 'vault': str(self.root / 'first-library'), 'hotword_files': [*shared, vocabulary('yanyun', '奇术')],
                                           'general_hotword_files': shared})
        self.assertTrue(result['ok'], result)
        self.assertEqual(ids(self.service._general_files()), ['uiux', 'team'])
        self.assertEqual(ids(self.service._game_files(self.service._cfg)), ['yanyun'])

    def test_a_game_save_cannot_replace_the_general_vocabulary_once_games_exist(self):
        first, _ = self.make_games()
        result = self.service.save_preset({'name': '燕云十六声', 'general_hotword_files': [vocabulary('uiux', '弹窗')]}, first)
        self.assertFalse(result['ok'])
        self.assertIn('通用', result['error'])

    def test_general_save_refuses_game_fields(self):
        self.make_games()
        result = self.service.save_general({'window': 'other-window'})
        self.assertFalse(result['ok'])
        self.assertIn('不支持', result['error'])

    def test_monitor_source_turns_input_recording_off_everywhere(self):
        first, second = self.make_games()
        result = self.service.save_general({'source': '整个显示器', 'monitor': 'monitor-id', 'record_inputs': True})
        self.assertTrue(result['ok'], result)
        presets = self.service._cfg['presets']
        self.assertFalse(presets[first]['record_inputs'])
        self.assertFalse(presets[second]['record_inputs'])


class DigestTests(unittest.TestCase):
    def test_quote_prefers_obstacle_high_confidence_verbatim(self):
        said = lambda text, start=1.0: [{'kind': 'quote', 'text': text, 'start': start}]
        result = {'events': [{'title': '活动一'}, {'title': '活动二'}, {'title': '活动三'}], 'instances': [
            {'id': 'i1', 'kind': 'confusion', 'confidence': 'high', 'said': said('这个图标是什么意思啊？')},
            {'id': 'i2', 'kind': 'obstacle', 'confidence': 'medium', 'said': said('按了没有任何反应啊')},
            {'id': 'i3', 'kind': 'obstacle', 'confidence': 'high', 'said': said('嗯，按了没有任何反应')},
            {'id': 'i4', 'kind': 'obstacle', 'confidence': 'high', 'said': said('入口到底藏在哪里了呢', 42.5)},
            {'id': 'i5', 'kind': 'positive', 'confidence': 'high', 'said': said('这个设计还挺好的嘛')},
        ]}
        digest = _digest(result)
        self.assertEqual(digest['quote'], {'text': '入口到底藏在哪里了呢', 'at': 42.5, 'kind': 'obstacle', 'instance': 'i4'})
        self.assertEqual(digest['kinds'], {'confusion': 1, 'obstacle': 3, 'positive': 1})
        self.assertEqual(digest['event_titles'], ['活动一', '活动二'])

    def test_no_quote_when_nothing_qualifies(self):
        self.assertIsNone(_digest({'events': [], 'instances': [
            {'kind': 'obstacle', 'confidence': 'high', 'said': [{'text': '太短'}]}]})['quote'])


if __name__ == '__main__':
    unittest.main()
