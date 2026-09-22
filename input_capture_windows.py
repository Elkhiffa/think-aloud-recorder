"""Windows Raw Input listener bounded to one live target window/session.

RIDEV_INPUTSINK delivers physical events without disabling the application's
normal input. Every event is checked against the captured HWND and process
identity before it reaches the recorder. All registrations are removed on exit.
"""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
import math
import os
import threading
import time
import uuid
from input_capture import InputCaptureError


@dataclass(frozen=True)
class TargetWindow:
    hwnd: int
    pid: int
    created: float
    window_class: str


def parse_obs_window(value):
    parts = str(value).split(':')
    if len(parts) != 3 or not all(parts):
        raise InputCaptureError('窗口标识无效，请刷新并重新选择游戏窗口。')
    return tuple(part.replace('#3A', ':').replace('#22', '#') for part in parts)


def winapi():
    if os.name != 'nt':
        raise InputCaptureError('操作采集目前仅支持 Windows。')
    user = C.WinDLL('user32', use_last_error=True)
    kernel = C.WinDLL('kernel32', use_last_error=True)
    for name, args, restype in (
        ('GetForegroundWindow', [], W.HWND), ('IsWindowVisible', [W.HWND], W.BOOL),
        ('IsWindow', [W.HWND], W.BOOL),
        ('GetWindowThreadProcessId', [W.HWND, C.POINTER(W.DWORD)], W.DWORD),
        ('GetWindowTextW', [W.HWND, W.LPWSTR, C.c_int], C.c_int),
        ('GetClassNameW', [W.HWND, W.LPWSTR, C.c_int], C.c_int),
        ('GetAsyncKeyState', [C.c_int], C.c_short),
    ):
        fn = getattr(user, name)
        fn.argtypes, fn.restype = args, restype
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [W.DWORD, W.BOOL, W.DWORD], W.HANDLE
    kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = [W.HANDLE, W.DWORD], W.DWORD
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [W.HANDLE], W.BOOL
    kernel.GetModuleHandleW.argtypes, kernel.GetModuleHandleW.restype = [W.LPCWSTR], W.HMODULE
    kernel.GetTickCount64.restype = C.c_uint64
    return user, kernel


def resolve_target(value):
    """Exact title/class/executable match, then bind HWND + process creation.

    Unlike OBS's fallback matching, ambiguous or missing targets fail closed.
    This read-only enumeration does not register keyboard/mouse/controller input.
    """
    title, window_class, exe = parse_obs_window(value)
    user, _ = winapi()
    import psutil
    found = []
    callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, W.LPARAM], W.BOOL

    @callback_type
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        text, cls = C.create_unicode_buffer(4096), C.create_unicode_buffer(512)
        user.GetWindowTextW(hwnd, text, len(text))
        user.GetClassNameW(hwnd, cls, len(cls))
        if text.value != title or cls.value != window_class:
            return True
        pid = W.DWORD()
        user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        try:
            process = psutil.Process(pid.value)
            if process.name().casefold() == exe.casefold():
                found.append(TargetWindow(int(hwnd), pid.value, process.create_time(), cls.value))
        except psutil.Error:
            pass
        return True

    user.EnumWindows(visit, 0)
    if len(found) != 1:
        raise InputCaptureError('目标窗口尚未打开或存在重名窗口，请刷新并重新选择。')
    return found[0]


KEY_NAMES = {8: 'Backspace', 9: 'Tab', 13: 'Enter', 19: 'Pause', 20: 'CapsLock',
             27: 'Escape', 32: 'Space', 33: 'PageUp', 34: 'PageDown', 35: 'End', 36: 'Home',
             37: 'ArrowLeft', 38: 'ArrowUp', 39: 'ArrowRight', 40: 'ArrowDown',
             44: 'PrintScreen', 45: 'Insert', 46: 'Delete', 91: 'WinLeft', 92: 'WinRight',
             93: 'ContextMenu', 106: 'NumMultiply', 107: 'NumAdd', 109: 'NumSubtract',
             110: 'NumDecimal', 111: 'NumDivide', 144: 'NumLock', 145: 'ScrollLock',
             160: 'ShiftLeft', 161: 'ShiftRight', 162: 'ControlLeft', 163: 'ControlRight',
             164: 'AltLeft', 165: 'AltRight', 186: 'Semicolon', 187: 'Equal', 188: 'Comma',
             189: 'Minus', 190: 'Period', 191: 'Slash', 192: 'Backquote', 219: 'BracketLeft',
             220: 'Backslash', 221: 'BracketRight', 222: 'Quote', 226: 'IntlBackslash'}
KEY_NAMES.update({v: chr(v) for v in range(48, 58)})
KEY_NAMES.update({v: chr(v) for v in range(65, 91)})
KEY_NAMES.update({v: 'Num' + str(v - 96) for v in range(96, 106)})
KEY_NAMES.update({v: 'F' + str(v - 111) for v in range(112, 136)})


def key_code(vkey, scan=0, flags=0):
    if vkey == 16:
        return 'ShiftRight' if scan == 0x36 else 'ShiftLeft'
    if vkey == 17:
        return 'ControlRight' if flags & 2 else 'ControlLeft'
    if vkey == 18:
        return 'AltRight' if flags & 2 else 'AltLeft'
    if vkey == 13 and flags & 2:
        return 'NumEnter'
    return KEY_NAMES.get(vkey)


class Header(C.Structure):
    _fields_ = [('type', W.DWORD), ('size', W.DWORD), ('device', W.HANDLE), ('param', W.WPARAM)]


class RawKeyboard(C.Structure):
    _fields_ = [('scan', W.USHORT), ('flags', W.USHORT), ('reserved', W.USHORT),
                ('vkey', W.USHORT), ('message', W.UINT), ('extra', W.ULONG)]


class MouseButtons(C.Structure):
    _fields_ = [('flags', W.USHORT), ('data', W.USHORT)]


class MouseUnion(C.Union):
    _anonymous_ = ('button',)
    _fields_ = [('buttons', W.ULONG), ('button', MouseButtons)]


class RawMouse(C.Structure):
    _anonymous_ = ('button_union',)
    _fields_ = [('flags_move', W.USHORT), ('button_union', MouseUnion), ('raw_buttons', W.ULONG),
                ('x', W.LONG), ('y', W.LONG), ('extra', W.ULONG)]


class RawData(C.Union):
    _fields_ = [('keyboard', RawKeyboard), ('mouse', RawMouse)]


class RawInput(C.Structure):
    _fields_ = [('header', Header), ('data', RawData)]


class RawDevice(C.Structure):
    _fields_ = [('page', W.USHORT), ('usage', W.USHORT), ('flags', W.DWORD), ('target', W.HWND)]



class SystemTickClock:
    """One shared Win32 tick-to-monotonic mapping for raw input and WinEvents.

    Tick resolution affects absolute video alignment; using the same calibration
    removes callback-delivery phase differences from foreground classification.
    """
    def __init__(self, clock, ticks):
        self.ticks = ticks
        samples = []
        for _ in range(5):
            before = clock()
            tick = ticks()
            after = clock()
            samples.append((after - before, tick, (before + after) / 2))
        _, self.tick_origin, self.perf_origin = min(samples)

    def from_tick32(self, stamp):
        now = self.ticks()
        age = ((now & 0xffffffff) - (stamp & 0xffffffff)) & 0xffffffff
        return self.perf_origin + (now - age - self.tick_origin) / 1000.

    def now(self):
        return self.perf_origin + (self.ticks() - self.tick_origin) / 1000.


class ForegroundLedger:
    """Timestamped foreground history; authorization never uses current focus alone."""
    def __init__(self):
        self.lock = threading.Lock()
        self.transitions = []
        self.watermark = float('-inf')
        self.uncertain = []
        self.invalid_from = None

    def note(self, foreground, timestamp, observed=None):
        with self.lock:
            if self.transitions and timestamp < self.transitions[-1][0]:
                self.uncertain.append((timestamp, observed if observed is not None else self.watermark))
                self.invalid_from = timestamp if self.invalid_from is None else min(self.invalid_from, timestamp)
                return
            if timestamp < self.watermark:
                self.uncertain.append((timestamp, observed if observed is not None else self.watermark))
                self.invalid_from = timestamp if self.invalid_from is None else min(self.invalid_from, timestamp)
            self.transitions.append((timestamp, bool(foreground)))

    def publish(self, timestamp):
        with self.lock:
            self.watermark = max(self.watermark, timestamp)

    def drain(self, cursor):
        with self.lock:
            return list(self.transitions[cursor:]), len(self.transitions), self.watermark

    def authorized(self, timestamp):
        with self.lock:
            if timestamp > self.watermark or not self.transitions or timestamp < self.transitions[0][0]:
                return False
            # SDL's clock is separate from Win32's; discard a conservative
            # boundary band rather than classify near-transition samples.
            if any(abs(timestamp - at) <= .032 for at, _ in self.transitions):
                return False
            if any(a <= timestamp <= b for a, b in self.uncertain):
                return False
            for at, foreground in reversed(self.transitions):
                if at <= timestamp:
                    return foreground
        return False


class ForegroundObserver:
    """A dedicated WinEvent pump remains responsive if capture or disk stalls."""
    def __init__(self, target, clock, invalidated=None, mapper=None):
        self.target, self.clock = target, clock
        self.invalidated = invalidated
        self.mapper = mapper
        self.ledger = ForegroundLedger()
        self.ready, self.stopping = threading.Event(), threading.Event()
        self.error = None
        self.thread = None
        self.unhooked = False
        self.markers_acknowledged = 0
        self.marker_hwnd = None

    def start(self):
        self.thread = threading.Thread(target=self._run, name='InputForegroundEvents', daemon=True)
        self.thread.start()
        if not self.ready.wait(3) or self.error:
            self.stop()
            raise InputCaptureError('无法验证前台窗口变化，操作采集已停止。')

    def stop(self):
        self.stopping.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2)

    def _run(self):
        hook = marker_window = None
        try:
            user, kernel = winapi()
            mapper = self.mapper or SystemTickClock(self.clock, kernel.GetTickCount64)
            callback_type = C.WINFUNCTYPE(None, W.HANDLE, W.DWORD, W.HWND, W.LONG, W.LONG, W.DWORD, W.DWORD)
            user.SetWinEventHook.argtypes = [W.DWORD, W.DWORD, W.HMODULE, callback_type, W.DWORD, W.DWORD, W.DWORD]
            user.SetWinEventHook.restype = W.HANDLE
            user.UnhookWinEvent.argtypes, user.UnhookWinEvent.restype = [W.HANDLE], W.BOOL
            user.PeekMessageW.argtypes, user.PeekMessageW.restype = [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT], W.BOOL
            user.DispatchMessageW.argtypes, user.DispatchMessageW.restype = [C.POINTER(W.MSG)], C.c_ssize_t
            user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int, C.c_int,
                                            W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
            user.CreateWindowExW.restype = W.HWND
            user.DestroyWindow.argtypes, user.DestroyWindow.restype = [W.HWND], W.BOOL
            user.NotifyWinEvent.argtypes, user.NotifyWinEvent.restype = [W.DWORD, W.HWND, W.LONG, W.LONG], None
            marker_window = user.CreateWindowExW(0, 'STATIC', '', 0, 0, 0, 0, 0, W.HWND(-3), None,
                                                kernel.GetModuleHandleW(None), None)
            if not marker_window:
                raise InputCaptureError('无法创建前台事件确认窗口。')
            self.marker_hwnd = marker_window
            # Published custom OEM WinEvent (see validation doc). It describes
            # only a private queue fence on our message-only window, never focus.
            marker_event, marker_object = 0x01FF, 0x5441
            waiting = {}
            sequence = 0

            @callback_type
            def changed(_hook, event, hwnd, obj, child, thread, stamp_ms):
                now = self.clock()
                if event == marker_event and hwnd == marker_window and obj == marker_object:
                    fence = waiting.pop(child, None)
                    if fence is not None:
                        # The same OUTOFCONTEXT hook receives all preceding
                        # foreground callbacks before this marker. The 32 ms
                        # margin bounds common 10-16 ms system tick resolution.
                        # It never authorizes an event without a marker ack.
                        self.ledger.publish(fence - .032)
                        self.markers_acknowledged += 1
                        self.ready.set()
                    return
                if event != 3:
                    return
                self.ledger.note(hwnd == self.target.hwnd, mapper.from_tick32(stamp_ms), now)
                if self.ledger.invalid_from is not None and self.invalidated:
                    self.invalidated(self.ledger.invalid_from)

            hook = user.SetWinEventHook(3, marker_event, None, changed, 0, 0, 0)  # One ordered queue for focus and markers
            if not hook:
                raise InputCaptureError('无法订阅前台窗口变化。')
            self.ledger.note(user.GetForegroundWindow() == self.target.hwnd, mapper.now())
            message = W.MSG()
            while not self.stopping.is_set():
                while user.PeekMessageW(C.byref(message), None, 0, 0, 1):
                    user.DispatchMessageW(C.byref(message))
                if not waiting:
                    sequence = sequence % 0x7ffffffe + 1
                    waiting[sequence] = mapper.now()
                    user.NotifyWinEvent(marker_event, marker_window, marker_object, sequence)
                elif self.clock() - min(waiting.values()) > 1.:
                    raise InputCaptureError('前台事件确认超时，操作采集已停止。')
                self.stopping.wait(.004)
        except Exception:
            self.error = '前台窗口事件不可用。'
        finally:
            if hook:
                self.unhooked = bool(user.UnhookWinEvent(hook))
            if marker_window:
                user.DestroyWindow(marker_window)
            self.ready.set()

_SOURCE_LOCK = threading.Lock()


class WindowsInputSource:
    def __init__(self, target, sdl_path, clock=time.perf_counter):
        self.target, self.sdl_path, self.clock = target, sdl_path, clock
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._error = None
        self._eligible = False
        self._eligible_since = float('inf')
        self._controllers = None
        self._observer = None
        self._pending = []
        self._focus_cursor = 0
        self._invalid_sent = None
        self._mouse_xy = None
        self._mouse_accum = [0, 0]
        self._mouse_stamp = 0.
        self._motion_started = False
        self._mapper = None
        self._resume_due = None

    def start(self, callback):
        self.callback = callback
        self._thread = threading.Thread(target=self._run, name='SessionInputCapture', daemon=True)
        self._thread.start()
        if not self._ready.wait(8):
            self.stop()
            raise InputCaptureError('操作采集启动超时。')
        if self._error:
            raise InputCaptureError(self._error)

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                raise InputCaptureError('操作采集仍在退出，请稍后重试。')

    def _foreground(self):
        if self.user.GetForegroundWindow() != self.target.hwnd:
            return False
        if self.kernel.WaitForSingleObject(self.process_handle, 0) != 258:
            return False
        pid = W.DWORD()
        self.user.GetWindowThreadProcessId(self.target.hwnd, C.byref(pid))
        return pid.value == self.target.pid

    def _focus(self):
        foreground = self._foreground()
        if foreground != self._eligible:
            self._eligible = foreground
            self._eligible_since = self.clock() if foreground else float('inf')
            self._mouse_xy = None
            self._mouse_accum = [0, 0]
            self._motion_started = False
            self._resume_due = self.clock() + .064 if foreground else None
        return foreground

    def _resume_if_stable(self):
        if self._resume_due is None or self.clock() < self._resume_due:
            return
        self._resume_due = None
        if not self._foreground():
            self._focus()
            return
        self._resume_keyboard()
        if self._controllers and self._foreground():
            self._controllers.resume()

    def _emit(self, event):
        if event['type'] in ('connect', 'disconnect'):
            self._pending.append(event)
            return
        # Re-check for each event; never trust a foreground state cached by a
        # previous timer iteration. Also discard older messages queued outside.
        if not self._focus() or event.get('timestamp', 0) < self._eligible_since:
            return
        if self.clock() - event.get('timestamp', self.clock()) > 2:
            self._pending.append({'type': 'coverage_gap', 'timestamp': event['timestamp'], 'end': self.clock()})
            return
        self._pending.append(dict(event, foreground=True))

    def _resume_keyboard(self):
        # No state is sampled while another program is foreground. A resumed
        # hold is marked explicitly rather than pretending to know its onset.
        for vk, code in KEY_NAMES.items():
            if not self._foreground():
                return
            if self.user.GetAsyncKeyState(vk) & 0x8000:
                self._emit({'type': 'button', 'device': 'keyboard', 'code': code,
                               'down': True, 'timestamp': self.clock(), 'foreground': True, 'resumed': True})
        for vk, code in ((1, 'MouseLeft'), (2, 'MouseRight'), (4, 'MouseMiddle'), (5, 'MouseX1'), (6, 'MouseX2')):
            if not self._foreground():
                return
            if self.user.GetAsyncKeyState(vk) & 0x8000:
                self._emit({'type': 'button', 'device': 'mouse', 'code': code,
                               'down': True, 'timestamp': self.clock(), 'foreground': True, 'resumed': True})

    def _invalidate(self, timestamp):
        if self._invalid_sent is None or timestamp < self._invalid_sent:
            self._invalid_sent = timestamp
            self.callback({'type': 'invalidate', 'timestamp': timestamp})
        self._stop.set()

    def _flush_pending(self, through=None):
        if self._observer.ledger.invalid_from is not None:
            self._invalidate(self._observer.ledger.invalid_from)
            self._pending.clear()
            return
        if self._observer.error:
            raise InputCaptureError('前台窗口验证中断，操作采集已停止。')
        transitions, self._focus_cursor, watermark = self._observer.ledger.drain(self._focus_cursor)
        if through is not None:
            watermark = min(watermark, through)
        self._pending.extend({'type': 'focus', 'timestamp': stamp, 'foreground': active} for stamp, active in transitions)
        ready = sorted((e for e in self._pending if e['timestamp'] <= watermark), key=lambda e: (e['timestamp'], e['type'] != 'focus'))
        self._pending = [e for e in self._pending if e['timestamp'] > watermark]
        for event in ready:
            if event['type'] in ('focus', 'connect', 'disconnect', 'coverage_gap') or self._observer.ledger.authorized(event['timestamp']):
                self.callback(event)
            else:
                self.callback({'type': 'coverage_gap', 'timestamp': event['timestamp'],
                               'end': event['timestamp'], 'reason': '前台归属无法确认，此次输入未记录'})
        if math.isfinite(watermark):
            self.callback({'type': 'watermark', 'timestamp': watermark})

    def _stamp(self):
        # Win32 message time preserves short press/release spacing even when a
        # batch is drained together. Unsigned subtraction handles uptime wrap.
        if self._mapper is not None:
            return self._mapper.from_tick32(self.user.GetMessageTime())
        age = ((self.kernel.GetTickCount64() & 0xffffffff) - (self.user.GetMessageTime() & 0xffffffff)) & 0xffffffff
        return self.clock() - age / 1000.

    def _raw(self, handle):
        if not self._focus():
            return
        size = W.UINT()
        if self.user.GetRawInputData(handle, 0x10000003, None, C.byref(size), C.sizeof(Header)) == 0xffffffff:
            raise InputCaptureError('读取原始输入失败。')
        if size.value < C.sizeof(Header) or size.value > 65536:
            return
        buffer = C.create_string_buffer(size.value)
        if self.user.GetRawInputData(handle, 0x10000003, buffer, C.byref(size), C.sizeof(Header)) == 0xffffffff:
            raise InputCaptureError('读取原始输入失败。')
        raw = C.cast(buffer, C.POINTER(RawInput)).contents
        stamp = self._stamp()
        if stamp < self._eligible_since:
            return
        if raw.header.type == 1:
            key = raw.data.keyboard
            code = key_code(key.vkey, key.scan, key.flags)
            if code:
                self._emit({'type': 'button', 'device': 'keyboard', 'code': code,
                            'down': not bool(key.flags & 1), 'timestamp': stamp})
        elif raw.header.type == 0:
            mouse = raw.data.mouse
            for down, up, code in ((1, 2, 'MouseLeft'), (4, 8, 'MouseRight'), (16, 32, 'MouseMiddle'),
                                   (64, 128, 'MouseX1'), (256, 512, 'MouseX2')):
                if mouse.flags & down:
                    self._emit({'type': 'button', 'device': 'mouse', 'code': code, 'down': True, 'timestamp': stamp})
                if mouse.flags & up:
                    self._emit({'type': 'button', 'device': 'mouse', 'code': code, 'down': False, 'timestamp': stamp})
            if mouse.flags & (0x400 | 0x800):
                positive = C.c_short(mouse.data).value > 0
                code = ('WheelRight' if positive else 'WheelLeft') if mouse.flags & 0x800 else ('WheelUp' if positive else 'WheelDown')
                self._emit({'type': 'pulse', 'device': 'mouse', 'code': code, 'timestamp': stamp})
            x, y = mouse.x, mouse.y
            if mouse.flags_move & 1:
                previous, self._mouse_xy = self._mouse_xy, (x, y)
                x, y = (x - previous[0], y - previous[1]) if previous else (0, 0)
            if x or y:
                self._mouse_accum[0] += x
                self._mouse_accum[1] += y
                if stamp - self._mouse_stamp >= 1 / 60:
                    dx, dy = self._mouse_accum
                    magnitude = math.hypot(dx, dy)
                    # Two raw counts / sample excludes stationary hardware noise.
                    if magnitude >= 2:
                        self._emit({'type': 'motion', 'kind': 'motion', 'device': 'mouse', 'code': 'MouseMove',
                                    'x': round(dx / magnitude, 1), 'y': round(dy / magnitude, 1),
                                    'value': 1., 'timestamp': stamp})
                    self._mouse_accum = [0, 0]
                    self._mouse_stamp = stamp

    def _run(self):
        acquired = _SOURCE_LOCK.acquire(blocking=False)
        hwnd = instance = process_handle = None
        class_name = 'ThinkAloudInput-' + uuid.uuid4().hex
        registered = raw_registered = False
        try:
            if not acquired:
                raise InputCaptureError('已有场次正在采集操作。')
            self.user, self.kernel = winapi()
            import psutil
            if psutil.Process(self.target.pid).create_time() != self.target.created:
                raise InputCaptureError('目标程序已重新启动，请重新开始录制。')
            process_handle = self.kernel.OpenProcess(0x100000 | 0x1000, False, self.target.pid)
            if not process_handle:
                raise InputCaptureError('无法验证目标进程，请检查程序权限。')
            self.process_handle = process_handle
            self._mapper = SystemTickClock(self.clock, self.kernel.GetTickCount64)
            self._observer = ForegroundObserver(self.target, self.clock, self._invalidate, self._mapper)
            self._observer.start()
            wndproc_type = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

            class WindowClass(C.Structure):
                _fields_ = [('style', W.UINT), ('proc', wndproc_type), ('cls_extra', C.c_int), ('wnd_extra', C.c_int),
                            ('instance', W.HINSTANCE), ('icon', W.HICON), ('cursor', W.HANDLE), ('brush', W.HBRUSH),
                            ('menu', W.LPCWSTR), ('name', W.LPCWSTR)]

            for name, args, result in (
                ('DefWindowProcW', [W.HWND, W.UINT, W.WPARAM, W.LPARAM], C.c_ssize_t),
                ('RegisterClassW', [C.POINTER(WindowClass)], W.ATOM),
                ('UnregisterClassW', [W.LPCWSTR, W.HINSTANCE], W.BOOL),
                ('CreateWindowExW', [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD, C.c_int, C.c_int, C.c_int,
                                     C.c_int, W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p], W.HWND),
                ('DestroyWindow', [W.HWND], W.BOOL),
                ('RegisterRawInputDevices', [C.POINTER(RawDevice), W.UINT, W.UINT], W.BOOL),
                ('GetRawInputData', [W.HANDLE, W.UINT, C.c_void_p, C.POINTER(W.UINT), W.UINT], W.UINT),
                ('PeekMessageW', [C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT], W.BOOL),
                ('DispatchMessageW', [C.POINTER(W.MSG)], C.c_ssize_t),
                ('TranslateMessage', [C.POINTER(W.MSG)], W.BOOL),
                ('GetMessageTime', [], W.LONG),
            ):
                fn = getattr(self.user, name)
                fn.argtypes, fn.restype = args, result

            @wndproc_type
            def procedure(window, message, param, data):
                if message == 0xff:
                    try:
                        self._raw(data)
                    except Exception:
                        self._error = '操作采集读取异常，已停止采集。'
                        self.callback({'type': 'error'})
                        self._stop.set()
                return self.user.DefWindowProcW(window, message, param, data)

            instance = self.kernel.GetModuleHandleW(None)
            wc = WindowClass(0, procedure, 0, 0, instance, None, None, None, None, class_name)
            if not self.user.RegisterClassW(C.byref(wc)):
                raise InputCaptureError('无法创建操作采集窗口。')
            registered = True
            hwnd = self.user.CreateWindowExW(0, class_name, '', 0, 0, 0, 0, 0, W.HWND(-3), None, instance, None)
            if not hwnd:
                raise InputCaptureError('无法创建操作采集窗口。')
            from input_capture_devices import SDLControllers
            self._controllers = SDLControllers(self.sdl_path, self._emit, self.clock, self._foreground)
            devices = (RawDevice * 2)(RawDevice(1, 2, 0x100, hwnd), RawDevice(1, 6, 0x100, hwnd))
            if not self.user.RegisterRawInputDevices(devices, 2, C.sizeof(RawDevice)):
                raise InputCaptureError('无法订阅键鼠输入，请检查程序权限。')
            raw_registered = True
            self.callback({'type': 'ready', 'timestamp': self.clock()})
            self._focus()
            self._ready.set()
            message = W.MSG()
            while not self._stop.is_set():
                self._focus()
                count = 0
                while self.user.PeekMessageW(C.byref(message), None, 0, 0, 1):
                    self.user.TranslateMessage(C.byref(message))
                    self.user.DispatchMessageW(C.byref(message))
                    count += 1
                    if count >= 512 or self._stop.is_set():
                        break
                self._controllers.pump()
                self._resume_if_stable()
                self._flush_pending()
                self._stop.wait(.004)
            stop_at = self.clock()
            # Wait only for a real marker acknowledgement, never advance a fence
            # merely because wall time elapsed. Unconfirmed tail remains absent.
            deadline = stop_at + .5
            while self._observer.ledger.watermark < stop_at and self.clock() < deadline and not self._observer.error:
                time.sleep(.005)
            self._flush_pending(through=stop_at)
        except Exception as exc:
            self._error = str(exc) if isinstance(exc, InputCaptureError) else '操作采集不可用，请检查设备和窗口。'
            self.callback({'type': 'error'})
        finally:
            if self._observer:
                self._observer.stop()
            if raw_registered:
                removal = (RawDevice * 2)(RawDevice(1, 2, 1, None), RawDevice(1, 6, 1, None))
                self.user.RegisterRawInputDevices(removal, 2, C.sizeof(RawDevice))
            if self._controllers:
                self._controllers.close()
            if hwnd:
                self.user.DestroyWindow(hwnd)
            if registered:
                self.user.UnregisterClassW(class_name, instance)
            if process_handle:
                self.kernel.CloseHandle(process_handle)
            if acquired:
                _SOURCE_LOCK.release()
            self._ready.set()
