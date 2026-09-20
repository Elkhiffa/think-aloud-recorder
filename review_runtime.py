"""Locate a separately installed Obsidian. Never download or bundle its binary."""
import os
from pathlib import Path


def find_obsidian(configured=None):
    candidates = [Path(configured)] if configured else []
    for variable, suffix in (
        ('LOCALAPPDATA', 'Programs/Obsidian/Obsidian.exe'),
        ('PROGRAMFILES', 'Obsidian/Obsidian.exe'),
        ('PROGRAMFILES(X86)', 'Obsidian/Obsidian.exe'),
    ):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / suffix)
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Obsidian.exe') as key:
                    candidates.append(Path(winreg.QueryValueEx(key, '')[0].strip('"')))
            except OSError:
                pass
    return next((p.resolve() for p in candidates if p.name.lower() == 'obsidian.exe' and p.is_file()), None)
