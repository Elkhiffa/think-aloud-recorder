"""Entry point used by the native, relocatable Windows launcher."""
from pathlib import Path
import os
import runpy
import sys
import traceback


def restart_elevated(root, shell32=None):
    """Start the launcher again through UAC; True when it started and this process should end.

    A game run as administrator (燕云's launcher is) keeps keyboard and mouse Raw Input from a normal-level process
    while it is in front, so recordings lost every key and click made in the game; controllers were unaffected.
    The recorder therefore asks for administrator rights once per start. Declining the prompt keeps the normal
    level: everything works except keyboard/mouse capture while such a game is in front."""
    if shell32 is None:
        import ctypes
        shell32 = ctypes.windll.shell32
    if shell32.IsUserAnAdmin():
        # app_paths.open_externally then opens browsers and editors through the shell, at the user's normal level.
        from app_paths import ELEVATED
        os.environ[ELEVATED] = '1'
        return False
    launcher = root.parent / 'Think Aloud.exe'
    if not launcher.is_file():
        return False
    # ShellExecute returns a value above 32 on success; declining the prompt returns an error code.
    return shell32.ShellExecuteW(None, 'runas', str(launcher), None, str(root.parent), 1) > 32


def main():
    root = Path(__file__).resolve().parent
    sys.dont_write_bytecode = True
    os.chdir(root)
    # Child applications inherit a private, predictable runtime search path.
    os.environ.pop('PYTHONHOME', None)
    os.environ.pop('PYTHONPATH', None)
    os.environ['PYTHONNOUSERSITE'] = '1'
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    os.environ['HF_HUB_OFFLINE'] = '1'
    try:
        if '--self-check' in sys.argv:
            from portable_check import main as check
            return check()
        if restart_elevated(root):
            return 0
        from update_installer import ensure_launch_allowed
        ensure_launch_allowed(root)
        from portable_config import initialize
        initialize(root)
        runpy.run_module('app', run_name='__main__')
    except Exception:
        report = root / '启动错误.txt'
        report.write_text(traceback.format_exc(), encoding='utf-8')
        import tkinter as tk
        from tkinter import messagebox
        window = tk.Tk()
        window.withdraw()
        messagebox.showerror('记录器启动失败', str(sys.exc_info()[1]) + '\n\n'
                             '请把软件包全部解压到有写入权限的文件夹再运行。\n'
                             '界面需要 Microsoft Edge WebView2 Runtime；缺失时可从 Microsoft 官网安装。\n'
                             '详细信息已保存到：\n' + str(report), parent=window)
        window.destroy()
        return 1
