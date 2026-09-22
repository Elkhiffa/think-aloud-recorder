"""Shell tests: no real window, capture, user configuration, or network."""
import threading
from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch

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
        window.events.closing = []
        # pywebview event supports += callback; model that behavior for the shell.
        class Event:
            def __iadd__(self, handler):
                self.handler = handler
                return self
        window.events.closing = Event()
        window.events.closed = Event()
        with patch.dict('sys.modules', {'webview': webview, 'desktop_service': service_module}), \
                patch.object(app, 'instance_lock', return_value=nullcontext()):
            self.assertEqual(app.main(), 0)
        kwargs = webview.create_window.call_args.kwargs
        self.assertTrue(kwargs['url'].startswith('file:///'))
        self.assertEqual(kwargs['min_size'], (820, 620))
        self.assertFalse(kwargs['frameless'])
        self.assertEqual(webview.start.call_args.kwargs['gui'], 'edgechromium')
        service_module.DesktopService.return_value.set_window.assert_called_once_with(window)
        service_module.DesktopService.return_value.shutdown.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
