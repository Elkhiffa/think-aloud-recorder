import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import httpx

import ocr_component
from ocr_component import MARKER, OcrComponent, ensure_importable

ROOT = Path(__file__).resolve().parents[1]


def wheel(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class OcrComponentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.payloads = {
            'probe_ocr-1.0-py3-none-any.whl': wheel({
                'probe_ocr_fixture/__init__.py': b'VALUE = 7\n',
                'probe_ocr-1.0.dist-info/METADATA': b'Name: probe-ocr\n'}),
            'probe_native-1.0-cp312-cp312-win_amd64.whl': wheel({
                'probe_native-1.0.data/platlib/probe_native_fixture.py': b'NATIVE = 1\n',
                'probe_native-1.0.data/scripts/probe.exe': b'MZ'}),
        }
        self.manifest = {'schema': 1, 'component': 'ocr', 'id': 'probe-1',
                         'files': [{'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                    'url': 'https://files.pythonhosted.org/packages/aa/bb/' + name}
                                   for name, data in self.payloads.items()]}
        self.components = []

    def tearDown(self):
        for component in self.components:
            component.pause_download()
            component.wait(5)
        self.tmp.cleanup()

    def component(self, handler=None):
        def serve(request):
            if handler:
                return handler(request)
            return httpx.Response(200, content=self.payloads[request.url.path.rsplit('/', 1)[-1]])
        component = OcrComponent(self.root, manifest=self.manifest,
                                 client_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(serve), **kw))
        self.components.append(component)
        return component

    def finish(self, component, expected):
        self.assertTrue(component.wait(10))
        self.assertEqual(component.status()['state'], expected, component.status())

    def test_shipped_manifest_pins_official_wheels(self):
        # 路径 1：安装版的设置页用随包清单构造组件。
        component = OcrComponent(ROOT)
        self.assertEqual(component.status()['state'] in ('missing', 'ready'), True)
        self.assertEqual(component.total, 68049623)
        self.assertTrue(all(item['url'].startswith('https://files.pythonhosted.org/') for item in component.files))

    def test_download_unpacks_like_site_packages_and_then_imports(self):
        # 路径 1：用户在设置里点“下载”，之后 context-build 在没有 OCR 的安装版 runtime 中运行。
        component = self.component()
        self.assertTrue(component.start_download()['ok'])
        self.finish(component, 'ready')
        site = self.root / 'models' / 'ocr' / 'probe-1' / 'site'
        self.assertEqual(component.site(), site)
        self.assertTrue((site / 'probe_ocr_fixture' / '__init__.py').is_file())
        self.assertTrue((site / 'probe_native_fixture.py').is_file())
        self.assertFalse(any('scripts' in path.parts for path in site.rglob('*')))
        self.assertEqual(json.loads((self.root / 'state' / 'ocr-component.json').read_text())['model'], 'ocr')
        real = importlib.util.find_spec
        missing = lambda name, *args: None if name == 'rapidocr_onnxruntime' else real(name, *args)
        with (patch.object(sys, 'path', list(sys.path)),
              patch.object(ocr_component.importlib.util, 'find_spec', side_effect=missing),
              patch.object(ocr_component, 'OcrComponent', return_value=component)):
            self.assertTrue(ensure_importable(self.root))
            self.assertEqual(sys.path[-1], str(site))
            self.assertEqual(importlib.import_module('probe_ocr_fixture').VALUE, 7)
        sys.modules.pop('probe_ocr_fixture', None)

    def test_missing_unpack_is_not_ready(self):
        # 路径 5：解压目录被手动删改后，不能继续报告“已准备好”。
        component = self.component()
        component.start_download()
        self.finish(component, 'ready')
        (component.site() / MARKER).unlink()
        self.assertEqual(component.status()['state'], 'missing')
        self.assertIsNone(component.site())

    def test_redirect_off_official_host_is_refused(self):
        # 路径 3：下载被重定向到非官方地址。
        component = self.component(lambda request: httpx.Response(302, headers={'Location': 'https://example.com/x.whl'}))
        component.start_download()
        self.finish(component, 'error')
        self.assertFalse((self.root / 'state' / 'ocr-component.json').exists())

    def test_wheel_escaping_its_folder_is_refused_and_leaves_nothing_unpacked(self):
        # 路径 3：清单固定的文件内容含越界路径（校验值随之固定，仍然拒绝解压）。
        name = 'probe_ocr-1.0-py3-none-any.whl'
        self.payloads[name] = wheel({'../escape.py': b'x'})
        item = self.manifest['files'][0]
        item.update(bytes=len(self.payloads[name]), sha256=hashlib.sha256(self.payloads[name]).hexdigest())
        component = self.component()
        component.start_download()
        self.finish(component, 'error')
        folder = self.root / 'models' / 'ocr' / 'probe-1'
        self.assertEqual(sorted(path.name for path in folder.iterdir() if path.is_dir()), [])
        self.assertFalse((self.root / 'models' / 'ocr' / 'escape.py').exists())

    def test_manifest_must_point_at_pythonhosted_wheels(self):
        for mutation in ('host', 'name'):
            with self.subTest(mutation=mutation):
                manifest = json.loads(json.dumps(self.manifest))
                if mutation == 'host':
                    manifest['files'][0]['url'] = 'https://example.com/' + manifest['files'][0]['name']
                else:
                    manifest['files'][0]['name'] = 'probe.zip'
                with self.assertRaises(ValueError):
                    OcrComponent(self.root, manifest=manifest)


if __name__ == '__main__':
    unittest.main()
