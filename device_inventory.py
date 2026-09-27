"""Read Windows device identities without opening capture streams or OBS sources.

IDs follow OBS's WASAPI/window/display property formats. These are availability
checks; configure_scene still verifies the selected target against OBS before
recording. No input listeners, screen pixels or microphone samples are read here.
"""
import ctypes as C
from ctypes import wintypes as W
from contextlib import contextmanager
import os
import uuid

import psutil


def item(name, value):
    return dict(itemName=name, itemValue=value, itemEnabled=True)


def window_id(title, window_class, executable):
    return ':'.join(value.replace('#', '#22').replace(':', '#3A')
                    for value in (title, window_class, executable))


def _dll(name, signatures):
    dll = C.WinDLL(name, use_last_error=True)
    for method, args, result in signatures:
        fn = getattr(dll, method)
        fn.argtypes, fn.restype = args, result
    return dll


class GUID(C.Structure):
    _fields_ = [('bytes', C.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__((C.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le))


class PropertyKey(C.Structure):
    _fields_ = [('fmtid', GUID), ('pid', W.DWORD)]


class VariantData(C.Union):
    _fields_ = [('pointer', C.c_void_p), ('alignment', C.c_ulonglong * 2)]


class PropVariant(C.Structure):
    _fields_ = [('vt', W.USHORT), ('reserved', W.USHORT * 3), ('data', VariantData)]


def _com(pointer, index, args=(), result=C.c_int32):
    table = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *args)(table[index])


def _checked(hr):
    if hr < 0:
        raise OSError('Windows 设备查询失败：0x%08X' % (hr & 0xffffffff))


@contextmanager
def _interface():
    pointer = C.c_void_p()
    try:
        yield pointer
    finally:
        if pointer.value:
            _com(pointer, 2, result=W.ULONG)(pointer)  # IUnknown::Release


def microphones():
    """IMMDevice enumeration only; never call IMMDevice::Activate/IAudioClient."""
    ole = _dll('ole32', [
        ('CoInitializeEx', [C.c_void_p, W.DWORD], C.c_int32),
        ('CoUninitialize', [], None),
        ('CoCreateInstance', [C.POINTER(GUID), C.c_void_p, W.DWORD, C.POINTER(GUID), C.POINTER(C.c_void_p)], C.c_int32),
        ('CoTaskMemFree', [C.c_void_p], None),
        ('PropVariantClear', [C.POINTER(PropVariant)], C.c_int32),
    ])
    initialized = ole.CoInitializeEx(None, 0)
    # A caller's STA is also valid. Balance only our successful COM initialize.
    if initialized not in (0, 1, -2147417850):
        _checked(initialized)
    try:
        with _interface() as enumerator, _interface() as collection:
            _checked(ole.CoCreateInstance(C.byref(GUID('bcde0395-e52f-467c-8e3d-c4579291692e')), None, 1,
                C.byref(GUID('a95664d2-9614-4f35-a746-de8db63617e6')), C.byref(enumerator)))
            _checked(_com(enumerator, 3, (C.c_int, W.DWORD, C.POINTER(C.c_void_p)))(
                enumerator, 1, 1, C.byref(collection)))  # eCapture, DEVICE_STATE_ACTIVE
            count = W.UINT()
            _checked(_com(collection, 3, (C.POINTER(W.UINT),))(collection, C.byref(count)))
            result = []
            for index in range(count.value):
                with _interface() as device, _interface() as properties:
                    if _com(collection, 4, (W.UINT, C.POINTER(C.c_void_p)))(collection, index, C.byref(device)) < 0:
                        continue  # May disappear during enumeration.
                    identity = C.c_void_p()
                    try:
                        _checked(_com(device, 5, (C.POINTER(C.c_void_p),))(device, C.byref(identity)))
                        value = C.wstring_at(identity) if identity.value else ''
                    finally:
                        ole.CoTaskMemFree(identity)
                    if not value:
                        continue
                    label = value
                    if _com(device, 4, (W.DWORD, C.POINTER(C.c_void_p)))(device, 0, C.byref(properties)) >= 0:
                        key = PropertyKey(GUID('a45c254e-df1c-4efd-8020-67d146a850e0'), 14)
                        variant = PropVariant()
                        try:
                            hr = _com(properties, 5, (C.POINTER(PropertyKey), C.POINTER(PropVariant)))(
                                properties, C.byref(key), C.byref(variant))
                            if hr >= 0 and variant.vt == 31 and variant.data.pointer:
                                label = C.wstring_at(variant.data.pointer) or value
                        finally:
                            ole.PropVariantClear(C.byref(variant))
                    result.append(item(label, value))
            with _interface() as default:
                hr = _com(enumerator, 4, (C.c_int, C.c_int, C.POINTER(C.c_void_p)))(
                    enumerator, 1, 2, C.byref(default))  # Same eCommunications default as OBS.
                if hr >= 0 and default.value and result:
                    result.insert(0, item('默认麦克风', 'default'))
            return result
    finally:
        if initialized in (0, 1):
            ole.CoUninitialize()


class MonitorInfo(C.Structure):
    _fields_ = [('cbSize', W.DWORD), ('rcMonitor', W.RECT), ('rcWork', W.RECT),
                ('dwFlags', W.DWORD), ('szDevice', W.WCHAR * 32)]


class DisplayDevice(C.Structure):
    _fields_ = [('cb', W.DWORD), ('DeviceName', W.WCHAR * 32), ('DeviceString', W.WCHAR * 128),
                ('StateFlags', W.DWORD), ('DeviceID', W.WCHAR * 128), ('DeviceKey', W.WCHAR * 128)]


def monitors():
    callback = C.WINFUNCTYPE(W.BOOL, W.HANDLE, W.HDC, C.POINTER(W.RECT), W.LPARAM)
    user = _dll('user32', [
        ('EnumDisplayMonitors', [W.HDC, C.POINTER(W.RECT), callback, W.LPARAM], W.BOOL),
        ('GetMonitorInfoW', [W.HANDLE, C.POINTER(MonitorInfo)], W.BOOL),
        ('EnumDisplayDevicesW', [W.LPCWSTR, W.DWORD, C.POINTER(DisplayDevice), W.DWORD], W.BOOL),
    ])
    result = []

    @callback
    def visit(handle, _dc, _rect, _data):
        info = MonitorInfo(cbSize=C.sizeof(MonitorInfo))
        if user.GetMonitorInfoW(handle, C.byref(info)):
            device = DisplayDevice(cb=C.sizeof(DisplayDevice))
            found = user.EnumDisplayDevicesW(info.szDevice, 0, C.byref(device), 1)
            identity = device.DeviceID if found and device.DeviceID else info.szDevice
            rect = info.rcMonitor
            label = f'{device.DeviceString or info.szDevice}: {rect.right-rect.left}×{rect.bottom-rect.top}'
            if info.dwFlags & 1:
                label += '（主显示器）'
            result.append(item(label, identity))
        return True

    if not user.EnumDisplayMonitors(None, None, visit, 0):
        raise OSError('无法读取当前显示器列表。')
    return result


def windows():
    callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    user = _dll('user32', [
        ('EnumWindows', [callback, W.LPARAM], W.BOOL),
        ('IsWindowVisible', [W.HWND], W.BOOL),
        ('GetWindowLongPtrW', [W.HWND, C.c_int], C.c_ssize_t),
        ('GetWindowTextLengthW', [W.HWND], C.c_int),
        ('GetWindowTextW', [W.HWND, W.LPWSTR, C.c_int], C.c_int),
        ('GetClassNameW', [W.HWND, W.LPWSTR, C.c_int], C.c_int),
        ('GetWindowThreadProcessId', [W.HWND, C.POINTER(W.DWORD)], W.DWORD),
        ('FindWindowExW', [W.HWND, W.HWND, W.LPCWSTR, W.LPCWSTR], W.HWND),
    ])
    dwm = _dll('dwmapi', [('DwmGetWindowAttribute', [W.HWND, W.DWORD, C.c_void_p, W.DWORD], C.c_int32)])
    internal = {'startmenuexperiencehost.exe', 'applicationframehost.exe', 'peopleexperiencehost.exe',
        'shellexperiencehost.exe', 'microsoft.notes.exe', 'systemsettings.exe', 'textinputhost.exe',
        'searchapp.exe', 'video.ui.exe', 'searchui.exe', 'lockapp.exe', 'cortana.exe', 'gamebar.exe',
        'tabtip.exe', 'time.exe'}
    result = []

    def pid_of(handle):
        pid = W.DWORD()
        user.GetWindowThreadProcessId(handle, C.byref(pid))
        return pid.value

    def describe(handle):
        pid = pid_of(handle)
        if not pid or pid == os.getpid():
            return
        try:
            executable = psutil.Process(pid).name()
        except psutil.Error:
            return
        if executable.casefold() in internal or executable.casefold().startswith('windowsinternal'):
            return
        length = user.GetWindowTextLengthW(handle)
        if not 0 < length <= 32767:
            return
        title, cls = C.create_unicode_buffer(length+1), C.create_unicode_buffer(256)
        if user.GetWindowTextW(handle, title, len(title)) and user.GetClassNameW(handle, cls, len(cls)):
            result.append(item(f'[{executable}]: {title.value}', window_id(title.value, cls.value, executable)))

    @callback
    def visit(handle, _data):
        if not user.IsWindowVisible(handle) or user.GetWindowLongPtrW(handle, -20) & 0x80 or user.GetWindowLongPtrW(handle, -16) & 0x40000000:
            return True
        cloaked = W.DWORD()
        if dwm.DwmGetWindowAttribute(handle, 14, C.byref(cloaked), C.sizeof(cloaked)) >= 0 and cloaked.value:
            return True
        cls = C.create_unicode_buffer(256)
        user.GetClassNameW(handle, cls, len(cls))
        if cls.value in ('ApplicationFrameWindow', 'WinUIDesktopWin32WindowClass'):
            parent_pid, child = pid_of(handle), user.FindWindowExW(handle, None, None, None)
            while child:
                if pid_of(child) != parent_pid:
                    describe(child)
                    return True
                child = user.FindWindowExW(handle, child, None, None)
        describe(handle)
        return True

    if not user.EnumWindows(visit, 0):
        raise OSError('无法读取当前窗口列表。')
    return result


def devices(check=lambda: None):
    if os.name != 'nt':
        raise OSError('录制设备列表仅支持 Windows。')
    result = {}
    for key, query in (('mic', microphones), ('window', windows), ('monitor', monitors)):
        check()
        result[key] = query()
    check()
    return result
