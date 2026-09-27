"""Availability checks must not create capture sources or activate audio clients."""
import ctypes as C
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import unittest

import device_inventory as inventory
import recorder


class InventoryTests(unittest.TestCase):
    def audio_fixture(self, *, count=1, initialize=0, fail_id=False):
        buffers = [C.create_unicode_buffer('{0.0.1}.endpoint'), C.create_unicode_buffer('合成麦克风')]
        calls = []
        ole = SimpleNamespace(**{name: MagicMock() for name in (
            'CoInitializeEx', 'CoUninitialize', 'CoCreateInstance', 'CoTaskMemFree', 'PropVariantClear')})
        ole.CoInitializeEx.return_value = initialize
        def create(_cls, _outer, _ctx, _iid, pointer):
            pointer._obj.value = 1
            return 0
        ole.CoCreateInstance.side_effect = create
        def com(pointer, index, args=(), result=None):
            identity = pointer.value
            def invoke(_self, *values):
                calls.append((identity, index))
                if index == 2:
                    return 0
                if (identity, index) == (1, 3):
                    self.assertEqual(values[:2], (1, 1))  # Capture endpoints, active only.
                    values[2]._obj.value = 2
                elif (identity, index) == (1, 4):
                    self.assertEqual(values[:2], (1, 2))  # Communications default.
                    values[2]._obj.value = 3 if count else None
                    return 0 if count else -1
                elif (identity, index) == (2, 3):
                    values[0]._obj.value = count
                elif (identity, index) == (2, 4):
                    values[1]._obj.value = 10
                elif (identity, index) == (10, 5):
                    if fail_id:
                        return -1
                    values[0]._obj.value = C.addressof(buffers[0])
                elif (identity, index) == (10, 4):
                    self.assertEqual(values[0], 0)  # STGM_READ only.
                    values[1]._obj.value = 20
                elif (identity, index) == (20, 5):
                    variant = values[1]._obj
                    variant.vt = 31
                    variant.data.pointer = C.addressof(buffers[1])
                else:
                    self.fail(f'Unexpected native call, including any capture activation: {(identity,index)}')
                return 0
            return invoke
        return ole, com, calls

    def test_microphones_read_stable_ids_and_names_without_capture_activation(self):
        ole, com, calls = self.audio_fixture()
        with patch.object(inventory, '_dll', return_value=ole), patch.object(inventory, '_com', side_effect=com):
            self.assertEqual(inventory.microphones(), [inventory.item('默认麦克风', 'default'),
                inventory.item('合成麦克风', '{0.0.1}.endpoint')])
        self.assertEqual({p for p, method in calls if method == 2}, {1, 2, 3, 10, 20})
        ole.CoUninitialize.assert_called_once()
        ole.CoTaskMemFree.assert_called_once()
        ole.PropVariantClear.assert_called_once()

    def test_microphone_failure_releases_interfaces_and_does_not_fake_availability(self):
        ole, com, calls = self.audio_fixture(fail_id=True)
        with patch.object(inventory, '_dll', return_value=ole), patch.object(inventory, '_com', side_effect=com):
            with self.assertRaises(OSError):
                inventory.microphones()
        self.assertEqual({p for p, method in calls if method == 2}, {1, 2, 10})
        ole.CoUninitialize.assert_called_once()

    def test_missing_microphone_does_not_offer_default_and_sta_is_not_uninitialized(self):
        ole, com, _calls = self.audio_fixture(count=0, initialize=-2147417850)
        with patch.object(inventory, '_dll', return_value=ole), patch.object(inventory, '_com', side_effect=com):
            self.assertEqual(inventory.microphones(), [])
        ole.CoUninitialize.assert_not_called()

    def test_inventory_cancellation_stops_before_next_device_query(self):
        calls = []
        def check():
            calls.append('check')
            if len(calls) == 2:
                raise RuntimeError('cancelled')
        with patch.object(inventory, 'microphones', return_value=[]) as mic, \
             patch.object(inventory, 'windows') as windows, patch.object(inventory, 'monitors') as monitors:
            with self.assertRaisesRegex(RuntimeError, 'cancelled'):
                inventory.devices(check)
        mic.assert_called_once()
        windows.assert_not_called()
        monitors.assert_not_called()

    def test_window_ids_match_obs_escaping_and_keep_ambiguous_duplicate_rows(self):
        encoded = inventory.window_id('游戏:#22', 'class:#3A', 'game.exe')
        self.assertEqual(encoded, '游戏#3A#2222:class#3A#223A:game.exe')
        rows = [inventory.item('one', encoded), inventory.item('two', encoded)]
        self.assertEqual(recorder.resolve_window_selection(encoded, rows)['status'], 'ambiguous')

    def test_explicit_refresh_reads_inventory_without_mutating_obs_sources(self):
        client = MagicMock()
        expected = {'mic': [], 'window': [], 'monitor': []}
        with patch.object(recorder, 'obs_connection') as connection, \
             patch.object(recorder, 'ensure_idle') as idle, \
             patch.object(inventory, 'devices', return_value=expected):
            connection.return_value.__enter__.return_value = client
            self.assertEqual(recorder.devices(), expected)
        self.assertEqual(idle.call_count, 2)
        client.create_input.assert_not_called()
        client.remove_input.assert_not_called()
        client.set_input_settings.assert_not_called()

    def test_monitor_identity_uses_interface_id_and_falls_back_to_display_name(self):
        def enumerate_monitors(_dc, _rect, callback, data):
            callback(1, None, None, data)
            callback(2, None, None, data)
            return True
        def info(handle, pointer):
            pointer._obj.szDevice = 'DISPLAY' + str(handle)
            pointer._obj.rcMonitor.right = 3440
            pointer._obj.rcMonitor.bottom = 1440
            pointer._obj.dwFlags = int(handle == 1)
            return True
        def display(name, index, pointer, flags):
            self.assertEqual((index, flags), (0, 1))
            pointer._obj.DeviceID = 'stable-monitor-interface'
            return name == 'DISPLAY1'
        user = SimpleNamespace(EnumDisplayMonitors=MagicMock(side_effect=enumerate_monitors),
            GetMonitorInfoW=MagicMock(side_effect=info), EnumDisplayDevicesW=MagicMock(side_effect=display))
        with patch.object(inventory, '_dll', return_value=user):
            rows = inventory.monitors()
        self.assertEqual([r['itemValue'] for r in rows], ['stable-monitor-interface', 'DISPLAY2'])
        self.assertIn('主显示器', rows[0]['itemName'])

    def test_window_inventory_filters_hidden_tools_cloaked_and_disappearing_processes(self):
        def enumerate_windows(callback, data):
            for handle in range(1, 7):
                callback(handle, data)
            return True
        def pid(handle, pointer):
            pointer._obj.value = 1000 + handle
            return 1
        def text(handle, buffer, length):
            buffer.value = 'Synthetic:game#'
            return len(buffer.value)
        def cls(handle, buffer, length):
            buffer.value = 'SyntheticClass'
            return len(buffer.value)
        def cloak(handle, _property, pointer, size):
            pointer._obj.value = int(handle == 4)
            return 0
        user = SimpleNamespace(EnumWindows=MagicMock(side_effect=enumerate_windows),
            IsWindowVisible=MagicMock(side_effect=lambda h: h != 2),
            GetWindowLongPtrW=MagicMock(side_effect=lambda h, k: 0x80 if h == 3 and k == -20 else 0),
            GetWindowTextLengthW=MagicMock(return_value=15), GetWindowTextW=MagicMock(side_effect=text),
            GetClassNameW=MagicMock(side_effect=cls), GetWindowThreadProcessId=MagicMock(side_effect=pid))
        dwm = SimpleNamespace(DwmGetWindowAttribute=MagicMock(side_effect=cloak))
        def process(pid):
            if pid == 1005:
                raise inventory.psutil.NoSuchProcess(pid)
            return SimpleNamespace(name=lambda: 'game.exe')
        with patch.object(inventory, '_dll', side_effect=[user, dwm]), \
             patch.object(inventory.psutil, 'Process', side_effect=process):
            rows = inventory.windows()
        # Preserve identical identities for two actual windows, so the existing
        # selection resolver can reject ambiguity instead of silently choosing.
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['itemValue'], 'Synthetic#3Agame#22:SyntheticClass:game.exe')
        self.assertEqual(rows[0], rows[1])


if __name__ == '__main__':
    unittest.main()
