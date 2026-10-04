"""Checkpoint contention regression: synthetic inputs and owned temporary files."""
import ctypes
import json
import os
from pathlib import Path
import shutil
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import input_capture
from tests.test_input_capture import Clock, Source


def denied(code=5):
    error = PermissionError(13, 'synthetic replacement conflict')
    error.winerror = code
    return error


class CheckpointRetryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def collector(self):
        self.clock, self.source = Clock(), Source()
        self.capture = input_capture.InputRecorder(self.folder, lambda: self.source,
                                                  clock=self.clock, flush_interval=60)
        self.capture.start(origin=100)
        self.addCleanup(self.capture.stop)
        self.source.callback(dict(type='focus', timestamp=100, foreground=True))
        return self.capture

    def tap(self, code, start, end):
        for at, down in ((start, True), (end, False)):
            self.clock.value = 100 + at
            self.source.callback(dict(type='button', timestamp=self.clock.value,
                                      device='keyboard', code=code, down=down, foreground=True))

    def test_access_and_sharing_conflicts_retry_the_same_completed_temp_file(self):
        for code in (5, 32, 33):
            with self.subTest(winerror=code):
                path = self.folder / 'checkpoint.json'
                path.write_text('{"old":true}', encoding='utf-8')
                replace = os.replace
                attempts = []

                def blocked(temp, destination):
                    attempts.append((temp, destination, temp.read_bytes()))
                    if len(attempts) <= 2:
                        self.assertEqual(path.read_text(encoding='utf-8'), '{"old":true}')
                        raise denied(code)
                    return replace(temp, destination)

                with patch.object(input_capture.os, 'replace', side_effect=blocked), \
                        patch.object(input_capture.time, 'sleep') as sleep:
                    input_capture._atomic_json(path, dict(new=True))
                self.assertEqual(len(attempts), 3)
                self.assertTrue(all(item == attempts[0] for item in attempts))
                self.assertEqual(sleep.call_count, 2)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8')), dict(new=True))

    def test_non_sharing_errors_fail_immediately_without_removing_checkpoint(self):
        path = self.folder / 'checkpoint.json'
        path.write_text('old checkpoint', encoding='utf-8')
        for error in (OSError(28, 'disk full'), FileNotFoundError(2, 'missing directory'),
                      PermissionError(13, 'not a Windows sharing result')):
            with self.subTest(error=error), \
                    patch.object(input_capture.os, 'replace', side_effect=error) as replace, \
                    patch.object(input_capture.time, 'sleep') as sleep:
                with self.assertRaises(OSError) as caught:
                    input_capture._atomic_json(path, dict(new=True))
                self.assertIs(caught.exception, error)
                replace.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(path.read_text(encoding='utf-8'), 'old checkpoint')

    def test_persistent_conflict_keeps_checkpoint_authority_and_reports_failure(self):
        capture = self.collector()
        original_checkpoint = capture.path.read_bytes()
        self.tap('A', 1, 1.1)
        self.source.callback(dict(type='button', timestamp=101.2, device='keyboard',
                                  code='W', down=True, foreground=True))
        self.source.callback(dict(type='watermark', timestamp=101.5))
        self.clock.value = 103
        replace = os.replace
        attempts = []

        def blocked(temp, destination):
            if destination == capture.path:
                attempts.append((temp, destination))
                raise denied()
            return replace(temp, destination)

        with patch.object(input_capture.os, 'replace', side_effect=blocked), \
                patch.object(input_capture.time, 'sleep') as sleep, \
                patch.object(capture, '_writer_stop', Mock(wait=Mock(return_value=False))):
            capture._write_loop()
        self.assertEqual(len(attempts), 7)
        self.assertAlmostEqual(sum(call.args[0] for call in sleep.call_args_list), .63)
        self.assertEqual(capture.path.read_bytes(), original_checkpoint)
        self.assertEqual(self.source.stopped, 1)
        self.assertEqual(capture.health()['state'], 'failed')
        diagnostic = json.loads((self.folder / 'input-capture-diagnostic.json').read_text(encoding='utf-8'))
        self.assertEqual(diagnostic['replace_attempts'], 7)
        self.assertEqual(diagnostic['winerror'], 5)
        self.assertEqual(diagnostic['confirmed_until_seconds'], 1.5)
        # A crash here must ignore the appended but uncheckpointed journal tail.
        recovered_folder = self.folder / 'crash-copy'
        recovered_folder.mkdir()
        for path in (capture.path, capture.journal_path):
            shutil.copy2(path, recovered_folder / path.name)
        recovered = input_capture.recover_capture(recovered_folder, duration=5)
        self.assertEqual(recovered['intervals'], [])
        # A live orderly stop may preserve real events still held by the collector.
        result = capture.stop(duration=5)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual([(i['code'], i['start'], i['end']) for i in result['intervals']],
                         [('A', 1, 1.1), ('W', 1.2, 1.5)])
        self.assertTrue(any(g['start'] == 1.5 and g['end'] == 5 for g in result['gaps']))

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_real_windows_reader_lock_does_not_stop_capture_or_duplicate_journal(self):
        """Reproduce WinError 5/32 with CreateFileW, never read actual devices."""
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        capture = self.collector()
        self.tap('A', 1, 1.1)
        original_checkpoint = capture.path.read_bytes()
        # A ordinary reader can share reads/writes while denying replacement.
        handle = kernel.CreateFileW(str(capture.path), 0x80000000, 0x1 | 0x2,
                                    None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        denied_once = threading.Event()
        errors, conflicts = [], []
        replace = os.replace

        def observed_replace(temp, destination):
            try:
                return replace(temp, destination)
            except OSError as error:
                if destination == capture.path:
                    conflicts.append(error.winerror)
                    denied_once.set()
                raise

        def flush():
            try:
                capture._flush()
            except Exception as error:
                errors.append(error)

        with patch.object(input_capture.os, 'replace', side_effect=observed_replace):
            writer = threading.Thread(target=flush)
            writer.start()
            try:
                self.assertTrue(denied_once.wait(2), 'owned reader must actually deny replacement')
                self.assertEqual(capture.path.read_bytes(), original_checkpoint)
                producer = threading.Thread(target=lambda: self.tap('B', 2, 2.1))
                producer.start()
                producer.join(.3)
                self.assertFalse(producer.is_alive(), 'replacement retries must not lock input callbacks')
                self.assertEqual(capture.health()['state'], 'recording')
            finally:
                kernel.CloseHandle(handle)
                writer.join(3)
            self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(conflicts and all(code in (5, 32, 33) for code in conflicts))
        capture._flush()
        result = capture.stop(duration=3)
        self.assertEqual(result['state'], 'complete')
        self.assertEqual([(i['code'], i['start'], i['end']) for i in result['intervals']],
                         [('A', 1, 1.1), ('B', 2, 2.1)])
        rows = [json.loads(line)['value'] for line in capture.journal_path.read_text(encoding='utf-8').splitlines()
                if json.loads(line)['type'] == 'interval']
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({row['id'] for row in rows}), 2)
        self.assertFalse((self.folder / 'input-capture-diagnostic.json').exists())


if __name__ == '__main__':
    unittest.main()
