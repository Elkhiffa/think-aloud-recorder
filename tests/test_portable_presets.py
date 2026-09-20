"""Each preset retains its own library across relocation; device IDs are machine-local."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import portable_config as config


class PortablePresets(unittest.TestCase):
    def test_all_internal_vaults_are_relative_without_mutating_live_settings(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();(root/'portable.json').write_text('{}')
            cfg={'vault':str(root/'A'),'presets':{'a':{'vault':str(root/'A')},
                'b':{'vault':str(root/'B')},'external':{'vault':str(root.parent/'external-library')}}}
            saved=config.stored_settings(root,cfg)
            self.assertEqual(saved['vault'],'A')
            self.assertEqual(saved['presets']['b']['vault'],'B')
            self.assertEqual(cfg['presets']['b']['vault'],str(root/'B'))
            self.assertEqual(saved['presets']['external']['vault'],str(root.parent/'external-library'))

    def test_relocated_legacy_absolute_vaults_and_new_machine_devices(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();old=root.parent/'previous-recorder'
            (root/'portable.json').write_text('{}')
            settings={'vault':str(old/'library-A'),'window':'old-window','monitor':'old-monitor',
                      'mic':'old-mic','configured':True,'game':'A'}
            cfg={**settings,'_portable_root':str(old),'_portable_machine':'previous-machine',
                 'active_preset_id':'b','presets':{'a':dict(settings),
                     'b':{**settings,'vault':str(old/'library-B'),'game':'B'}},'games':{}}
            config._write(root/'config.json',cfg)
            with patch.object(config,'_setup_obs'),patch.object(config,'_free_port',return_value=12345):
                config._initialize_locked(root,'new-machine')
            with patch.object(config,'initialize'):
                loaded=config.load_settings(root)
            self.assertEqual(loaded['active_preset_id'],'b')
            for ident,suffix in [('a','A'),('b','B')]:
                preset=loaded['presets'][ident]
                self.assertEqual(preset['vault'],str(root/('library-'+suffix)))
                self.assertFalse(preset['configured'])
                self.assertEqual(preset['window'],'')
                self.assertEqual(preset['monitor'],'')
                self.assertEqual(preset['mic'],'default')


if __name__=='__main__':unittest.main()
