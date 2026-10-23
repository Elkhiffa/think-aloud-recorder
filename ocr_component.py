"""Optional local OCR component: pinned wheels downloaded in the app, never packaged.

The bundled runtime has no rapidocr/OpenCV, and runtime/ is replaced on every update, so the wheels live under
models/ocr/<id>/ (kept across updates like the Whisper model) and are unpacked to site/ beside them. The download,
resume, hashing and registry are ModelManager's; this class only changes where the files come from and adds the
unpack step before the registry marks the component ready.
"""
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import uuid
from urllib.parse import urlsplit
import zipfile

from model_manager import ModelManager

MISSING = '识别组件未安装：在 设置 → 通用 里下载“识别组件”后重试。'
MARKER = '.component.json'


class OcrComponent(ModelManager):
    MANIFEST = 'docs/ocr-component.json'
    REGISTRY = 'ocr-component.json'
    LOCK = 'ocr-component.lock'
    THREAD = 'ocr-component'

    def _identity(self):
        return 'ocr', self.manifest['id']

    def default_directory(self):
        return self.root / 'models' / 'ocr' / self.manifest['id']

    def file_url(self, item):
        return item['url']

    def _validate_manifest(self):
        m = self.manifest
        if m.get('schema') != 1 or m.get('component') != 'ocr' or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', m.get('id', '')):
            raise ValueError('识别组件清单无效。')
        if not m.get('files'):
            raise ValueError('识别组件清单为空。')
        names = set()
        for item in m['files']:
            name = item.get('name', '')
            if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.whl', name) or name.lower() in names
                    or not str(item.get('url', '')).startswith('https://files.pythonhosted.org/packages/')
                    or not item['url'].endswith('/' + name)
                    or not isinstance(item.get('bytes'), int) or item['bytes'] <= 0
                    or not re.fullmatch(r'[a-f0-9]{64}', item.get('sha256', ''))):
                raise ValueError('识别组件清单文件名、来源、大小或校验值无效。')
            names.add(name.lower())

    @staticmethod
    def _official_request(request):
        url = urlsplit(str(request.url))
        if (url.scheme != 'https' or url.username or url.password or url.port not in (None, 443)
                or url.hostname != 'files.pythonhosted.org'):
            raise ValueError('识别组件下载地址不是官方 HTTPS 地址。')

    def _expected_marker(self):
        return {'id': self.manifest['id'], 'wheels': {item['name']: item['sha256'] for item in self.files}}

    def _unpacked(self, site):
        try:
            return json.loads((site / MARKER).read_text(encoding='utf-8')) == self._expected_marker()
        except (OSError, ValueError):
            return False

    def _read_ready(self):
        ready = super()._read_ready()
        return ready if ready and self._unpacked(Path(ready[0]) / 'site') else None

    def site(self):
        ready = self._read_ready()
        return Path(ready[0]) / 'site' if ready else None

    def _members(self, wheel):
        """(archive member, relative target) for what pip would put in site-packages."""
        for info in wheel.infolist():
            if info.is_dir():
                continue
            name = info.filename
            parts = PurePosixPath(name).parts
            if (name.startswith('/') or '\\' in name or ':' in name or not parts
                    or any(part in ('', '.', '..') for part in parts)):
                raise ValueError('识别组件文件路径无效：' + name)
            if parts[0].endswith('.data'):
                # Console scripts, headers and data files are not needed to import the packages.
                if len(parts) < 3 or parts[1] not in ('purelib', 'platlib'):
                    continue
                parts = parts[2:]
            yield info, PurePosixPath(*parts)

    def _prepare(self, directory):
        site = directory / 'site'
        if self._unpacked(site):
            return
        wheels = [zipfile.ZipFile(self._file(directory, item['name'])) for item in self.files]
        temp = directory / ('.site-' + uuid.uuid4().hex)
        try:
            members = [(wheel, info, relative) for wheel in wheels for info, relative in self._members(wheel)]
            if shutil.disk_usage(directory).free < sum(info.file_size for _, info, _ in members) + 16 * 1024 * 1024:
                raise ValueError('磁盘空间不足，无法解压识别组件。')
            temp.mkdir()
            for wheel, info, relative in members:
                self._check_pause()
                target = temp.joinpath(*relative.parts)
                if target.exists():
                    raise ValueError('识别组件文件重复：' + relative.as_posix())
                target.parent.mkdir(parents=True, exist_ok=True)
                with wheel.open(info) as source, target.open('xb') as output:
                    shutil.copyfileobj(source, output, self.CHUNK)
            (temp / MARKER).write_text(json.dumps(self._expected_marker(), indent=2), encoding='utf-8')
            self._check_pause()
            if site.exists():
                # An earlier unpack that no longer matches; set aside, never deleted (models/ is the user's area).
                os.rename(site, directory / ('.site-old-' + uuid.uuid4().hex))
            os.rename(temp, site)
        except BaseException:
            shutil.rmtree(temp, ignore_errors=True)
            raise
        finally:
            for wheel in wheels:
                wheel.close()


def ensure_importable(root=None):
    """Put the downloaded component on sys.path when the runtime itself has no OCR (the installed app).

    The development runtime has rapidocr installed and is left as it is. Appended, so the runtime's own numpy and
    onnxruntime are always the ones imported."""
    if importlib.util.find_spec('rapidocr_onnxruntime'):
        return True
    try:
        site = OcrComponent(root or Path(__file__).resolve().parent).site()
    except (OSError, ValueError, KeyError):
        return False
    if site is None:
        return False
    if str(site) not in sys.path:
        sys.path.append(str(site))
        importlib.invalidate_caches()
    return True
