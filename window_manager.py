"""Native windows share one application lifetime; closing a viewer is local."""
import threading


class _Win32ForegroundQuery:
    """Read-only Win32 checks; no WinForms objects are touched by workers."""
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self._ctypes = ctypes
        self._user32 = ctypes.WinDLL('user32', use_last_error=True)
        self._kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        self._user32.GetForegroundWindow.argtypes = []
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.IsWindow.argtypes = [wintypes.HWND]
        self._user32.IsWindow.restype = wintypes.BOOL
        self._user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._user32.OpenInputDesktop.restype = wintypes.HANDLE
        self._user32.CloseDesktop.argtypes = [wintypes.HANDLE]
        self._user32.CloseDesktop.restype = wintypes.BOOL
        self._user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
        self._user32.GetThreadDesktop.restype = wintypes.HANDLE
        self._user32.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self._user32.GetUserObjectInformationW.restype = wintypes.BOOL
        self._kernel32.GetCurrentThreadId.argtypes = []
        self._kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def _desktop_name(self, desktop):
        from ctypes import wintypes
        if not desktop:
            return None
        buffer = self._ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        if not self._user32.GetUserObjectInformationW(desktop, 2, buffer,
                self._ctypes.sizeof(buffer), self._ctypes.byref(needed)):
            return None
        return buffer.value or None

    def is_foreground(self, hwnd):
        if not hwnd or not self._user32.IsWindow(hwnd):
            return False
        # SessionSwitch can be unavailable or arrive after the desktop changed.
        # Opening the input desktop for READOBJECTS does not switch desktops.
        desktop = self._user32.OpenInputDesktop(0, False, 0x0001)
        if not desktop:
            return False
        try:
            current = self._user32.GetThreadDesktop(self._kernel32.GetCurrentThreadId())
            name = self._desktop_name(desktop)
            if name is None or name != self._desktop_name(current):
                return False
            return self._user32.GetForegroundWindow() == hwnd
        finally:
            self._user32.CloseDesktop(desktop)


def _session_switch_source():
    # pywebview has loaded WinForms before its synchronous before_show event.
    from Microsoft.Win32 import SystemEvents
    return SystemEvents


class WindowManager:
    def __init__(self, service, webview):
        self.service = service
        self.webview = webview
        self._lock = threading.RLock()
        self._closing = False
        self._shutdown_thread = None
        self._viewers = {}
        self._viewer_changed = threading.Condition(self._lock)
        self._main_gone = threading.Event()
        self._updating = False
        self._update_main_closing = False
        self._main_focus = (0, False, False)  # HWND, native active, session locked
        self._foreground_query = None
        self._main_native = None
        self._main_native_events = []
        self._session_events = None

    def bind_main(self, window):
        self.main = window
        self.service.set_main_foreground_probe(self._main_is_foreground)
        try:
            window.events.before_show += self._main_before_show
        except (AttributeError, TypeError):
            # Unsupported native backends stay closed to automatic detection.
            pass
        window.events.closing += self.close_main
        window.events.closed += self._main_closed

    def _main_before_show(self):
        """pywebview runs before_show synchronously on the native UI thread."""
        with self._lock:
            if self._main_gone.is_set() or self._main_native is not None:
                return
            try:
                native = self.main.native
                hwnd = int(native.Handle.ToInt64())
                if not hwnd:
                    return
                query = _Win32ForegroundQuery()
                native.Activated += self._main_activated
                self._main_native_events.append((native, 'Activated', self._main_activated))
                native.Deactivate += self._main_deactivated
                self._main_native_events.append((native, 'Deactivate', self._main_deactivated))
            except Exception:
                self._remove_main_native_events()
                return
            self._main_native = native
            self._foreground_query = query
            self._main_focus = (hwnd, False, False)
            try:
                source = _session_switch_source()
                source.SessionSwitch += self._main_session_switch
                self._session_events = source
            except Exception:
                # The input-desktop check remains mandatory on every query.
                self._session_events = None

    def _main_is_foreground(self):
        # This snapshot is replaced atomically. Do not acquire the manager lock:
        # callers may hold the service lock while native events notify it.
        focus = self._main_focus
        hwnd, active, locked = focus
        if self._main_gone.is_set() or not hwnd or not active or locked:
            return False
        try:
            foreground = self._foreground_query.is_foreground(hwnd) is True
        except Exception:
            return False
        return foreground and self._main_focus is focus and not self._main_gone.is_set()

    def _main_activation(self, active):
        with self._lock:
            if self._main_gone.is_set():
                return
            hwnd, previous, locked = self._main_focus
            if not hwnd or active == previous:
                return
            self._main_focus = (hwnd, active, locked)
        self._notify_main_activation()

    def _main_activated(self, sender=None, event=None):
        self._main_activation(True)

    def _main_deactivated(self, sender=None, event=None):
        self._main_activation(False)

    def _main_session_switch(self, sender, event):
        with self._lock:
            if self._main_gone.is_set():
                return
            reason = str(event.Reason)
            hwnd, active, locked = self._main_focus
            if reason == 'SessionLock':
                self._main_focus = (hwnd, False, True)
            elif reason == 'SessionUnlock':
                # Unlock is only a reason to re-query the HWND. Another app or
                # a review window may be foreground when the desktop returns.
                self._main_focus = (hwnd, True, False)
                active = self._main_is_foreground()
                self._main_focus = (hwnd, active, False)
            else:
                return
        self._notify_main_activation()

    def _notify_main_activation(self):
        # Never enter the service while holding _lock: service snapshots can
        # call review_count while holding their own lock. Closed probes reject
        # a callback that was already in flight when the main window closed.
        if self._main_gone.is_set():
            return
        try:
            self.service.main_activation_changed()
        except Exception:
            # A failing service callback must not escape into the native loop.
            pass

    def _remove_main_native_events(self):
        for native, name, handler in self._main_native_events:
            try:
                event = getattr(native, name)
                event -= handler
            except Exception:
                pass
        self._main_native_events.clear()

    def _detach_main_focus(self):
        with self._lock:
            self._main_gone.set()
            self._main_focus = (0, False, True)
            if self._session_events is not None:
                try:
                    self._session_events.SessionSwitch -= self._main_session_switch
                except Exception:
                    pass
                self._session_events = None
            self._remove_main_native_events()
            self._main_native = None
            self._foreground_query = None
            try:
                self.main.events.before_show -= self._main_before_show
            except (AttributeError, TypeError, ValueError):
                pass

    def _main_closed(self):
        self._detach_main_focus()
        # Review windows do not need OBS. Finish engine cleanup even while they
        # remain open; a non-daemon worker also survives the last window closing.
        with self._lock:
            if self._shutdown_thread is None:
                self._shutdown_thread = threading.Thread(target=self.service.shutdown,
                    name='owned-obs-shutdown', daemon=False)
                self._shutdown_thread.start()

    def close_main(self):
        # Native close events must not wait on dialogs or worker completion.
        if self.service.update_in_progress() is True:
            # Helper readiness alone is not permission for the user's X to
            # remove the error/cancellation surface while viewers remain.
            with self._lock:programmatic=self._update_main_closing
            return programmatic and self.service.close_allowed(for_update=True)
        if self.service.close_allowed():
            return True
        # Update admission can race the first read above. Its native-only
        # close permission must also be explicit in the service lock.
        if self.service.update_in_progress() is True:
            return False
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

    def _review_window_options(self):
        """Leave room for a 900px video plus timeline on ordinary desktops.

        Use pywebview's existing monitor coordinates/work area. Smaller screens
        retain the responsive player rather than receiving an offscreen window.
        """
        options={'width':1440,'height':900}
        try:
            screens=self.webview.screens
            if not isinstance(screens,(list,tuple)) or not screens:return options
            selected=screens[0]
            main=getattr(self,'main',None)
            x,y=getattr(main,'x',None),getattr(main,'y',None)
            if type(x) in (int,float) and type(y) in (int,float):
                selected=next((screen for screen in screens
                    if screen.x<=x<screen.x+screen.width and screen.y<=y<screen.y+screen.height),selected)
            width,height=selected.width,selected.height
            if type(width) is not int or type(height) is not int or width<560 or height<540:return options
            frame=getattr(selected,'frame',None)
            work_width,work_height=getattr(frame,'Width',None),getattr(frame,'Height',None)
            if type(work_width) is int and 560<=work_width<=width:width=work_width
            if type(work_height) is int and 540<=work_height<=height:height=work_height
            options.update(width=min(1440,max(560,width-48)),height=min(900,max(540,height-64)),screen=selected)
        except Exception:
            # An unavailable monitor enumeration must not block existing reviews.
            pass
        return options

    def open_review(self, session):
        with self._lock:
            if self._updating:raise RuntimeError('应用正在退出以完成更新。')
        from review_runtime import ReviewAPI, prepare_window
        page, payload = prepare_window(self.service.root, session)
        api = ReviewAPI(session.path, payload, self.service.root / 'state/review-layout.json')
        try:
            window = self.webview.create_window(
                payload['title'] + ' · ' + payload['id'] + ' · 回看', url=page.as_uri(),
                js_api=api, **self._review_window_options(), min_size=(560, 540),
                frameless=False, resizable=True, text_select=True,
                background_color='#fcfaf5')
            with self._lock:
                self._viewers[window.uid] = window

            def closed():
                with self._viewer_changed:
                    self._viewers.pop(window.uid, None)
                    self._viewer_changed.notify_all()
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

    def review_count(self):
        with self._lock:return len(self._viewers)

    def close_for_update(self, timeout=5):
        """Only the admitted update flow closes viewers; ordinary close does not."""
        import time
        if self.service.update_close_ready() is not True:
            raise RuntimeError('尚未完成安全退出检查，未关闭回看窗口。')
        with self._lock:
            self._updating=True
            viewers=list(self._viewers.values())
        try:
            for window in viewers:window.destroy()
            deadline=time.monotonic()+timeout
            with self._viewer_changed:
                while self._viewers:
                    remaining=deadline-time.monotonic()
                    if remaining<=0:raise RuntimeError('回看窗口尚未关闭，更新未开始；请关闭后重试。')
                    self._viewer_changed.wait(remaining)
            # Keep the main error/status surface until all viewers are gone.
            with self._lock:self._update_main_closing=True
            self.main.destroy()
            if not self._main_gone.wait(timeout):
                raise RuntimeError('主窗口尚未关闭，更新未开始；请稍后重试。')
        except Exception:
            with self._lock:
                self._updating=False
                self._update_main_closing=False
            raise
