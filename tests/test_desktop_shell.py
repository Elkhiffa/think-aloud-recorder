"""Shell tests: no real window, capture, user configuration, or network."""
import threading
from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

import app
from pathlib import Path
from tempfile import TemporaryDirectory


class DesktopShellTests(unittest.TestCase):
    def test_second_instance_cannot_acquire_same_lock(self):
        with TemporaryDirectory() as d:
            with app.instance_lock(Path(d)):
                with self.assertRaisesRegex(RuntimeError, "已经运行"):
                    with app.instance_lock(Path(d)):
                        self.fail("second instance admitted")
            with app.instance_lock(Path(d)):
                pass

    def test_shell_uses_local_ui_native_frame_and_webview2(self):
        webview = Mock()
        webview.settings = {}
        service_module = Mock()
        window = webview.create_window.return_value
        # pywebview event supports += callback; model that behavior for the shell.
        class Event:
            def __init__(self):
                self.handlers = []
            def __iadd__(self, handler):
                self.handlers.append(handler)
                return self
            def fire(self):
                for handler in self.handlers:
                    handler()
        window.events.closing = Event()
        window.events.closed = Event()
        window.events.loaded = Event()
        with patch.dict('sys.modules', {'webview': webview, 'desktop_service': service_module}), \
                patch.object(app, 'instance_lock', return_value=nullcontext()), \
                patch('update_installer.ensure_launch_allowed') as launch_guard, \
                patch('update_installer.acknowledge_start') as acknowledge:
            def native_loop(**kwargs):
                acknowledge.assert_not_called()
                window.events.loaded.fire()
            webview.start.side_effect = native_loop
            self.assertEqual(app.main(), 0)
            root = Path(app.__file__).resolve().parent
            launch_guard.assert_called_once_with(root)
            acknowledge.assert_called_once_with(root)
        kwargs = webview.create_window.call_args.kwargs
        self.assertTrue(kwargs['url'].startswith('file:///'))
        self.assertEqual(kwargs['min_size'], (720, 600))
        self.assertFalse(kwargs['frameless'])
        self.assertEqual(webview.start.call_args.kwargs['gui'], 'edgechromium')
        service_module.DesktopService.return_value.set_window.assert_called_once_with(window)
        service_module.DesktopService.return_value.shutdown.assert_called_once_with()

    def test_initial_window_fits_monitor_work_area(self):
        for size, work_area, expected in [
            ((3440, 1440), (3440, 1392), (920, 1040)),
            ((1366, 768), (1366, 728), (920, 680)),
            ((800, 600), (800, 552), (768, 504)),
        ]:
            with self.subTest(size=size):
                screen = SimpleNamespace(width=size[0], height=size[1],
                                         frame=SimpleNamespace(Width=work_area[0], Height=work_area[1]))
                options = app.main_window_options(SimpleNamespace(screens=[screen]))
                self.assertEqual((options['width'], options['height']), expected)
                self.assertLessEqual(options['min_size'][0], options['width'])
                self.assertLessEqual(options['min_size'][1], options['height'])
                self.assertIs(options['screen'], screen)
        class UnavailableScreens:
            @property
            def screens(self):
                raise RuntimeError('monitor lookup unavailable')
        self.assertEqual(app.main_window_options(UnavailableScreens()),
                         dict(width=920, height=1040, min_size=(720, 600)))


if __name__ == '__main__':
    unittest.main()
