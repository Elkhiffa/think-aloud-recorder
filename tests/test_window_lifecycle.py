"""Window lifecycle units; native last-window exit is tested separately on Windows."""
import threading
import unittest
from unittest.mock import Mock
from window_manager import WindowManager


class Event:
    def __iadd__(self, handler):
        self.handler = handler
        return self


class LifecycleTests(unittest.TestCase):
    def setup_manager(self):
        service, window = Mock(), Mock()
        window.events.closing = Event()
        window.events.closed = Event()
        manager = WindowManager(service, Mock())
        manager.bind_main(window)
        return manager, service, window

    def test_idle_main_closes_without_closing_other_windows(self):
        manager, service, window = self.setup_manager()
        service.close_allowed.return_value = True
        other = Mock()
        manager._viewers['review'] = other
        self.assertTrue(manager.close_main())
        other.destroy.assert_not_called()
        window.minimize.assert_not_called()

    def test_busy_close_waits_for_saving_then_closes_never_minimizes(self):
        manager, service, window = self.setup_manager()
        service.close_allowed.return_value = False
        service.close_reason.return_value = 'Synthetic recording'
        entered, release, destroyed = threading.Event(), threading.Event(), threading.Event()
        service.finish_for_close.side_effect = lambda: (entered.set(), release.wait(2))
        window.create_confirmation_dialog.return_value = True
        window.destroy.side_effect = destroyed.set
        try:
            self.assertFalse(manager.close_main())
            self.assertTrue(entered.wait(1))
            window.destroy.assert_not_called()
            self.assertFalse(manager.close_main())
            window.create_confirmation_dialog.assert_called_once()
            release.set()
            self.assertTrue(destroyed.wait(1))
            window.minimize.assert_not_called()
        finally:
            release.set()

    def test_cancel_keeps_work_and_window(self):
        manager, service, window = self.setup_manager()
        window.create_confirmation_dialog.return_value = False
        manager._confirm_close()
        window.destroy.assert_not_called()
        service.finish_for_close.assert_not_called()

    def test_closed_main_cleans_engine_once_while_review_windows_remain(self):
        manager, service, window = self.setup_manager()
        other = Mock()
        manager._viewers['review'] = other
        completed = threading.Event()
        service.shutdown.side_effect = completed.set
        window.events.closed.handler()
        self.assertTrue(completed.wait(1))
        window.events.closed.handler()
        manager._shutdown_thread.join(1)
        service.shutdown.assert_called_once_with()
        self.assertFalse(manager._shutdown_thread.daemon)
        other.destroy.assert_not_called()

    def test_rejected_main_close_does_not_schedule_engine_cleanup(self):
        manager, service, window = self.setup_manager()
        service.close_allowed.return_value = False
        window.create_confirmation_dialog.return_value = False
        self.assertFalse(manager.close_main())
        self.assertIsNone(manager._shutdown_thread)
        service.shutdown.assert_not_called()


if __name__ == '__main__':
    unittest.main()
