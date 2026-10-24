import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app_paths import ELEVATED, open_externally
from portable_entry import restart_elevated


class RestartElevatedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'app'
        self.root.mkdir()
        (self.root.parent / 'Think Aloud.exe').write_bytes(b'MZ')
        patcher = patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(ELEVATED, None)

    def test_normal_start_asks_once_through_uac_and_hands_over(self):
        # 路径 1：从资源管理器打开安装版 → 普通权限 → 通过 UAC 以管理员身份重开启动器，本进程退出。
        shell32 = Mock(IsUserAnAdmin=Mock(return_value=0), ShellExecuteW=Mock(return_value=42))
        self.assertTrue(restart_elevated(self.root, shell32))
        args = shell32.ShellExecuteW.call_args.args
        self.assertEqual((args[1], args[2]), ('runas', str(self.root.parent / 'Think Aloud.exe')))
        self.assertNotIn(ELEVATED, os.environ)

    def test_declined_prompt_keeps_running_at_the_normal_level(self):
        # 路径 1：用户在 UAC 里点“否”（ShellExecute 返回 5）→ 照常以普通权限运行。
        shell32 = Mock(IsUserAnAdmin=Mock(return_value=0), ShellExecuteW=Mock(return_value=5))
        self.assertFalse(restart_elevated(self.root, shell32))
        self.assertNotIn(ELEVATED, os.environ)

    def test_elevated_instance_runs_and_marks_itself(self):
        # 路径 1：UAC 重开的那个实例：不再重开，并标记为管理员身份。
        shell32 = Mock(IsUserAnAdmin=Mock(return_value=1))
        self.assertFalse(restart_elevated(self.root, shell32))
        shell32.ShellExecuteW.assert_not_called()
        self.assertEqual(os.environ[ELEVATED], '1')

    def test_source_checkout_without_launcher_is_left_alone(self):
        (self.root.parent / 'Think Aloud.exe').unlink()
        shell32 = Mock(IsUserAnAdmin=Mock(return_value=0))
        self.assertFalse(restart_elevated(self.root, shell32))
        shell32.ShellExecuteW.assert_not_called()


class OpenExternallyTests(unittest.TestCase):
    def test_elevated_recorder_opens_through_the_shell(self):
        # 路径 1：以管理员身份运行时点“百炼控制台”等 → 浏览器由外壳以普通权限打开，不继承管理员身份。
        fallback = Mock()
        with patch.dict(os.environ, {ELEVATED: '1'}), patch('subprocess.Popen') as popen:
            self.assertTrue(open_externally('https://example.invalid/', fallback))
        popen.assert_called_once_with(['explorer.exe', 'https://example.invalid/'])
        fallback.assert_not_called()

    def test_normal_level_keeps_the_usual_opener(self):
        fallback = Mock(return_value=True)
        with patch.dict(os.environ, {}, clear=False), patch('subprocess.Popen') as popen:
            os.environ.pop(ELEVATED, None)
            self.assertTrue(open_externally('D:/synthetic-only/folder', fallback))
        fallback.assert_called_once_with('D:/synthetic-only/folder')
        popen.assert_not_called()


if __name__ == '__main__':
    unittest.main()
