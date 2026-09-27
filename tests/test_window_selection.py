"""Synthetic window selection checks; no OBS process or native capture is used."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

import recorder


def window(value, name='Synthetic game', enabled=True):
    return dict(itemValue=value, itemName=name, itemEnabled=enabled)


class WindowSelectionTests(unittest.TestCase):
    saved = 'Game:OldClass:game.exe'

    def test_unique_exact_match_has_priority_over_other_same_executable_windows(self):
        result = recorder.resolve_window_selection(self.saved, [
            window('Game:OtherClass:game.exe'), window(self.saved, 'Chosen window'),
            window('Another window:OtherClass:game.exe')])
        self.assertEqual(result, dict(requested=self.saved, resolved=self.saved,
            status='matched', matched_by='exact', itemName='Chosen window'))

    def test_changed_class_matches_unique_title_and_executable(self):
        current = 'Game:NewRandomClass:GAME.EXE'
        result = recorder.resolve_window_selection(self.saved, [
            window('Launcher:OtherClass:game.exe'), window(current)])
        self.assertEqual((result['resolved'], result['matched_by']), (current, 'exe_title'))

    def test_changed_title_and_class_match_only_one_executable_candidate(self):
        current = 'Game - Chapter 2:NewClass:GAME.EXE'
        result = recorder.resolve_window_selection(self.saved, [
            window(current), window('Game:OldClass:different.exe')])
        self.assertEqual((result['resolved'], result['matched_by']), (current, 'exe_unique'))

    def test_same_class_alone_does_not_break_executable_ambiguity(self):
        result = recorder.resolve_window_selection(self.saved, [
            window('Chapter 1:OldClass:game.exe'), window('Chapter 2:NewClass:game.exe')])
        self.assertEqual((result['status'], result['resolved'], result['matched_by']),
                         ('ambiguous', '', 'exe_unique'))

    def test_duplicate_exact_rows_are_ambiguous_and_not_deduplicated(self):
        result = recorder.resolve_window_selection(self.saved, [
            window(self.saved), window(self.saved), window('Other:Class:game.exe')])
        self.assertEqual((result['status'], result['matched_by']), ('ambiguous', 'exact'))
        self.assertEqual(result['resolved'], '')

    def test_same_title_candidates_fail_at_that_tier(self):
        result = recorder.resolve_window_selection(self.saved, [
            window('Game:NewClassA:game.exe'), window('Game:NewClassB:game.exe'),
            window('Other:Class:game.exe')])
        self.assertEqual((result['status'], result['matched_by']), ('ambiguous', 'exe_title'))

    def test_disabled_exact_and_disabled_other_candidates_do_not_count(self):
        current = 'Game:NewClass:game.exe'
        items = [window(self.saved, enabled=False), window(current),
                 window('Other:Class:game.exe', enabled=False)]
        self.assertEqual(recorder.resolve_window_selection(self.saved, items)['resolved'], current)
        self.assertEqual(recorder.resolve_window_selection(self.saved, items[:1])['status'], 'missing')

    def test_opaque_exact_identifier_works_but_never_falls_back(self):
        self.assertEqual(recorder.resolve_window_selection('window-id', [window('window-id')])['matched_by'], 'exact')
        self.assertEqual(recorder.resolve_window_selection('window-id', [window(self.saved)])['status'], 'missing')

    def test_empty_invalid_requested_values_cannot_select_an_unrelated_window(self):
        for requested in (None, 42, {}, [], '', ' ', ':Class:game.exe', 'Game::game.exe',
                          'Game:Class:', 'Game:Too:Many:game.exe'):
            with self.subTest(requested=requested):
                result = recorder.resolve_window_selection(requested, [window(self.saved), window('')])
                self.assertEqual((result['status'], result['resolved']), ('missing', ''))

    def test_invalid_candidates_and_missing_enabled_flag_are_ignored(self):
        items = [None, {}, {'itemValue': self.saved}, window(None), window(42),
                 window('Game::game.exe'), window('Game:Class:other.exe')]
        self.assertEqual(recorder.resolve_window_selection(self.saved, items)['status'], 'missing')

    def test_invalid_or_empty_lists_are_missing(self):
        for items in (None, {}, 'not a list', []):
            with self.subTest(items=items):
                self.assertEqual(recorder.resolve_window_selection(self.saved, items)['status'], 'missing')

    def test_obs_escaped_colon_and_hash_follow_native_parser(self):
        saved = 'Game#3A #223A#22:Old:game.exe'
        current = 'Game#3A #223A#22:New:GAME.EXE'
        result = recorder.resolve_window_selection(saved, [
            window(current), window('Game#3A #3A#22:Old:game.exe')])
        self.assertEqual((result['resolved'], result['matched_by']), (current, 'exe_title'))

    def test_inputs_are_not_mutated(self):
        items = [window('Game:New:game.exe')]
        before = deepcopy(items)
        recorder.resolve_window_selection(self.saved, items)
        self.assertEqual(items, before)


class WindowSceneTests(unittest.TestCase):
    saved = 'Game:OldClass:game.exe'
    current = 'Game:NewClass:game.exe'

    def config(self, vault='unused'):
        return dict(game='Synthetic', vault=vault, preset='均衡 1080p30',
                    source='游戏窗口', window=self.saved, monitor='', mic='default',
                    record_inputs=True, transcription_provider='later', language='zh')

    def client(self, window_lists):
        """Model property-list changes independently of written source settings."""
        client = MagicMock()
        sources = {}
        lists = deepcopy(window_lists)
        client.get_profile_parameter.side_effect = lambda section, key: SimpleNamespace(
            parameter_value='Advanced' if key == 'Mode' else '3')
        client.get_input_list.side_effect = lambda: SimpleNamespace(inputs=[
            dict(inputName=name) for name in sources])

        def create(scene, name, kind, settings, enabled):
            sources[name] = dict(settings=dict(settings), enabled=enabled,
                                 tracks={}, ident=len(sources) + 1)

        def update(name, settings, overlay):
            sources[name]['settings'].update(settings)

        def enable(scene, ident, enabled):
            next(source for source in sources.values() if source['ident'] == ident)['enabled'] = enabled

        def properties(name, prop):
            if prop == 'window':
                values = lists.pop(0) if len(lists) > 1 else lists[0]
            else:
                values = [window('default')]
            return SimpleNamespace(property_items=deepcopy(values))

        client.create_input.side_effect = create
        client.remove_input.side_effect = lambda name: sources.pop(name)
        client.set_input_settings.side_effect = update
        client.set_scene_item_enabled.side_effect = enable
        client.get_input_properties_list_property_items.side_effect = properties
        client.set_input_audio_tracks.side_effect = lambda name, tracks: sources[name].update(tracks=tracks)
        client.get_input_audio_tracks.side_effect = lambda name: SimpleNamespace(input_audio_tracks=sources[name]['tracks'])
        client.get_scene_item_list.side_effect = lambda scene: SimpleNamespace(scene_items=[
            dict(sourceName=name, sceneItemId=source['ident']) for name, source in sources.items()])
        client.get_record_status.return_value = SimpleNamespace(output_active=True, output_duration=100)
        client.get_scene_item_transform.return_value = SimpleNamespace(
            scene_item_transform=dict(sourceWidth=1920, sourceHeight=1080))
        return client, sources

    def test_scene_rebinds_disabled_source_before_enabling_and_updates_local_config(self):
        client, sources = self.client([[window(self.current)]])
        cfg = self.config()
        with patch.object(recorder, 'ensure_idle'), patch.object(recorder.time, 'sleep'):
            recorder.configure_scene(client, cfg)
        created = next(call for call in client.create_input.call_args_list if call.args[1] == '游戏画面')
        self.assertFalse(created.args[4])
        self.assertEqual(created.args[3]['window'], '')
        self.assertEqual(sources['游戏画面']['settings']['window'], self.current)
        self.assertTrue(sources['游戏画面']['enabled'])
        self.assertEqual(cfg['window'], self.current)
        methods = [call[0] for call in client.mock_calls]
        self.assertLess(methods.index('set_input_settings'), methods.index('set_scene_item_enabled'))
        client.start_record.assert_not_called()

    def test_ultrawide_scene_uses_actual_capture_aspect_with_bounded_encoding_size(self):
        client,_=self.client([[window(self.current)]])
        client.get_scene_item_transform.side_effect=[
            SimpleNamespace(scene_item_transform=dict(sourceWidth=0,sourceHeight=0)),
            SimpleNamespace(scene_item_transform=dict(sourceWidth=3440,sourceHeight=1440))]
        with patch.object(recorder,'ensure_idle'),patch.object(recorder.time,'sleep'):
            geometry=recorder.configure_scene(client,self.config())
        self.assertEqual(geometry,dict(source_width=3440,source_height=1440,width=1920,height=804))
        last_video=[c.args[1] for c in client.send.call_args_list if c.args[0]=='SetVideoSettings'][-1]
        self.assertEqual((last_video['baseWidth'],last_video['baseHeight']),(1920,804))
        self.assertEqual((last_video['outputWidth'],last_video['outputHeight']),(1920,804))
        transform=client.set_scene_item_transform.call_args.args[2]
        self.assertEqual(transform['boundsType'],'OBS_BOUNDS_NONE')
        self.assertAlmostEqual(transform['scaleX']*3440,1920)
        self.assertAlmostEqual(transform['scaleY']*1440,804)
        self.assertEqual(transform['alignment'],5)

    def test_unready_capture_never_silently_records_a_guessed_aspect(self):
        client,_=self.client([[window(self.current)]])
        client.get_scene_item_transform.return_value=SimpleNamespace(scene_item_transform=dict(sourceWidth=0,sourceHeight=0))
        with patch.object(recorder,'ensure_idle'),patch.object(recorder.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'画面的尺寸'):
                recorder.configure_scene(client,self.config())
        client.start_record.assert_not_called()

    def test_recording_dimensions_preserve_quality_caps_and_encoder_alignment(self):
        for sw,sh,expected in [(1920,1080,(1920,1080)),(3440,1440,(1920,804)),
                              (1080,1920,(608,1080)),(640,360,(640,360)),(1921,1081,(1920,1080))]:
            with self.subTest(source=(sw,sh)):
                w,h,fps=recorder.recording_dimensions(sw,sh,'均衡 1080p30')
                self.assertEqual((w,h),expected)
                self.assertLess(abs(w/h-sw/sh)/(sw/sh),.002)
                self.assertEqual((w%2,h%2,fps),(0,0,30))
        for invalid in (None,True,float('nan'),float('inf'),0,-1,100000):
            with self.assertRaises(ValueError):recorder.recording_dimensions(invalid,1440,'均衡 1080p30')

    def test_ambiguous_or_missing_targets_stay_disabled_and_do_not_change_config(self):
        for options in ([], [window(self.current), window('Game:ThirdClass:game.exe')]):
            with self.subTest(options=options):
                client, sources = self.client([options])
                cfg = self.config()
                with patch.object(recorder, 'ensure_idle'), patch.object(recorder.time, 'sleep'):
                    with self.assertRaises(RuntimeError):
                        recorder.configure_scene(client, cfg)
                self.assertEqual(cfg['window'], self.saved)
                self.assertFalse(sources['游戏画面']['enabled'])
                client.set_input_settings.assert_not_called()
                client.set_scene_item_enabled.assert_not_called()
                client.start_record.assert_not_called()

    def test_target_change_after_settings_update_is_rejected_without_further_fallback(self):
        for later in ([], [window('Game:ChangedAgain:game.exe')],
                      [window(self.current), window(self.current)]):
            with self.subTest(later=later):
                client, sources = self.client([[window(self.current)], later])
                cfg = self.config()
                with patch.object(recorder, 'ensure_idle'), patch.object(recorder.time, 'sleep'):
                    with self.assertRaisesRegex(RuntimeError, '准备期间'):
                        recorder.configure_scene(client, cfg)
                self.assertEqual(cfg['window'], self.saved)
                self.assertFalse(sources['游戏画面']['enabled'])
                client.set_scene_item_enabled.assert_not_called()
                client.start_record.assert_not_called()

    def test_session_video_history_and_native_preparation_share_resolved_identity(self):
        client, sources = self.client([[window(self.current)]])
        with TemporaryDirectory() as folder:
            cfg = self.config(str(Path(folder) / 'library'))
            with patch.object(recorder, 'client', return_value=client), \
                 patch.object(recorder, 'ensure_idle'), patch.object(recorder.time, 'sleep'), \
                 patch.object(recorder.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)), \
                 patch('input_capture_windows.resolve_target', return_value=object()) as target, \
                 patch('input_capture_devices.resolve_sdl', return_value='synthetic-sdl'), \
                 patch('input_capture.InputRecorder', return_value=None):
                session = recorder.Session.start(cfg)
            self.assertEqual(sources['游戏画面']['settings']['window'], self.current)
            self.assertEqual(session.meta['settings']['window'], self.current)
            self.assertEqual([call.args[0] for call in target.call_args_list], [self.current, self.current])
            self.assertEqual(cfg['window'], self.saved, 'Session.start must not mutate the caller preset')
            client.start_record.assert_called_once()

    def test_ambiguous_session_never_starts_recording_or_prepares_input_capture(self):
        client, _ = self.client([[window(self.current), window('Game:Other:game.exe')]])
        with TemporaryDirectory() as folder:
            with patch.object(recorder, 'client', return_value=client), \
                 patch.object(recorder, 'ensure_idle'), patch.object(recorder.time, 'sleep'), \
                 patch.object(recorder.shutil, 'disk_usage', return_value=SimpleNamespace(free=10*1024**3)), \
                 patch('input_capture.prepare_capture') as prepare:
                with self.assertRaisesRegex(RuntimeError, '多个匹配'):
                    recorder.Session.start(self.config(str(Path(folder) / 'library')))
            prepare.assert_not_called()
            client.start_record.assert_not_called()


if __name__ == '__main__':
    unittest.main()
