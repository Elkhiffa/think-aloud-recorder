"""Exercise the real PE launcher from an unrelated working directory."""
import os
import ctypes
from ctypes import wintypes as W
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.build_portable import launcher_bytes
from scripts.brand_launcher import icon_resources


@unittest.skipUnless(os.name == 'nt', 'Windows launcher')
class NativeLauncherTests(unittest.TestCase):
    def test_launcher_finds_private_python_beside_it_from_any_working_directory(self):
        seed = Path(sys.executable).parent
        if not (seed / 'pythonw.exe').is_file():
            self.skipTest('Run using the prepared Windows runtime')
        with TemporaryDirectory(prefix='Recorder launcher ') as tmp:
            root = Path(tmp) / '中文 application with spaces'
            runtime = root / 'runtime'
            runtime.mkdir(parents=True)
            for source in [seed / 'pythonw.exe', *seed.glob('*.dll')]:
                shutil.copy2(source, runtime / source.name)
            (runtime / 'python312._pth').write_text(
                str(seed / 'Lib') + '\n' + str(seed / 'DLLs') + '\n..\n', encoding='utf-8')
            (root / 'portable_entry.py').write_text(
                'from pathlib import Path\n'
                'def main():\n'
                '    Path(__file__).with_name("confirmed.txt").write_text("private runtime reached")\n'
                '    return 0\n', encoding='utf-8')
            executable = root / 'Think Aloud.exe'
            executable.write_bytes(launcher_bytes('0.6.0-preview.5+local.3'))
            result = subprocess.run([str(executable)], cwd=tmp, timeout=20,
                                    capture_output=True, creationflags=0x08000000)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual((root / 'confirmed.txt').read_text(), 'private runtime reached')

    def test_windows_reads_brand_icon_and_version_from_executable(self):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.LoadLibraryExW.argtypes=[W.LPCWSTR,W.HANDLE,W.DWORD];kernel.LoadLibraryExW.restype=W.HMODULE
        kernel.FindResourceW.argtypes=[W.HMODULE,ctypes.c_void_p,ctypes.c_void_p];kernel.FindResourceW.restype=W.HANDLE
        kernel.LoadResource.argtypes=[W.HMODULE,W.HANDLE];kernel.LoadResource.restype=W.HANDLE
        kernel.SizeofResource.argtypes=[W.HMODULE,W.HANDLE];kernel.SizeofResource.restype=W.DWORD
        kernel.LockResource.argtypes=[W.HANDLE];kernel.LockResource.restype=ctypes.c_void_p
        kernel.FreeLibrary.argtypes=[W.HMODULE]
        def resource(module,kind,name):
            found=kernel.FindResourceW(module,name,kind)
            self.assertTrue(found,ctypes.get_last_error())
            size=kernel.SizeofResource(module,found)
            pointer=kernel.LockResource(kernel.LoadResource(module,found))
            return ctypes.string_at(pointer,size)
        with TemporaryDirectory() as tmp:
            file=Path(tmp)/'Think Aloud.exe'
            file.write_bytes(launcher_bytes('0.6.0-preview.5+local.3'))
            module=kernel.LoadLibraryExW(str(file),None,2)
            self.assertTrue(module)
            try:
                icon=(Path(__file__).resolve().parents[1]/'ui/brand.ico').read_bytes()
                group,images=icon_resources(icon)
                self.assertEqual(resource(module,14,1),group)
                for index,image in enumerate(images,1):
                    self.assertEqual(resource(module,3,index),image)
                self.assertIn(b'assembly',resource(module,24,1))
            finally:kernel.FreeLibrary(module)
            version=ctypes.WinDLL('version',use_last_error=True)
            version.GetFileVersionInfoSizeW.argtypes=[W.LPCWSTR,ctypes.POINTER(W.DWORD)]
            version.GetFileVersionInfoSizeW.restype=W.DWORD
            version.GetFileVersionInfoW.argtypes=[W.LPCWSTR,W.DWORD,W.DWORD,ctypes.c_void_p]
            version.VerQueryValueW.argtypes=[ctypes.c_void_p,W.LPCWSTR,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(W.UINT)]
            size=version.GetFileVersionInfoSizeW(str(file),None)
            self.assertGreater(size,0)
            data=ctypes.create_string_buffer(size)
            self.assertTrue(version.GetFileVersionInfoW(str(file),0,size,data))
            for key,expected in [('ProductName','Think Aloud'),('FileDescription','Think Aloud'),
                                 ('OriginalFilename','Think Aloud.exe'),('FileVersion','0.6.0-preview.5+local.3')]:
                pointer,length=ctypes.c_void_p(),W.UINT()
                self.assertTrue(version.VerQueryValueW(data,'\\StringFileInfo\\040904B0\\'+key,ctypes.byref(pointer),ctypes.byref(length)))
                self.assertEqual(ctypes.wstring_at(pointer),expected)


if __name__ == '__main__':
    unittest.main()
