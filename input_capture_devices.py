"""Minimal SDL2 controller bridge. No library/device is opened on import."""
from __future__ import annotations
import ctypes as C
import math
import os
from pathlib import Path
from input_capture import InputCaptureError


XBOX_BUTTONS = ('A', 'B', 'X', 'Y', 'View', 'Guide', 'Menu', 'LS', 'RS',
                'LB', 'RB', 'DPadUp', 'DPadDown', 'DPadLeft', 'DPadRight',
                'Share', 'Paddle1', 'Paddle2', 'Paddle3', 'Paddle4', 'Touchpad')
PS_BUTTONS = ('Cross', 'Circle', 'Square', 'Triangle', 'Create', 'PS', 'Options',
              'L3', 'R3', 'L1', 'R1', 'DPadUp', 'DPadDown', 'DPadLeft', 'DPadRight',
              'Mute', 'Paddle1', 'Paddle2', 'Paddle3', 'Paddle4', 'Touchpad')


def resolve_sdl(root=None):
    candidate = os.environ.get('THINK_ALOUD_SDL2_PATH')
    path = Path(candidate) if candidate else Path(root or Path(__file__).resolve().parent) / 'tools' / 'input' / 'SDL2.dll'
    if not path.is_absolute() or not path.is_file():
        raise InputCaptureError('操作采集组件缺失，请使用包含 SDL2 的完整软件包。')
    return path


def normalized_axis(value):
    return max(-1., min(1., int(value) / 32767.))


def axis_event(device, axis, values):
    if axis < 4:
        base = 0 if axis < 2 else 2
        x, y = normalized_axis(values[base]), normalized_axis(values[base + 1])
        # Deadzone is applied to the vector; quantization limits file growth from
        # minute drift without changing button transition timestamps.
        if math.hypot(x, y) <= .18:
            x = y = 0.
        x, y = round(x * 20) / 20, round(y * 20) / 20
        return {'type': 'axis', 'device': device, 'code': 'LeftStick' if base == 0 else 'RightStick',
                'kind': 'axis', 'x': x, 'y': y, 'value': min(1., math.hypot(x, y))}
    value = max(0., normalized_axis(values[axis]))
    value = round(value * 20) / 20 if value > .08 else 0.
    code = ('L2' if axis == 4 else 'R2') if device == 'dualsense' else ('LT' if axis == 4 else 'RT')
    return {'type': 'axis', 'device': device, 'code': code, 'kind': 'trigger', 'value': value, 'x': 0, 'y': 0}


class ControllerEvent(C.Structure):
    _fields_ = [('type', C.c_uint32), ('timestamp', C.c_uint32), ('which', C.c_int32),
                ('control', C.c_uint8), ('state', C.c_uint8), ('padding', C.c_uint16),
                ('value', C.c_int16), ('pad', C.c_uint16)]


class Event(C.Union):
    _fields_ = [('type', C.c_uint32), ('controller', ControllerEvent), ('padding', C.c_uint8 * 56), ('align', C.c_uint64)]


class SDLControllers:
    """Called entirely on the Windows source thread that initialized SDL."""
    FLAGS = 0x2000 | 0x4000  # SDL_INIT_GAMECONTROLLER | SDL_INIT_EVENTS

    def __init__(self, path, emit, clock, foreground=lambda: True):
        self.emit, self.clock = emit, clock
        self.foreground = foreground
        self.controllers = {}
        self.dll = C.CDLL(str(path))
        specs = {
            'SDL_SetHint': ([C.c_char_p, C.c_char_p], C.c_int),
            'SDL_InitSubSystem': ([C.c_uint32], C.c_int),
            'SDL_QuitSubSystem': ([C.c_uint32], None),
            'SDL_NumJoysticks': ([], C.c_int),
            'SDL_IsGameController': ([C.c_int], C.c_int),
            'SDL_GameControllerOpen': ([C.c_int], C.c_void_p),
            'SDL_GameControllerClose': ([C.c_void_p], None),
            'SDL_GameControllerGetJoystick': ([C.c_void_p], C.c_void_p),
            'SDL_JoystickInstanceID': ([C.c_void_p], C.c_int32),
            'SDL_GameControllerGetType': ([C.c_void_p], C.c_int),
            'SDL_GameControllerGetAxis': ([C.c_void_p, C.c_int], C.c_int16),
            'SDL_GameControllerGetButton': ([C.c_void_p, C.c_int], C.c_uint8),
            'SDL_PollEvent': ([C.POINTER(Event)], C.c_int),
            'SDL_GetTicks': ([], C.c_uint32),
            'SDL_GameControllerUpdate': ([], None),
        }
        for name, (args, restype) in specs.items():
            fn = getattr(self.dll, name)
            fn.argtypes, fn.restype = args, restype
        self.dll.SDL_SetHint(b'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS', b'1')
        self.dll.SDL_SetHint(b'SDL_JOYSTICK_HIDAPI_PS5', b'1')
        self.dll.SDL_SetHint(b'SDL_JOYSTICK_HIDAPI_PS5_RUMBLE', b'0')
        if self.dll.SDL_InitSubSystem(self.FLAGS) != 0:
            raise InputCaptureError('手柄采集组件初始化失败。')
        try:
            for index in range(self.dll.SDL_NumJoysticks()):
                self._open(index)
        except Exception:
            self.close()
            raise

    def _open(self, index):
        if not self.dll.SDL_IsGameController(index):
            return
        pointer = self.dll.SDL_GameControllerOpen(index)
        if not pointer:
            raise InputCaptureError('检测到手柄但无法打开，请检查设备连接。')
        ident = self.dll.SDL_JoystickInstanceID(self.dll.SDL_GameControllerGetJoystick(pointer))
        if ident in self.controllers:
            self.dll.SDL_GameControllerClose(pointer)
            return
        typ = self.dll.SDL_GameControllerGetType(pointer)
        device = 'dualsense' if typ == 7 else ('xbox' if typ in (1, 2) else None)
        if device is None:
            self.dll.SDL_GameControllerClose(pointer)
            return
        self.controllers[ident] = {'pointer': pointer, 'device': device, 'axes': [0] * 6}
        self.emit({'type': 'connect', 'device': device, 'timestamp': self.clock()})

    def pump(self):
        event = Event()
        while self.dll.SDL_PollEvent(C.byref(event)):
            e = event.controller
            if e.type == 0x653:
                self._open(e.which)
                continue
            item = self.controllers.get(e.which)
            if not item:
                continue
            now = self.clock()
            age = ((self.dll.SDL_GetTicks() - e.timestamp) & 0xffffffff) / 1000.
            stamp = now - age
            device = item['device']
            if e.type == 0x654:
                self.dll.SDL_GameControllerClose(item['pointer'])
                del self.controllers[e.which]
                self.emit({'type': 'disconnect', 'device': device, 'timestamp': now})
            elif e.type in (0x651, 0x652):
                names = PS_BUTTONS if device == 'dualsense' else XBOX_BUTTONS
                if e.control < len(names):
                    self.emit({'type': 'button', 'device': device, 'code': names[e.control],
                               'down': e.type == 0x651, 'timestamp': stamp})
            elif e.type == 0x650 and e.control < 6:
                item['axes'][e.control] = e.value
                self.emit(dict(axis_event(device, e.control, item['axes']), timestamp=stamp))

    def resume(self):
        """Read current state only once the target has regained foreground."""
        if not self.foreground():
            return
        self.dll.SDL_GameControllerUpdate()
        for item in self.controllers.values():
            device, pointer = item['device'], item['pointer']
            stamp = self.clock()
            names = PS_BUTTONS if device == 'dualsense' else XBOX_BUTTONS
            for button, code in enumerate(names):
                if not self.foreground():
                    return
                if self.dll.SDL_GameControllerGetButton(pointer, button):
                    self.emit({'type': 'button', 'device': device, 'code': code,
                               'down': True, 'timestamp': stamp, 'resumed': True})
            if not self.foreground():
                return
            item['axes'] = [self.dll.SDL_GameControllerGetAxis(pointer, axis) for axis in range(6)]
            for axis in (0, 2, 4, 5):
                self.emit(dict(axis_event(device, axis, item['axes']), timestamp=stamp, resumed=True))

    def close(self):
        for item in self.controllers.values():
            self.dll.SDL_GameControllerClose(item['pointer'])
        self.controllers.clear()
        self.dll.SDL_QuitSubSystem(self.FLAGS)
