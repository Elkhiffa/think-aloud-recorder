"""Synthetic native events and read-only adapters; never lock the real desktop."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from window_manager import WindowManager, _Win32ForegroundQuery


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def fire(self, *args):
        for handler in tuple(self.handlers):
            handler(*args)


class NativeWindow:
    def __init__(self, hwnd=0x123456789):
        self.hwnd = hwnd
        self.ui_thread = threading.get_ident()
        self.handle_reads = []
        self.handle_error = None
        self.Activated = Event()
        self.Deactivate = Event()

    @property
    def Handle(self):
        self.handle_reads.append(threading.get_ident())
        if threading.get_ident() != self.ui_thread:
            raise AssertionError('WinForms Handle accessed outside the UI thread')
        if self.handle_error:
            raise self.handle_error
        return SimpleNamespace(ToInt64=lambda: self.hwnd)


class ForegroundQuery:
    def __init__(self, hwnd):
        self.foreground = hwnd
        self.valid = True
        self.desktop_available = True
        self.error = None
        self.calls = []
        self.during_query = None

    def is_foreground(self, hwnd):
        self.calls.append(hwnd)
        if self.error:
            raise self.error
        if self.during_query:
            self.during_query()
        return self.valid and self.desktop_available and self.foreground == hwnd


class Service:
    def __init__(self):
        self.probe = None
        self.notifications = []
        self.shutdown = Mock()

    def set_main_foreground_probe(self, probe):
        self.probe = probe

    def main_activation_changed(self):
        self.notifications.append(self.probe())


class MainFocusTests(unittest.TestCase):
    def setUp(self):
        self.service = Service()
        self.native = NativeWindow()
        self.query = ForegroundQuery(self.native.hwnd)
        self.session = SimpleNamespace(SessionSwitch=Event())
        self.window = SimpleNamespace(native=self.native,
            events=SimpleNamespace(before_show=Event(), closing=Event(), closed=Event()))
        self.manager = WindowManager(self.service, SimpleNamespace())
        self.query_patch = patch('window_manager._Win32ForegroundQuery', return_value=self.query)
        self.session_patch = patch('window_manager._session_switch_source', return_value=self.session)
        self.query_patch.start()
        self.session_patch.start()
        self.addCleanup(self.query_patch.stop)
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.close_main)
        self.manager.bind_main(self.window)

    def close_main(self):
        self.manager._main_closed()
        if self.manager._shutdown_thread:
            self.manager._shutdown_thread.join(1)

    def show_main(self):
        self.window.events.before_show.fire()
        self.native.Activated.fire(self.native, None)

    def switch_session(self, reason):
        self.session.SessionSwitch.fire(None, SimpleNamespace(Reason=reason))

    def test_not_ready_until_ui_thread_caches_handle_and_native_activates(self):
        self.assertFalse(self.service.probe())
        self.assertEqual(self.native.handle_reads, [])
        self.window.events.before_show.fire()
        self.assertFalse(self.service.probe())
        self.native.Activated.fire(self.native, None)
        self.assertTrue(self.service.probe())
        self.assertEqual(self.service.notifications, [True])
        self.assertEqual(self.native.handle_reads, [self.native.ui_thread])
        self.assertEqual(self.query.calls[-1], 0x123456789)

    def test_other_application_and_review_windows_are_not_main_foreground(self):
        self.show_main()
        for hwnd in (88, 99, 0):
            self.query.foreground = hwnd
            self.assertFalse(self.service.probe())
        self.query.foreground = self.native.hwnd
        self.assertTrue(self.service.probe())

    def test_deactivate_blocks_even_before_os_foreground_changes(self):
        self.show_main()
        self.native.Deactivate.fire(self.native, None)
        self.assertFalse(self.service.probe())
        self.assertEqual(self.service.notifications, [True, False])

    def test_repeated_activation_is_deduplicated_and_return_notifies_immediately(self):
        self.show_main()
        self.native.Activated.fire(self.native, None)
        self.native.Activated.fire(self.native, None)
        self.native.Deactivate.fire(self.native, None)
        self.native.Deactivate.fire(self.native, None)
        self.native.Activated.fire(self.native, None)
        self.assertEqual(self.service.notifications, [True, False, True])

    def test_missing_native_or_zero_handle_stays_closed(self):
        self.window.native = None
        self.window.events.before_show.fire()
        self.assertFalse(self.service.probe())
        self.window.native = self.native
        self.native.hwnd = 0
        self.show_main()
        self.assertFalse(self.service.probe())
        self.assertEqual(self.native.Activated.handlers, [])

    def test_handle_exception_stays_closed(self):
        self.native.handle_error = RuntimeError('Synthetic disposed form')
        self.show_main()
        self.assertFalse(self.service.probe())
        self.assertEqual(self.service.notifications, [])

    def test_invalid_handle_and_query_exception_fail_closed(self):
        self.show_main()
        self.query.valid = False
        self.assertFalse(self.service.probe())
        self.query.valid = True
        self.query.error = OSError('Synthetic Win32 failure')
        self.assertFalse(self.service.probe())

    def test_background_probe_never_reads_native_handle(self):
        self.show_main()
        self.native.handle_error = AssertionError('No later Handle reads allowed')
        results = []
        worker = threading.Thread(target=lambda: results.extend(self.service.probe() for _ in range(3)))
        worker.start()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [True, True, True])
        self.assertEqual(self.native.handle_reads, [self.native.ui_thread])

    def test_lock_blocks_stale_foreground_and_activation_events(self):
        self.show_main()
        self.switch_session('SessionLock')
        self.assertFalse(self.service.probe())
        self.native.Activated.fire(self.native, None)
        self.assertFalse(self.service.probe())
        self.assertEqual(self.service.notifications, [True, False, False])

    def test_unlock_with_other_window_foreground_does_not_admit_detection(self):
        self.show_main()
        self.switch_session('SessionLock')
        self.query.foreground = 99
        self.switch_session('SessionUnlock')
        self.assertFalse(self.service.probe())
        self.assertEqual(self.service.notifications, [True, False, False])
        self.query.foreground = self.native.hwnd
        self.native.Activated.fire(self.native, None)
        self.assertTrue(self.service.probe())
        self.assertEqual(self.service.notifications[-1], True)

    def test_unlock_requeries_cached_handle_without_assuming_foreground(self):
        self.show_main()
        self.switch_session('SessionLock')
        self.switch_session('SessionUnlock')
        self.assertTrue(self.service.probe())
        self.assertEqual(self.service.notifications, [True, False, True])
        self.assertEqual(self.native.handle_reads, [self.native.ui_thread])

    def test_session_subscription_failure_retains_input_desktop_gate(self):
        self.session_patch.stop()
        with patch('window_manager._session_switch_source', side_effect=ImportError('Synthetic unavailable .NET event')):
            self.show_main()
        self.assertTrue(self.service.probe())
        self.query.desktop_available = False
        self.assertFalse(self.service.probe())

    def test_unavailable_input_desktop_also_blocks_with_session_subscription(self):
        self.show_main()
        self.query.desktop_available = False
        self.switch_session('SessionUnlock')
        self.assertFalse(self.service.probe())
        self.assertEqual(self.service.notifications[-1], False)

    def test_partial_native_subscription_is_removed_and_fails_closed(self):
        del self.native.Deactivate
        self.window.events.before_show.fire()
        self.assertEqual(self.native.Activated.handlers, [])
        self.assertFalse(self.service.probe())

    def test_repeated_before_show_does_not_duplicate_subscriptions(self):
        self.show_main()
        self.window.events.before_show.fire()
        self.assertEqual(len(self.native.Activated.handlers), 1)
        self.assertEqual(len(self.native.Deactivate.handlers), 1)
        self.assertEqual(len(self.session.SessionSwitch.handlers), 1)
        self.assertEqual(self.native.handle_reads, [self.native.ui_thread])

    def test_close_unsubscribes_static_and_native_events_and_rejects_late_callbacks(self):
        self.show_main()
        late_activation = self.native.Activated.handlers[0]
        late_session = self.session.SessionSwitch.handlers[0]
        late_show = self.window.events.before_show.handlers[0]
        self.close_main()
        self.assertFalse(self.service.probe())
        self.assertEqual(self.native.Activated.handlers, [])
        self.assertEqual(self.native.Deactivate.handlers, [])
        self.assertEqual(self.session.SessionSwitch.handlers, [])
        self.assertEqual(self.window.events.before_show.handlers, [])
        before = list(self.service.notifications)
        late_activation(self.native, None)
        late_session(None, SimpleNamespace(Reason='SessionUnlock'))
        late_show()
        self.assertEqual(self.service.notifications, before)
        self.assertFalse(self.service.probe())
        self.service.shutdown.assert_called_once_with()

    def test_lock_arriving_during_query_invalidates_prior_snapshot(self):
        self.show_main()
        self.query.during_query = lambda: self.switch_session('SessionLock')
        self.assertFalse(self.service.probe())

    def test_close_arriving_during_query_invalidates_prior_snapshot(self):
        self.show_main()
        self.query.during_query = self.close_main
        self.assertFalse(self.service.probe())

    def test_service_notifications_do_not_hold_window_manager_lock(self):
        self.show_main()
        available_during_callback = []
        workers = []

        def service_callback():
            read_complete = threading.Event()
            # Model a service snapshot on another thread that needs to read
            # review_count while this native callback enters the service.
            def service_snapshot():
                self.manager.review_count()
                read_complete.set()
            worker = threading.Thread(target=service_snapshot)
            workers.append(worker)
            worker.start()
            available_during_callback.append(read_complete.wait(.5))

        self.service.main_activation_changed = service_callback
        self.native.Deactivate.fire(self.native, None)
        self.native.Activated.fire(self.native, None)
        self.switch_session('SessionLock')
        self.switch_session('SessionUnlock')
        for worker in workers:
            worker.join(1)
            self.assertFalse(worker.is_alive())
        self.assertEqual(available_during_callback, [True, True, True, True])


class Win32ForegroundQueryTests(unittest.TestCase):
    def setUp(self):
        self.query = _Win32ForegroundQuery.__new__(_Win32ForegroundQuery)
        self.query._user32 = Mock()
        self.query._kernel32 = Mock()
        self.query._user32.IsWindow.return_value = True
        self.query._user32.OpenInputDesktop.return_value = 11
        self.query._user32.GetThreadDesktop.return_value = 12
        self.query._user32.GetForegroundWindow.return_value = 123
        self.query._desktop_name = Mock(return_value='Default')

    def test_actual_foreground_and_matching_desktop_required(self):
        self.assertTrue(self.query.is_foreground(123))
        self.assertFalse(self.query.is_foreground(456))
        self.query._user32.CloseDesktop.assert_called_with(11)

    def test_lock_desktop_or_unreadable_desktop_name_is_rejected(self):
        self.query._desktop_name.side_effect = ['Winlogon', 'Default', None]
        self.assertFalse(self.query.is_foreground(123))
        self.assertFalse(self.query.is_foreground(123))
        self.query._user32.GetForegroundWindow.assert_not_called()
        self.assertEqual(self.query._user32.CloseDesktop.call_count, 2)

    def test_open_desktop_failure_and_invalid_hwnd_are_rejected(self):
        self.query._user32.OpenInputDesktop.return_value = 0
        self.assertFalse(self.query.is_foreground(123))
        self.query._user32.CloseDesktop.assert_not_called()
        self.query._user32.IsWindow.return_value = False
        self.assertFalse(self.query.is_foreground(123))
        self.assertEqual(self.query._user32.OpenInputDesktop.call_count, 1)

    def test_input_desktop_handle_is_closed_when_foreground_query_raises(self):
        self.query._user32.GetForegroundWindow.side_effect = OSError('Synthetic query failure')
        with self.assertRaises(OSError):
            self.query.is_foreground(123)
        self.query._user32.CloseDesktop.assert_called_once_with(11)


if __name__ == '__main__':
    unittest.main()
