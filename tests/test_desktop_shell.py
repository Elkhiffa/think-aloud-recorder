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

    def test_native_close_is_cancelled_for_active_work(self):
        minimized = threading.Event()
        window = Mock()
        window.minimize.side_effect = minimized.set
        service = Mock()
        service.close_allowed.return_value = False
        self.assertFalse(app.build_close_guard(service, window)())
        self.assertTrue(minimized.wait(1))
        service.close_allowed.assert_called_once_with()

    def test_close_failure_never_allows_unconfirmed_shutdown(self):
        service = Mock()
        service.close_allowed.side_effect = RuntimeError('service unavailable')
        self.assertFalse(app.build_close_guard(service, Mock())())

    def test_only_confirmed_idle_allows_close(self):
        for response in (None, {}, {'ok': False}, {'ok': True, 'data': {}}, 'true', 1):
            with self.subTest(response=response):
                self.assertFalse(app._close_is_allowed(response))
        service, window = Mock(), Mock()
        service.close_allowed.return_value = True
        self.assertTrue(app.build_close_guard(service, window)())
        window.minimize.assert_not_called()

    def test_shell_uses_local_ui_native_frame_and_webview2(self):
        webview = Mock()
        service_module = Mock()
        window = webview.create_window.return_value
        window.events.closing = []
        # pywebview event supports += callback; model that behavior for the shell.
        class Event:
            def __iadd__(self, handler):
                self.handler = handler
                return self
        window.events.closing = Event()
        with patch.dict('sys.modules', {'webview': webview, 'desktop_service': service_module}), \
                patch.object(app, 'instance_lock', return_value=nullcontext()):
            self.assertEqual(app.main(), 0)
        kwargs = webview.create_window.call_args.kwargs
        self.assertTrue(kwargs['url'].startswith('file:///'))
        self.assertEqual(kwargs['min_size'], (820, 620))
        self.assertFalse(kwargs['frameless'])
        self.assertEqual(webview.start.call_args.kwargs['gui'], 'edgechromium')
        service_module.DesktopService.return_value.set_window.assert_called_once_with(window)


if __name__ == '__main__':
    unittest.main()
