"""Regression checks for exports and the JavaScript bridge, using synthetic files."""
import inspect
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import app
import recorder


class ReleaseBoundaries(unittest.TestCase):
    def test_session_settings_do_not_copy_other_presets_or_credentials(self):
        cfg={'game':'Example','mic':'example-mic','transcription_provider':'later',
             'vault':'private-library','password':'private-secret','port':1234,
             'presets':{'other':{'vault':'other-private-library'}},'games':{'old':{}},
             'active_preset_id':'active','obsidian_exe':'private-program-path'}
        self.assertEqual(recorder.session_settings(cfg),
                         {'game':'Example','mic':'example-mic','transcription_provider':'later'})

    def test_bridge_exposes_only_contract_methods(self):
        class Service:
            root = Path.cwd()
            def set_window(self, window): pass
            def close_allowed(self): return True
        for name in app.BRIDGE_METHODS:
            setattr(Service, name, lambda self: None)
        facade = app.DesktopAPI(Service())
        public = {name: getattr(facade, name) for name in dir(facade) if not name.startswith('_')}
        self.assertEqual(set(public), set(app.BRIDGE_METHODS))
        self.assertTrue(all(inspect.ismethod(value) for value in public.values()))

    def test_export_does_not_include_unrelated_plugin_credentials(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / 'vault'
            session = vault / '场次' / 'synthetic'
            session.mkdir(parents=True)
            recorder.write(session / 'session.json', {'id': 'synthetic', 'state': '可回看'})
            (session / '复盘.md').write_text('Synthetic review note', encoding='utf-8')
            secret = vault / '.obsidian/plugins/unrelated/data.json'
            secret.parent.mkdir(parents=True)
            secret.write_text('{"key":"SYNTHETIC_SECRET_DO_NOT_EXPORT"}', encoding='utf-8')
            archive = recorder.Session(session).package()
            with zipfile.ZipFile(archive) as z:
                self.assertNotIn('.obsidian/plugins/unrelated/data.json', z.namelist())
                self.assertFalse(any(name.startswith('.obsidian/') for name in z.namelist()))
                self.assertFalse(any(b'SYNTHETIC_SECRET_DO_NOT_EXPORT' in z.read(n) for n in z.namelist()))


if __name__ == '__main__':
    unittest.main()
