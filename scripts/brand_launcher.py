"""Embed the existing Think Aloud identity in a distlib Windows PE stub.

Only icon and version resources are replaced; the launcher's manifest and code
are preserved. Call before appending the relative shebang and Python ZIP.
"""
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import re
import struct
from tempfile import TemporaryDirectory


def icon_resources(data):
    if len(data) < 6:
        raise ValueError('Truncated brand icon')
    reserved, kind, count = struct.unpack_from('<HHH', data)
    if reserved or kind != 1 or not 1 <= count <= 64 or len(data) < 6 + 16 * count:
        raise ValueError('Invalid brand icon directory')
    group = bytearray(struct.pack('<HHH', 0, 1, count))
    images = []
    for index in range(count):
        position = 6 + index * 16
        size, offset = struct.unpack_from('<II', data, position + 8)
        if not size or offset < 6 + 16 * count or offset + size > len(data):
            raise ValueError('Invalid brand icon image')
        group.extend(data[position:position + 12])
        group.extend(struct.pack('<H', index + 1))
        images.append(data[offset:offset + size])
    return bytes(group), images


def version_resource(version):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.+-]+)?', version)
    if not match or any(int(n) > 65535 for n in match.groups()):
        raise ValueError('Invalid executable version')
    major, minor, patch = map(int, match.groups())

    def block(key, value=b'', children=(), text=False):
        body = bytearray(b'\0' * 6 + (key + '\0').encode('utf-16le'))
        body.extend(b'\0' * (-len(body) % 4))
        body.extend(value)
        for child in children:
            body.extend(b'\0' * (-len(body) % 4))
            body.extend(child)
        struct.pack_into('<HHH', body, 0, len(body), len(value) // 2 if text else len(value), int(text))
        return bytes(body)

    strings = {
        'FileDescription': 'Think Aloud', 'ProductName': 'Think Aloud',
        'FileVersion': version, 'ProductVersion': version,
        'OriginalFilename': 'Think Aloud.exe', 'InternalName': 'Think Aloud',
    }
    table = block('040904B0', children=[block(key, (value + '\0').encode('utf-16le'), text=True)
                                      for key, value in strings.items()], text=True)
    fixed = struct.pack('<13I', 0xFEEF04BD, 0x10000, major << 16 | minor, patch << 16,
                        major << 16 | minor, patch << 16, 0x3F,
                        2 if '-' in version else 0, 0x40004, 1, 0, 0, 0)
    return block('VS_VERSION_INFO', fixed, [block('StringFileInfo', children=[table], text=True),
                 block('VarFileInfo', children=[block('Translation', struct.pack('<HH', 0x409, 1200))], text=True)])


def branded_stub(stub, icon, version):
    group, images = icon_resources(icon)
    version_data = version_resource(version)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    ptr = ctypes.c_void_p
    kernel.LoadLibraryExW.argtypes = [W.LPCWSTR, W.HANDLE, W.DWORD]
    kernel.LoadLibraryExW.restype = W.HMODULE
    kernel.FreeLibrary.argtypes = [W.HMODULE]
    names_callback = ctypes.WINFUNCTYPE(W.BOOL, W.HMODULE, ptr, ptr, W.LPARAM)
    languages_callback = ctypes.WINFUNCTYPE(W.BOOL, W.HMODULE, ptr, ptr, W.WORD, W.LPARAM)
    kernel.EnumResourceNamesW.argtypes = [W.HMODULE, ptr, names_callback, W.LPARAM]
    kernel.EnumResourceNamesW.restype = W.BOOL
    kernel.EnumResourceLanguagesW.argtypes = [W.HMODULE, ptr, ptr, languages_callback, W.LPARAM]
    kernel.EnumResourceLanguagesW.restype = W.BOOL
    kernel.BeginUpdateResourceW.argtypes = [W.LPCWSTR, W.BOOL]
    kernel.BeginUpdateResourceW.restype = W.HANDLE
    kernel.UpdateResourceW.argtypes = [W.HANDLE, ptr, ptr, W.WORD, ptr, W.DWORD]
    kernel.UpdateResourceW.restype = W.BOOL
    kernel.EndUpdateResourceW.argtypes = [W.HANDLE, W.BOOL]
    kernel.EndUpdateResourceW.restype = W.BOOL

    def identifier(value):
        return value if value <= 65535 else ctypes.wstring_at(value)

    def resource_pointer(value):
        return ptr(value) if isinstance(value, int) else ctypes.cast(ctypes.c_wchar_p(value), ptr)

    with TemporaryDirectory(prefix='think-aloud-brand-') as temporary:
        target = Path(temporary) / 'launcher.exe'
        target.write_bytes(stub)
        module = kernel.LoadLibraryExW(str(target), None, 2)  # data only, never execute
        if not module:
            raise ctypes.WinError(ctypes.get_last_error())
        old, errors = [], []

        @languages_callback
        def language_found(_module, kind, name, language, _param):
            old.append((identifier(kind), identifier(name), language))
            return True

        @names_callback
        def name_found(module, kind, name, _param):
            if not kernel.EnumResourceLanguagesW(module, kind, name, language_found, 0):
                errors.append(ctypes.get_last_error())
            return True

        try:
            for kind in (3, 14, 16):  # RT_ICON, RT_GROUP_ICON, RT_VERSION
                if not kernel.EnumResourceNamesW(module, ptr(kind), name_found, 0):
                    error = ctypes.get_last_error()
                    if error != 1813:  # resource type absent in this stub
                        errors.append(error)
        finally:
            kernel.FreeLibrary(module)
        if errors:
            raise ctypes.WinError(errors[0])

        handle = kernel.BeginUpdateResourceW(str(target), False)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            for kind, name, language in old:
                if not kernel.UpdateResourceW(handle, resource_pointer(kind), resource_pointer(name), language, None, 0):
                    raise ctypes.WinError(ctypes.get_last_error())
            resources = [(14, 1, group), (16, 1, version_data)]
            resources.extend((3, index, data) for index, data in enumerate(images, 1))
            for kind, name, data in resources:
                buffer = ctypes.create_string_buffer(data)
                if not kernel.UpdateResourceW(handle, ptr(kind), ptr(name), 0, buffer, len(data)):
                    raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            kernel.EndUpdateResourceW(handle, True)
            raise
        if not kernel.EndUpdateResourceW(handle, False):
            raise ctypes.WinError(ctypes.get_last_error())
        return target.read_bytes()
