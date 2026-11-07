"""After the app is updated, bring along the parts the user already has: the analysis skills in their agents and the
text-recognition component.

They are parts of one product, so an update the user started should leave them on the same version without the user
telling the parts apart. It runs once per app version, on the first start after an update (or a fresh install):
later starts leave a skill alone, so edits made after the update are not overwritten again. Only skills already
installed in an agent are updated, and the OCR component is fetched again only if an older one had been downloaded.
The 3 GB transcription model is left to its own prompt in settings.
"""
import json
from pathlib import Path

import skill_install
from update_installer import atomic_json

MARKER = 'state/components-version.json'


def _version(root):
    try:
        return json.loads((Path(root) / 'portable.json').read_text(encoding='utf-8')).get('version', '')
    except (OSError, ValueError):
        return ''


def due(root):
    """The app version that still needs its components brought along, or None."""
    version = _version(root)
    try:
        done = json.loads((Path(root) / MARKER).read_text(encoding='utf-8')).get('version')
    except (OSError, ValueError):
        done = None
    return version if version and version != done else None


def _ocr_was_downloaded(ocr):
    """An older component is recorded but this version needs another one."""
    try:
        entry = json.loads(ocr.registry.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return entry.get('model') == 'ocr' and entry.get('revision') != ocr.manifest['id']


def run(root, home, stamp, ocr=None, ocr_builtin=False):
    """Returns what was brought along, or None when nothing was due. Never raises: opening the recorder comes first."""
    version = due(root)
    if not version:
        return None
    note = dict(id=stamp, version=version, skills=[], ocr=None, errors=[])
    try:
        rows = skill_install.install(root, home, stamp, only_existing=True)['results']
        note['skills'] = sorted({row['agent'] for row in rows if row['state'] != 'unchanged'})
    except ValueError:
        pass  # no agent at all: nothing installed, nothing to bring along
    except Exception as error:  # a locked file must not stop the app; the manual button stays available
        note['errors'].append('分析 skill 没能同步：' + str(error))
    if ocr is not None and not ocr_builtin and ocr.status().get('state') == 'missing' and _ocr_was_downloaded(ocr):
        try:
            result = ocr.start_download()
            note['ocr'] = 'downloading' if not isinstance(result, dict) or result.get('ok', True) else None
        except Exception as error:
            note['errors'].append('识别组件没能开始下载：' + str(error))
    atomic_json(Path(root) / MARKER, dict(schema=1, version=version))
    return note
