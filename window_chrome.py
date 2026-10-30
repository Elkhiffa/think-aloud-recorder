"""Native window behaviour for the self-drawn title bars (Windows, frameless pywebview).

The page draws its own title bar; Windows keeps owning the rest:
- the frame keeps a native sizing border (invisible on the sides and bottom), so
  resizing, Aero Snap, the shadow and the small rounded corners stay native;
- the title bar is a CSS `app-region: drag` area, which WebView2 reports to
  Windows as a real caption (move, snap, double-click to maximize);
- the thin top sizing border is tinted with the page colour so it reads as page;
- maximizing is limited to the monitor work area, so the taskbar stays visible.
Every native call runs on the window's UI thread.
"""
import ctypes
from ctypes import wintypes


# Window sizes vs page sizes. pywebview sizes a form by the window's DPI, but WebView2 can render the page at a
# different scale: on a home PC (2026-10-24) the form had a 720x520 client area while the page rendered at 1.46x,
# so it laid out in 494x357 and the home cards overlapped. The page's devicePixelRatio (zoom is fixed at 1) is the
# scale it actually renders at, so the client area is the design size times that ratio.

def page_factor(pixel_ratio, window_dpi):
    """How much larger the form must be than pywebview made it (1 when the page renders at the window's scale)."""
    window_scale = (window_dpi or 96) / 96
    return pixel_ratio / window_scale if pixel_ratio and pixel_ratio > 0 else 1.0


def physical_size(client_size, pixel_ratio, window_dpi):
    """The client area that gives the page exactly client_size layout pixels."""
    scale = pixel_ratio if pixel_ratio and pixel_ratio > 0 else (window_dpi or 96) / 96
    return round(client_size[0] * scale), round(client_size[1] * scale)


def fit(size, work):
    """Never larger than the monitor's work area."""
    return min(size[0], work[0]), min(size[1], work[1])

WM_SYSCOMMAND = 0x0112
SC_MINIMIZE, SC_MAXIMIZE, SC_RESTORE, SC_CLOSE = 0xF020, 0xF030, 0xF120, 0xF060
GWL_STYLE, WS_THICKFRAME, WS_MAXIMIZEBOX, WS_MINIMIZEBOX = -16, 0x00040000, 0x00010000, 0x00020000
SWP_FRAMECHANGED = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | FRAMECHANGED
DWMWA_BORDER_COLOR, DWMWA_CAPTION_COLOR, DWMWA_WINDOW_CORNER_PREFERENCE = 34, 35, 33
DWMWCP_ROUNDSMALL = 3

_user32 = ctypes.WinDLL('user32', use_last_error=True)
_user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
_user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT)
_user32.GetDpiForWindow.argtypes = (wintypes.HWND,)
_user32.GetDpiForWindow.restype = wintypes.UINT
_user32.IsZoomed.argtypes = (wintypes.HWND,)
_user32.IsIconic.argtypes = (wintypes.HWND,)
_user32.MonitorFromWindow.argtypes = (wintypes.HWND, wintypes.DWORD)
_user32.MonitorFromWindow.restype = wintypes.HANDLE


class _MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT), ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


def _colorref(value, shade=1.0):
    value = value.lstrip('#')
    if len(value) != 6 or any(c not in '0123456789abcdefABCDEF' for c in value):
        raise ValueError('颜色格式应为 #RRGGBB。')
    red, green, blue = (round(int(value[i:i + 2], 16) * shade) for i in (0, 2, 4))
    return ctypes.c_uint(red | green << 8 | blue << 16)


# The window outline is the paper a little darker, so stacked Think Aloud windows keep a visible edge (10-30).
EDGE_SHADE = .86


def _dwm(hwnd, attribute, value):
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value))
    except OSError:
        pass  # Older Windows keeps its default frame colour and corners.


class WindowChrome:
    """Bound to one pywebview window; the CHROME_METHODS are bridged to that page."""

    def __init__(self, window=None, frame_color='#f3ede1'):
        self._window = window
        self._frame_color = frame_color

    def bind(self, window):
        """Bridges are built before their window; bind once create_window has returned."""
        self._window = window

    def _native(self):
        native = getattr(self._window, 'native', None)
        if native is None:
            raise RuntimeError('窗口尚未就绪。')
        return native

    def _hwnd(self):
        return int(self._native().Handle.ToInt64())

    def _on_ui(self, action):
        from System import Action
        native = self._native()
        if native.InvokeRequired:
            native.Invoke(Action(action))
        else:
            action()

    def prepare(self, client_size=None):
        """Run once, after the first page load (the native form and WebView2 both exist).

        client_size is the page size the window was designed for; the sizing border is
        added outside it, so a 720x600 design still gets a 720x600 page.
        """
        if getattr(self, '_prepared', False):
            return
        self._prepared = True
        try:
            # Called from the page-loaded event, off the UI thread, so the page can answer.
            ratio = float(self._window.evaluate_js('window.devicePixelRatio') or 0) or None
        except Exception:
            ratio = None

        def apply():
            from System.Drawing import Point, Size
            native = self._native()
            hwnd = self._hwnd()
            style = _user32.GetWindowLongPtrW(hwnd, GWL_STYLE)
            _user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_MAXIMIZEBOX | WS_MINIMIZEBOX)
            _user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_FRAMECHANGED)
            _dwm(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.c_int(DWMWCP_ROUNDSMALL))
            self._tint(hwnd)
            # Measured once in the normal state; minimized windows report placeholder rects.
            outer, inner = wintypes.RECT(), wintypes.RECT()
            _user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(outer))
            _user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(inner))
            self._inset = (max(0, (outer.right - outer.left - inner.right) // 2),
                           max(0, (outer.bottom - outer.top - inner.bottom) // 2))
            dx, dy = self._inset
            window_dpi = _user32.GetDpiForWindow(wintypes.HWND(hwnd))
            factor = page_factor(ratio, window_dpi)
            info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
            monitor = _user32.MonitorFromWindow(wintypes.HWND(hwnd), 2)
            work = info.rcWork if monitor and _user32.GetMonitorInfoW(monitor, ctypes.byref(info)) else None
            area = (work.right - work.left, work.bottom - work.top) if work else (1 << 30, 1 << 30)
            minimum = native.MinimumSize
            if minimum.Width and minimum.Height:
                native.MinimumSize = Size(*fit((round(minimum.Width * factor) + 2 * dx,
                                                round(minimum.Height * factor) + 2 * dy), area))
            if client_size:
                width, height = physical_size(client_size, ratio, window_dpi)
            elif abs(factor - 1) > .02:
                width, height = round(inner.right * factor), round(inner.bottom * factor)
            else:
                width = height = None  # The page already renders at the window's scale: keep pywebview's size.
            if width:
                width, height = fit((width + 2 * dx, height + 2 * dy), area)
                native.Size = Size(width, height)
                if work:
                    # A grown window keeps its top-left corner; pull it back inside the work area.
                    left = max(work.left, min(native.Left, work.right - width))
                    top = max(work.top, min(native.Top, work.bottom - height))
                    if (left, top) != (native.Left, native.Top):
                        native.Location = Point(left, top)
            try:
                core = native.browser.webview.CoreWebView2
                core.Settings.IsNonClientRegionSupportEnabled = True
                # The setting only applies to the next navigation (verified by hand on 2026-10-19).
                core.Reload()
            except Exception:
                pass  # Older WebView2: the title bar cannot drag; the window buttons still work.
            self._normal_size = (native.Width, native.Height)
            self._last_state = 'normal'
            self._limit_maximize()
            native.LocationChanged += lambda sender, event: self._limit_maximize()
            native.Resize += lambda sender, event: self._keep_restored_size()
        self._on_ui(apply)

    def _keep_restored_size(self):
        """WinForms does not know about the added sizing border and restores 2×inset too small.

        The correction is queued behind WinForms' own restore handling, which would
        otherwise re-apply its smaller size after this event returns.
        """
        from System import Action
        from System.Windows.Forms import FormWindowState
        native = self._native()
        hwnd = wintypes.HWND(self._hwnd())
        zoomed, iconic = bool(_user32.IsZoomed(hwnd)), bool(_user32.IsIconic(hwnd))
        was_normal = self._last_state == 'normal'
        self._last_state = 'max' if zoomed else 'min' if iconic else 'normal'
        if zoomed or iconic:
            return
        if was_normal:
            self._normal_size = (native.Width, native.Height)
            return
        expected = self._normal_size

        def fix():
            from System.Drawing import Size
            if not _user32.IsZoomed(hwnd) and not _user32.IsIconic(hwnd) and (native.Width, native.Height) != expected:
                native.Size = Size(*expected)
            self._normal_size = (native.Width, native.Height)
        native.BeginInvoke(Action(fix))

    def _tint(self, hwnd):
        # The caption stays paper, so no system line runs along the title bar; the border is a weak outline.
        _dwm(hwnd, DWMWA_CAPTION_COLOR, _colorref(self._frame_color))
        _dwm(hwnd, DWMWA_BORDER_COLOR, _colorref(self._frame_color, EDGE_SHADE))

    def _limit_maximize(self):
        """Maximized size = current monitor's work area (WinForms applies it in WM_GETMINMAXINFO)."""
        from System.Drawing import Rectangle
        from System.Reflection import BindingFlags
        native = self._native()
        hwnd = wintypes.HWND(self._hwnd())
        if _user32.IsIconic(hwnd):
            return  # A minimized window has no real monitor position.
        info = _MonitorInfo(cbSize=ctypes.sizeof(_MonitorInfo))
        monitor = _user32.MonitorFromWindow(hwnd, 2)
        if not monitor or not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return
        work, screen = info.rcWork, info.rcMonitor
        # The invisible sizing border sits inside the window rect; push it past the work area
        # so the visible page fills the work area exactly, as a captioned window would.
        dx, dy = self._inset
        bounds = Rectangle(work.left - screen.left - dx, work.top - screen.top - dy,
                           work.right - work.left + 2 * dx, work.bottom - work.top + 2 * dy)
        prop = native.GetType().GetProperty('MaximizedBounds', BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)
        prop.SetValue(native, bounds)

    def win_set_frame_color(self, color):
        """The page calls this when its theme changes: the caption matches the paper, the outline follows it."""
        _colorref(color)
        self._frame_color = color
        hwnd = self._hwnd()
        self._on_ui(lambda: self._tint(hwnd))
        return True

    def bring_to_front(self):
        """Not bridged: the app uses it when an already-open window is requested again."""
        def show():
            native = self._native()
            if _user32.IsIconic(wintypes.HWND(self._hwnd())):
                _user32.PostMessageW(self._hwnd(), WM_SYSCOMMAND, SC_RESTORE, 0)
            native.Activate()
        self._on_ui(show)

    def win_minimize(self):
        _user32.PostMessageW(self._hwnd(), WM_SYSCOMMAND, SC_MINIMIZE, 0)
        return True

    def win_toggle_maximize(self):
        hwnd = self._hwnd()
        maximized = bool(_user32.IsZoomed(hwnd))
        _user32.PostMessageW(hwnd, WM_SYSCOMMAND, SC_RESTORE if maximized else SC_MAXIMIZE, 0)
        return not maximized

    def win_close(self):
        """Same path as the system close box, so the app's close guards still apply."""
        _user32.PostMessageW(self._hwnd(), WM_SYSCOMMAND, SC_CLOSE, 0)
        return True

    def win_is_maximized(self):
        return bool(_user32.IsZoomed(self._hwnd()))


CHROME_METHODS = ('win_minimize', 'win_toggle_maximize', 'win_close', 'win_is_maximized', 'win_set_frame_color')
