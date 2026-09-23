"""Opt-in native lifecycle smoke; hidden owned target never gains foreground.

Run explicitly with THINK_ALOUD_NATIVE_INPUT_SMOKE=1. Normal discovery skips it.
No SendInput, no user window target, no actual keyboard/button acceptance claim.
"""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@unittest.skipUnless(os.name == 'nt' and os.environ.get('THINK_ALOUD_NATIVE_INPUT_SMOKE') == '1',
                     'Explicit opt-in required for hidden-target native lifecycle smoke')
class NativeLifecycleSmoke(unittest.TestCase):
    def test_hidden_target_never_records_outside_input_and_cleans_up(self):
        import psutil
        from input_capture import InputRecorder
        from input_capture_devices import resolve_sdl
        from input_capture_windows import RawDevice, TargetWindow, WindowsInputSource, winapi
        root = Path(__file__).resolve().parents[1]
        user, kernel = winapi()
        user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
            C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
        user.CreateWindowExW.restype = W.HWND
        user.DestroyWindow.argtypes, user.DestroyWindow.restype = [W.HWND], W.BOOL
        user.GetRegisteredRawInputDevices.argtypes = [C.POINTER(RawDevice), C.POINTER(W.UINT), W.UINT]
        user.GetRegisteredRawInputDevices.restype = W.UINT

        def registrations():
            count = W.UINT()
            result = user.GetRegisteredRawInputDevices(None, C.byref(count), C.sizeof(RawDevice))
            self.assertNotEqual(result, 0xffffffff)
            if not count.value:
                return []
            devices = (RawDevice * count.value)()
            result = user.GetRegisteredRawInputDevices(devices, C.byref(count), C.sizeof(RawDevice))
            self.assertNotEqual(result, 0xffffffff)
            return sorted((d.page, d.usage, d.flags, int(d.target or 0)) for d in devices[:count.value])

        before = registrations()
        hwnd = user.CreateWindowExW(0, 'STATIC', 'ThinkAloud owned hidden smoke target',
            0, 0, 0, 100, 100, None, None, kernel.GetModuleHandleW(None), None)
        self.assertTrue(hwnd)
        capture = None
        observed = []
        try:
            self.assertFalse(user.IsWindowVisible(hwnd))
            self.assertNotEqual(user.GetForegroundWindow(), hwnd)
            target = TargetWindow(int(hwnd), os.getpid(), psutil.Process().create_time(), 'Static')
            source = WindowsInputSource(target, resolve_sdl(root))
            with TemporaryDirectory(prefix='think-aloud-hidden-native-') as folder:
                capture = InputRecorder(folder, lambda: source, flush_interval=.2)
                capture.start()
                during = registrations()
                self.assertTrue(any(d[0:2] == (1, 2) for d in during))
                self.assertTrue(any(d[0:2] == (1, 6) for d in during))
                for _ in range(12):
                    self.assertFalse(user.IsWindowVisible(hwnd))
                    self.assertNotEqual(user.GetForegroundWindow(), hwnd)
                    self.assertFalse(source._eligible)
                    self.assertEqual(capture.snapshot()['intervals'], [])
                    time.sleep(.1)
                observed = sorted({item['device'] for item in source._controllers.controllers.values()})
                result = capture.stop()
                self.assertFalse(source._thread.is_alive())
                self.assertFalse(source._observer.thread.is_alive())
                self.assertTrue(source._observer.unhooked)
                self.assertGreater(source._observer.markers_acknowledged, 1)
                self.assertEqual(result['state'], 'complete')
                self.assertEqual(result['intervals'], [])
                self.assertTrue(any(g['type'] == 'focus' for g in result['gaps']))
                self.assertEqual(json.loads(Path(folder, 'input-events.json').read_text(encoding='utf-8'))['intervals'], [])
                self.assertEqual(registrations(), before)
                library = C.CDLL(str(resolve_sdl(root)))
                library.SDL_WasInit.argtypes, library.SDL_WasInit.restype = [C.c_uint32], C.c_uint32
                self.assertEqual(library.SDL_WasInit(0x2000 | 0x4000), 0)
                evidence = {'test': 'hidden-owned-target-native-lifecycle', 'passed': True,
                    'foreground_target_ever': False, 'persisted_input_intervals': 0,
                    'duration_seconds': result['duration'], 'registered_keyboard_and_mouse': True,
                    'raw_input_registrations_restored': True, 'source_thread_stopped': True, 'foreground_observer_stopped': True, 'ordered_marker_acknowledgements': source._observer.markers_acknowledged,
                    'sdl_subsystems_released': True, 'controller_types_enumerated': observed,
                    'hardware_button_acceptance': 'not tested', 'video_sync_acceptance': 'not tested'}
                evidence_path = root / 'work' / 'input-native-smoke.json'
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                evidence_path.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
                print(json.dumps(evidence))
        finally:
            if capture:
                capture.stop()
            user.DestroyWindow(hwnd)


if __name__ == '__main__':
    unittest.main()
