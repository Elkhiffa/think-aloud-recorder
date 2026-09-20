"""Exercise the real PE launcher from an unrelated working directory."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from scripts.build_portable import launcher_bytes


@unittest.skipUnless(os.name == 'nt', 'Windows launcher')
class NativeLauncherTests(unittest.TestCase):
    def test_launcher_finds_private_python_beside_it_from_any_working_directory(self):
        seed = Path(sys.executable).parent
        if not (seed / 'pythonw.exe').is_file():
            self.skipTest('Run using the prepared Windows runtime')
        with TemporaryDirectory(prefix='Recorder launcher ') as tmp:
            root = Path(tmp) / 'application with spaces'
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
            executable = root / 'Recorder.exe'
            executable.write_bytes(launcher_bytes())
            result = subprocess.run([str(executable)], cwd=tmp, timeout=20,
                                    capture_output=True, creationflags=0x08000000)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual((root / 'confirmed.txt').read_text(), 'private runtime reached')


if __name__ == '__main__':
    unittest.main()
