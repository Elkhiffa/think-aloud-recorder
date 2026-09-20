"""Keep service credentials outside session exports, encrypted for this Windows user."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import uuid

SECRET_DIR = Path(__file__).resolve().parent / 'state' / 'secrets'


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def _crypt(value, decrypt=False):
    if os.name != 'nt':
        raise RuntimeError('密钥存储需要 Windows 用户加密服务。')
    buf = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    source = Blob(len(value), buf)
    result = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    # CRYPTPROTECT_UI_FORBIDDEN; no machine-wide flag, so only this user can decrypt.
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise RuntimeError('无法读取或保存本机密钥，请在“转写服务”中重新填写 API Key。')
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        kernel.LocalFree(ctypes.cast(result.data, ctypes.c_void_p))


def _path(region, directory=None):
    if region != 'beijing':
        raise ValueError('当前录音转写使用华北 2（北京）地域。')
    return Path(directory or SECRET_DIR) / ('dashscope-' + region + '.dpapi')


def has_key(region='beijing', directory=None):
    try:
        return bool(load_key(region, directory))
    except (OSError, RuntimeError, UnicodeError):
        # A copied DPAPI file belongs to the original Windows account/computer.
        return False


def load_key(region='beijing', directory=None):
    path = _path(region, directory)
    return _crypt(path.read_bytes(), decrypt=True).decode('utf-8') if path.is_file() else ''


def save_key(key, region='beijing', directory=None):
    key = key.strip()
    if not key or any(char.isspace() for char in key) or len(key) > 4096:
        raise ValueError('请填写完整的 API Key，不要包含空格或换行。')
    path = _path(region, directory)
    encrypted = _crypt(key.encode('utf-8'))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temporary.open('wb') as output:
            output.write(encrypted)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def delete_key(region='beijing', directory=None):
    _path(region, directory).unlink(missing_ok=True)
