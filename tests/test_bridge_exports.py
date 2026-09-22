"""Exercise pywebview's real export generator without a window or service jobs."""
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app import BRIDGE_METHODS, DesktopAPI
from desktop_service import DesktopService
import webview.util as webview_util


# An independent contract, rather than deriving expectations from the facade.
EXPECTED_EXPORTS = {
    'get_state': [],
    'refresh_devices': [],
    'save_settings': ['payload'],
    'save_preset': ['payload', 'preset_id'],
    'select_preset': ['id'],
    'choose_directory': ['kind'],
    'import_hotwords': ['current_text'],
    'choose_hotword_files': [],
    'open_dictionary_site': [],
    'open_bailian_console': [],
    'start_recording': ['payload'],
    'stop_recording': [],
    'process_session': ['id'],
    'open_review': ['id'],
    'rename_session': ['id', 'name'],
    'package_session': ['id'],
    'open_folder': ['id'],
    'open_raw': ['id'],
    'save_cloud_key': ['key'],
    'verify_cloud_key': [],
    'recover_cloud_task': ['id', 'task_id'],
    'model_action': ['action', 'path'],
}


class BridgeExportTests(unittest.TestCase):
    def test_real_pywebview_generator_exports_only_contract_with_exact_signatures(self):
        # Keep the actual bound methods, but never construct the service: no
        # configuration, model registry, OBS query, monitoring thread, or network.
        service = DesktopService.__new__(DesktopService)
        service.root = Path(__file__).resolve().parent.parent
        facade = DesktopAPI(service)
        scripts = []
        events = SimpleNamespace(
            before_load=threading.Event(),
            _pywebviewready=threading.Event(),
            loaded=threading.Event(),
        )
        window = SimpleNamespace(
            _js_api=facade,
            _functions={},
            _expose_lock=threading.RLock(),
            run_js=scripts.append,
            events=events,
        )

        # Replace only script loading/execution. The library's actual nested
        # get_functions(), generate_func(), and generate_js_object() all execute.
        with patch.object(webview_util, 'load_js_files',
                          return_value=('bootstrap-marker', '%(functions)s')):
            webview_util.inject_pywebview('edgechromium', window)
            self.assertTrue(events.loaded.wait(3), 'pywebview export generation timed out')

        self.assertTrue(events.before_load.is_set())
        self.assertTrue(events._pywebviewready.is_set(), 'export failed before bridge readiness')
        self.assertEqual(len(scripts), 2)
        self.assertEqual(scripts[0], 'bootstrap-marker')
        exports = json.loads(scripts[1])
        names = [entry['func'] for entry in exports]
        self.assertEqual(len(names), len(set(names)), 'duplicate exported names')
        self.assertEqual({entry['func']: entry['params'] for entry in exports}, EXPECTED_EXPORTS)
        self.assertEqual(set(BRIDGE_METHODS), set(EXPECTED_EXPORTS))
        self.assertFalse(any('.' in name for name in names), 'unexpected nested object exposure')
        self.assertTrue(set(names).isdisjoint({
            'root', 'set_window', 'close_allowed', 'unlink', 'write_text',
            'write_bytes', 'read_text', 'rename', 'rmdir', 'open',
        }))


if __name__ == '__main__':
    unittest.main()
