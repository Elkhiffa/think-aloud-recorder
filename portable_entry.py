"""Entry point used by the native, relocatable Windows launcher."""
from pathlib import Path
import os
import runpy
import sys
import traceback


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
