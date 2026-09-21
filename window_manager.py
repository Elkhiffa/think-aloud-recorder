"""Native windows share one application lifetime; closing a viewer is local."""
import threading


class WindowManager:
    def __init__(self, service, webview):
        self.service = service
        self.webview = webview
        self._lock = threading.RLock()
        self._closing = False
        self._viewers = {}

    def bind_main(self, window):
        self.main = window
        window.events.closing += self.close_main

    def close_main(self):
        # Native close events must not wait on dialogs or worker completion.
        if self.service.close_allowed():
            return True
        with self._lock:
            if not self._closing:
                self._closing = True
                threading.Thread(target=self._confirm_close, daemon=True,
                                 name='safe-window-close').start()
        return False

    def _confirm_close(self):
        try:
            message = self.service.close_reason()
            if self.main.create_confirmation_dialog('关闭记录器', message +
                    '\n\n结束当前录制，并等待保存和整理完成后关闭此窗口？已打开的回看窗口会继续保留。'):
                self.service.finish_for_close()
                self.main.destroy()
        except Exception as error:
            self.main.create_confirmation_dialog('暂时无法安全关闭',
                str(error) + '\n\n窗口已保留，请处理提示后再关闭。')
        finally:
            with self._lock:
                self._closing = False

    def open_review(self, session):
        from review_runtime import ReviewAPI, prepare_window
        page, payload = prepare_window(self.service.root, session)
        api = ReviewAPI(session.path, payload, self.service.root / 'state/review-layout.json')
        try:
            window = self.webview.create_window(
                payload['title'] + ' · ' + payload['id'] + ' · 回看', url=page.as_uri(),
                js_api=api, width=1180, height=780, min_size=(560, 540),
                frameless=False, resizable=True, text_select=True,
                background_color='#fafbf7')
            with self._lock:
                self._viewers[window.uid] = window

            def closed():
                with self._lock:
                    self._viewers.pop(window.uid, None)
                page.unlink(missing_ok=True)
            window.events.closed += closed
            if not api._ready.wait(15):
                raise RuntimeError('回看窗口尚未确认加载完成，请查看新窗口中的提示。')
            if api._error:
                raise RuntimeError(api._error)
            return {'ready': True}
        except Exception:
            if 'window' not in locals():
                page.unlink(missing_ok=True)
            raise
