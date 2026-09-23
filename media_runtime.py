"""Resolve the isolated media CLI without changing OBS or Python's native libraries."""
import hashlib
import json
from pathlib import Path
import re

MEDIA_DIRECTORY = 'runtime/Lib/think_aloud_media'
MEDIA_EXECUTABLE = MEDIA_DIRECTORY + '/ffmpeg.exe'


def verify_media(root):
    """Validate the prepared closure at build/self-check time, not every UI launch."""
    base = Path(root) / MEDIA_DIRECTORY
    manifest = json.loads((base / 'provenance.json').read_text(encoding='utf-8'))
    if manifest.get('schema') != 1 or manifest.get('executable') != 'ffmpeg.exe':
        raise ValueError('Invalid media runtime provenance')
    records = manifest.get('files')
    if not isinstance(records, list) or not records:
        raise ValueError('Empty media runtime inventory')
    names = set()
    for item in records:
        name = item.get('filename', '')
        if (not re.fullmatch(r'[A-Za-z0-9_.-]+\.(?:exe|dll)', name)
                or name.casefold() in names):
            raise ValueError('Invalid media runtime filename')
        names.add(name.casefold())
        path = base / name
        if (path.is_symlink() or not path.resolve().is_relative_to(base.resolve())
                or not path.is_file() or path.stat().st_size != item.get('bytes')
                or hashlib.sha256(path.read_bytes()).hexdigest() != item.get('sha256')):
            raise ValueError('Media runtime mismatch: ' + name)
    if 'ffmpeg.exe' not in names:
        raise ValueError('Missing FFmpeg inventory entry')
    actual = {p.name.casefold() for p in base.iterdir() if p.suffix.lower() in ('.exe', '.dll')}
    if actual != names:
        raise ValueError('Unlisted media runtime binary')
    return manifest


def resolve_ffmpeg(root):
    root = Path(root)
    executable = root / MEDIA_EXECUTABLE
    if executable.is_file():
        return str(executable)
    # A packaged install must not silently switch to a PATH/env/wheel binary.
    # The repository retains a historical portable.json template. A Git
    # checkout without a prepared runtime is still a development environment.
    if ((root / 'portable.json').exists() and not (root / '.git').exists()
            or (root / 'package-manifest.json').exists()
            or (root / MEDIA_DIRECTORY).exists()):
        raise RuntimeError('缺少随软件提供的音视频处理组件，请重新解压完整软件包。')
    # Source checkouts may use the existing development dependency.
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()
