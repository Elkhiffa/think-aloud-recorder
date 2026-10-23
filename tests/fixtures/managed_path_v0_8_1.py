"""managed_path as shipped in v0.8.1 (git show v0.8.1:update_installer.py, lines 69-95), copied verbatim.

In-app updates are checked by the INSTALLED version's updater, so every path in a new package must pass this
older check too; 0.9.0 shipped app/tools/fonts/provenance.json, which this refuses, and could not be installed
from 0.8.x. Only the error type is local.
"""
import re
import unicodedata


class UpdateError(Exception):
    pass


def safe_name(name):
    if (not isinstance(name, str) or not name or len(name) > 240 or '\\' in name
            or name.startswith('/') or any(ord(c) < 32 for c in name)):
        raise UpdateError('更新包包含不安全的路径。')
    for part in name.split('/'):
        if (part in ('', '.', '..') or part.endswith((' ', '.')) or any(c in part for c in ':<>"|?*')
                or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part)):
            raise UpdateError('更新包包含不安全的 Windows 路径。')
    if unicodedata.normalize('NFC', name) != name: raise UpdateError('更新包路径编码不规范。')
    return name


def managed_path(name):
    safe_name(name)
    lower = name.casefold()
    if lower.startswith('app/'):
        lower = lower[4:]
        # Public vocabulary and the launcher belong beside app/, never inside it.
        if lower.startswith('vocabularies/') or lower.endswith('.exe') and '/' not in lower: return False
    if lower.startswith(('state/', 'secrets/', 'models/', 'staging/', 'tools/obs/config/')): return False
    if lower.startswith('vocabularies/'): return lower == 'vocabularies/uiux-terms.txt'
    if '/' not in lower:
        return lower.endswith('.py') or lower in {'think aloud.exe', 'experiencerecorder.exe', 'portable.json',
            'package-manifest.json', 'dependency-source-manifest.json', 'model-manifest.json',
            'requirements-lock.txt', 'license', 'third_party_notices.md', 'readme.md', 'player.html'}
    return lower.startswith(('runtime/', 'ui/', 'licenses/', 'docs/', 'scripts/', 'tools/input/',
                             'tools/obs/bin/', 'tools/obs/data/', 'tools/obs/obs-plugins/')) or lower == 'tools/obs/portable_mode.txt'
