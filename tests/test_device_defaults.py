"""Synthetic defaults/refresh checks; never start OBS or read private settings."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import ctypes
import threading
import unittest
from unittest.mock import MagicMock, patch

import desktop_service as bridge
import recorder


def item(value, enabled=True):
    return dict(itemName='Synthetic ' + value, itemValue=value, itemEnabled=enabled)


class NativePrimaryMonitorTests(unittest.TestCase):
    def native(self, *, interface='primary-interface', enumerate_ok=True):
        def enum_monitors(_dc, _rect, callback, data):
            callback(1, None, None, data)
            callback(2, None, None, data)
            return enumerate_ok

        def get_info(monitor, pointer):
            pointer._obj.dwFlags = 1 if monitor == 2 else 0
            pointer._obj.szDevice = r'\\.\DISPLAY2' if monitor == 2 else r'\\.\DISPLAY1'
            return True

        def enum_devices(name, index, pointer, flags):
            self.assertEqual((name, index, flags), (r'\\.\DISPLAY2', 0, 1))
            pointer._obj.DeviceID = interface
            return bool(interface)

        return SimpleNamespace(EnumDisplayMonitors=MagicMock(side_effect=enum_monitors),
            GetMonitorInfoW=MagicMock(side_effect=get_info),
            EnumDisplayDevicesW=MagicMock(side_effect=enum_devices))

    def test_windows_primary_flag_not_enumeration_order_identifies_display(self):
        with patch.object(ctypes, 'WinDLL', return_value=self.native()):
            self.assertEqual(recorder.primary_monitor_ids(), ('primary-interface', r'\\.\DISPLAY2'))

    def test_primary_display_name_remains_a_candidate_if_interface_lookup_fails(self):
        with patch.object(ctypes, 'WinDLL', return_value=self.native(interface='')):
            self.assertEqual(recorder.primary_monitor_ids(), (r'\\.\DISPLAY2',))

    def test_native_lookup_failure_returns_no_guessed_monitor(self):
        with patch.object(ctypes, 'WinDLL', side_effect=OSError('synthetic native failure')):
            self.assertEqual(recorder.primary_monitor_ids(), ())
        with patch.object(ctypes, 'WinDLL', return_value=self.native(enumerate_ok=False)):
            self.assertEqual(recorder.primary_monitor_ids(), ())


class DeviceDefaultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        cfg = dict(vault=str(self.root / 'library'), game='Synthetic project',
                   configured=False, games={}, transcription_provider='qwen')
        model = MagicMock()
        model.status.return_value = dict(state='missing', model='large-v3', path=None)
        patches = [patch.object(bridge, 'load_settings', return_value=cfg),
                   patch.object(bridge, 'ModelManager', return_value=model),
                   patch.object(bridge.DesktopService, '_startup', return_value=None),
                   patch.object(bridge.DesktopService, '_monitor_loop', return_value=None),
                   patch.object(bridge.DesktopService, '_visible_session_paths', return_value={}),
                   patch.object(bridge.DesktopService, '_has_key', return_value=False),
                   patch.object(recorder, 'primary_monitor_ids', return_value=('primary-ID',))]
        for mocked in patches:
            mocked.start()
            self.addCleanup(mocked.stop)
        self.service = bridge.DesktopService(self.root)
        self.wait()
        self.addCleanup(self.service._closed.set)
        self.devices = dict(monitor=[item('secondary-id'), item('PRIMARY-id')],
                            mic=[item('usb-mic'), item('default')], window=[])

    def wait(self):
        self.service._job.join(5)
        self.assertFalse(self.service._job.is_alive(), 'synthetic worker did not finish')

    def state(self):
        result = self.service.get_state()
        self.assertTrue(result['ok'], result)
        return result['data']

    def test_defaults_match_real_enabled_values_case_insensitively_not_first_item(self):
        self.service._cache_devices(self.devices)
        state = self.state()
        self.assertEqual(state['device_defaults'], dict(monitor='PRIMARY-id', mic='default'))
        self.assertIsNone(state['device_refresh'])
        state['device_defaults']['monitor'] = 'changed snapshot'
        self.assertEqual(self.state()['device_defaults']['monitor'], 'PRIMARY-id')

    def test_unknown_primary_does_not_fall_back_to_first_monitor_or_obs_dummy(self):
        devices = deepcopy(self.devices)
        devices['monitor'].append(item('DUMMY'))
        for native in ((), ('not-listed',)):
            with self.subTest(native=native), patch.object(recorder, 'primary_monitor_ids', return_value=native):
                self.service._cache_devices(devices)
                self.assertEqual(self.state()['device_defaults']['monitor'], '')

    def test_disabled_or_missing_system_defaults_are_not_suggested(self):
        for devices in (dict(monitor=[item('PRIMARY-id', False)], mic=[item('default', False)], window=[]),
                        dict(monitor=[], mic=[item('usb-mic')], window=[])):
            self.service._cache_devices(devices)
            self.assertEqual(self.state()['device_defaults'], dict(monitor='', mic=''))

    def test_native_query_failure_does_not_break_device_cache(self):
        with patch.object(recorder, 'primary_monitor_ids', side_effect=OSError('synthetic failure')):
            self.service._cache_devices(self.devices)
        state = self.state()
        self.assertEqual(state['devices'], self.devices)
        self.assertEqual(state['device_defaults'], dict(monitor='', mic='default'))

    def test_explicit_refresh_admits_one_token_then_reports_that_completion(self):
        entered, release = threading.Event(), threading.Event()
        def enumerate_devices(**_kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError('synthetic test did not release device enumeration')
            return deepcopy(self.devices)
        with patch.object(self.service, '_recover'), patch.object(self.service, '_update_readiness'), \
             patch.object(recorder, 'devices', side_effect=enumerate_devices):
            try:
                result = self.service.refresh_devices()
                self.assertTrue(result['ok'], result)
                token = result['data']['refresh_id']
                self.assertTrue(result['data']['started'])
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.state()['device_refresh'], dict(id=token, state='running', error=''))
                rejected = self.service.refresh_devices()
                self.assertFalse(rejected['ok'])
                self.assertEqual(self.state()['device_refresh']['id'], token)
            finally:
                release.set()
                self.wait()
        self.assertEqual(self.state()['device_refresh'], dict(id=token, state='succeeded', error=''))
        self.assertEqual(self.state()['device_defaults'], dict(monitor='PRIMARY-id', mic='default'))
        # Ordinary readiness calls this cache method; it must not create or
        # overwrite an explicit user action's completion acknowledgement.
        self.service._cache_devices(dict(monitor=[], mic=[], window=[]))
        self.assertEqual(self.state()['device_refresh'], dict(id=token, state='succeeded', error=''))

    def test_failed_refresh_stays_failed_when_later_readiness_finds_devices(self):
        with patch.object(self.service, '_recover'), patch.object(self.service, '_update_readiness'), \
             patch.object(recorder, 'devices', side_effect=RuntimeError('Synthetic OBS unavailable')):
            result = self.service.refresh_devices()
            self.assertTrue(result['ok'], result)
            self.wait()
        token = result['data']['refresh_id']
        self.assertEqual(self.state()['device_refresh'],
                         dict(id=token, state='failed', error='Synthetic OBS unavailable'))
        self.service._cache_devices(self.devices)
        self.assertEqual(self.state()['device_refresh']['state'], 'failed')
        self.assertEqual(self.state()['device_refresh']['id'], token)

    def test_rejected_refresh_preserves_previous_result(self):
        previous = dict(id='earlier-refresh', state='failed', error='earlier failure')
        self.service._device_refresh = deepcopy(previous)
        self.service._activity['busy'] = True
        with patch.object(recorder, 'devices') as devices:
            result = self.service.refresh_devices()
        self.assertFalse(result['ok'])
        self.assertNotIn('data', result)
        devices.assert_not_called()
        self.assertEqual(self.state()['device_refresh'], previous)


if __name__ == '__main__':
    unittest.main()
