import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from portable_check import settings_for_check


class ReadOnlyCheckTests(unittest.TestCase):
    def test_moved_installation_does_not_initialize_or_rewrite_settings(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            data=json.dumps({'_portable_root':'C:/previous location','port':4567,
                'password':'synthetic sentinel','vault':'my library','presets':{'fixture':{'mic':'default'}}}).encode()
            (root/'config.json').write_bytes(data)
            with patch('portable_config.initialize',side_effect=AssertionError('must stay read only')):
                cfg=settings_for_check(root)
            self.assertEqual((root/'config.json').read_bytes(),data)
            self.assertEqual(cfg['vault'],str((root/'my library').resolve()))
            self.assertEqual(cfg['port'],4567)
            self.assertFalse((root/'tools').exists())

    def test_fresh_package_does_not_create_config_obs_or_library(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)/'app';root.mkdir()
            cfg=settings_for_check(root)
            self.assertEqual(cfg['vault'],str(root.parent.resolve()/'think-aloud-database'))
            self.assertEqual(list(root.iterdir()),[])

    def test_synthetic_recording_explicitly_keeps_initialization(self):
        with patch('portable_config.load_settings',return_value={'test':True}) as load:
            root=Path('fixture')
            self.assertEqual(settings_for_check(root,synthetic_recording=True),{'test':True})
            load.assert_called_once_with(root)


if __name__=='__main__':unittest.main()
