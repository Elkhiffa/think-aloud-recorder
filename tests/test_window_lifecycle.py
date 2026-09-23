"""Window lifecycle units; native last-window exit is tested separately on Windows."""
import threading
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from window_manager import WindowManager


class Event:
    def __iadd__(self, handler):
        self.handler = handler
        return self


class LifecycleTests(unittest.TestCase):
    def test_review_starts_wide_enough_for_video_and_caps_to_monitor_work_area(self):
        large=SimpleNamespace(x=0,y=0,width=1920,height=1080,frame=SimpleNamespace(Width=1920,Height=1040))
        small=SimpleNamespace(x=-1280,y=0,width=1280,height=720,frame=SimpleNamespace(Width=1280,Height=680))
        manager=WindowManager(Mock(),SimpleNamespace(screens=[large,small]))
        manager.main=SimpleNamespace(x=100,y=100)
        self.assertEqual(manager._review_window_options(),dict(width=1440,height=900,screen=large))
        manager.main.x=-1000
        self.assertEqual(manager._review_window_options(),dict(width=1232,height=616,screen=small))

    def test_review_monitor_lookup_failure_does_not_prevent_opening(self):
        manager=WindowManager(Mock(),SimpleNamespace(screens=[]))
        self.assertEqual(manager._review_window_options(),dict(width=1440,height=900))

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

    def test_update_close_requires_native_commit_and_closes_reviews_before_main(self):
        manager,service,window=self.setup_manager()
        other=Mock()
        manager._viewers['review']=other
        service.update_close_ready.return_value=False
        with self.assertRaisesRegex(RuntimeError,'安全退出'):manager.close_for_update(timeout=.02)
        other.destroy.assert_not_called()
        service.update_close_ready.return_value=True
        calls=[]
        def review_closed():
            calls.append('review')
            manager._viewers.pop('review')
        other.destroy.side_effect=review_closed
        window.destroy.side_effect=lambda:(calls.append('main'),window.events.closed.handler())
        manager.close_for_update(timeout=.2)
        self.assertEqual(calls,['review','main'])
        self.assertEqual(manager.review_count(),0)

    def test_unclosed_review_keeps_main_available_for_update_error(self):
        manager,service,window=self.setup_manager()
        service.update_close_ready.return_value=True
        manager._viewers['review']=Mock()
        with self.assertRaisesRegex(RuntimeError,'回看窗口尚未关闭'):manager.close_for_update(timeout=.01)
        window.destroy.assert_not_called()
        self.assertFalse(manager._updating)

    def test_manual_close_during_update_preparation_does_not_spawn_normal_exit(self):
        manager,service,window=self.setup_manager()
        service.update_in_progress.return_value=True
        service.close_allowed.return_value=False
        self.assertFalse(manager.close_main())
        window.create_confirmation_dialog.assert_not_called()
        service.finish_for_close.assert_not_called()

    def test_helper_ready_does_not_allow_manual_main_close_while_viewers_remain(self):
        manager,service,window=self.setup_manager()
        service.update_in_progress.return_value=True
        service.update_close_ready.return_value=True
        service.close_allowed.return_value=True
        viewer=Mock()
        manager._viewers['review']=viewer
        viewer.destroy.side_effect=lambda:self.assertFalse(manager.close_main())
        with self.assertRaisesRegex(RuntimeError,'回看窗口尚未关闭'):
            manager.close_for_update(timeout=.01)
        window.destroy.assert_not_called()
        service.close_allowed.assert_not_called()
        self.assertFalse(manager._update_main_closing)
        self.assertFalse(manager.close_main())


if __name__ == '__main__':
    unittest.main()
