import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

import httpx

from model_manager import ModelManager


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.payloads = {'config.json': b'{"model":"fixture"}', 'model.bin': b'0123456789abcdefghij'}
        self.manifest = {
            'model': 'large-v3', 'repository': 'Systran/faster-whisper-large-v3',
            'revision': 'a' * 40,
            'files': [{'name': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                      for name, data in self.payloads.items()]}
        self.calls = []
        self.managers = []

    def tearDown(self):
        for manager in self.managers:
            manager.pause_download()
            manager.wait(5)
        self.tmp.cleanup()

    def manager(self, handler=None, root=None):
        def serve(request):
            self.calls.append(request)
            if handler:
                return handler(request)
            data = self.payloads[request.url.path.rsplit('/', 1)[-1]]
            if 'range' in request.headers:
                start = int(request.headers['range'][6:-1])
                return httpx.Response(206, content=data[start:], headers={
                    'Content-Range': f'bytes {start}-{len(data)-1}/{len(data)}'})
            return httpx.Response(200, content=data)
        manager = ModelManager(root or self.root, manifest=self.manifest,
                               client_factory=lambda **kw: httpx.Client(transport=httpx.MockTransport(serve), **kw))
        self.managers.append(manager)
        return manager

    def existing(self, name='existing'):
        directory = self.root / name
        directory.mkdir()
        for file, data in self.payloads.items():
            (directory / file).write_bytes(data)
        return directory

    def finish(self, manager, expected='ready'):
        self.assertTrue(manager.wait(10))
        self.assertEqual(manager.status()['state'], expected, manager.status())

    def test_missing_construction_never_connects(self):
        m = self.manager(lambda _: self.fail('unexpected network'))
        self.assertEqual(m.status()['state'], 'missing')
        self.assertIsNone(m.resolve_model())
        self.assertFalse((self.root / 'state').exists())

    def test_download_hashes_all_and_atomically_registers(self):
        m = self.manager()
        self.assertTrue(m.start_download()['ok'])
        self.finish(m)
        directory = self.root / 'models' / 'large-v3'
        self.assertEqual(m.resolve_model(), str(directory))
        self.assertEqual(m.status()['downloaded_bytes'], sum(map(len, self.payloads.values())))
        registry = json.loads(m.registry.read_text())
        self.assertTrue(registry['relative'])
        self.assertEqual(set(registry['files']), set(self.payloads))
        for name, data in self.payloads.items():
            self.assertEqual((directory / name).read_bytes(), data)
            self.assertEqual((directory / ('.' + name + '.part')).read_bytes(), data)
        self.assertEqual(self.manager().resolve_model(), str(directory))

    def test_import_no_copy_or_network_then_worker_reloads_registry(self):
        external = self.existing()
        m = self.manager(lambda _: self.fail('unexpected network'))
        worker = self.manager()
        self.assertIsNone(worker.resolve_model())
        self.assertTrue(m.use_existing(external)['ok'])
        self.finish(m)
        self.assertEqual(worker.resolve_model(), str(external))
        self.assertFalse((self.root / 'models').exists())

    def test_missing_or_changed_file_revokes_ready(self):
        for kind in ('missing', 'same_size_changed', 'size_changed'):
            with self.subTest(kind=kind):
                directory = self.existing(kind)
                m = self.manager()
                m.use_existing(directory)
                self.finish(m)
                file = directory / 'model.bin'
                if kind == 'missing':
                    file.unlink()
                elif kind == 'same_size_changed':
                    stat = file.stat()
                    file.write_bytes(b'x' * stat.st_size)
                    os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
                else:
                    file.write_bytes(b'x')
                self.assertIsNone(m.resolve_model())
                self.assertEqual(m.status()['state'], 'missing')

    def test_registry_cannot_claim_wrong_revision_hash_or_escape(self):
        m = self.manager()
        m.use_existing(self.existing())
        self.finish(m)
        original = json.loads(m.registry.read_text())
        for mutation in ('hash', 'revision', 'path'):
            entry = json.loads(json.dumps(original))
            if mutation == 'hash':
                entry['files']['model.bin']['sha256'] = '0' * 64
            elif mutation == 'revision':
                entry['revision'] = 'b' * 40
            else:
                entry['path'] = '../existing'
            m.registry.write_text(json.dumps(entry))
            self.assertIsNone(m.resolve_model())

    def test_move_entire_software_keeps_relative_registry(self):
        m = self.manager()
        m.start_download()
        self.finish(m)
        moved = self.root / 'moved'
        moved.mkdir()
        shutil.move(str(self.root / 'models'), moved / 'models')
        shutil.move(str(self.root / 'state'), moved / 'state')
        self.assertEqual(self.manager(root=moved).resolve_model(), str(moved / 'models' / 'large-v3'))

    def test_external_registry_is_absolute(self):
        m = self.manager(root=self.root / 'software')
        external = self.existing()
        m.use_existing(external)
        self.finish(m)
        entry = json.loads(m.registry.read_text())
        self.assertFalse(entry['relative'])
        self.assertEqual(entry['path'], str(external))

    def test_bad_import_does_not_publish_any_registry(self):
        directory = self.existing()
        (directory / 'model.bin').write_bytes(b'x' * 20)
        m = self.manager()
        m.use_existing(directory)
        self.finish(m, 'error')
        self.assertFalse(m.registry.exists())
        self.assertIsNone(m.resolve_model())

    def test_bad_download_never_ready_and_preserves_part(self):
        def bad(request):
            name = request.url.path.rsplit('/', 1)[-1]
            return httpx.Response(200, content=b'x' * len(self.payloads[name]))
        m = self.manager(bad)
        m.start_download()
        self.finish(m, 'error')
        self.assertIsNone(m.resolve_model())
        self.assertTrue((self.root / 'models/large-v3/.config.json.part').exists())
        self.assertFalse((self.root / 'models/large-v3/config.json').exists())

    def test_mismatching_completed_file_never_overwritten(self):
        directory = self.existing()
        file = directory / 'model.bin'
        file.write_bytes(b'x' * 20)
        m = self.manager()
        m.start_download(directory)
        self.finish(m, 'error')
        self.assertEqual(file.read_bytes(), b'x' * 20)
        self.assertEqual(self.calls, [])

    def test_valid_partial_resume_checks_overlap(self):
        directory = self.root / 'download'
        directory.mkdir()
        (directory / '.config.json.part').write_bytes(self.payloads['config.json'][:9])
        m = self.manager()
        m.OVERLAP = 4
        m.start_download(directory)
        self.finish(m)
        self.assertEqual(self.calls[0].headers['range'], 'bytes=5-')

    def test_invalid_partial_overlap_preserved(self):
        directory = self.root / 'download'
        directory.mkdir()
        part = directory / '.config.json.part'
        part.write_bytes(b'wrong1234')
        m = self.manager()
        m.start_download(directory)
        self.finish(m, 'error')
        self.assertEqual(part.read_bytes(), b'wrong1234')
        self.assertIsNone(m.resolve_model())

    def test_wrong_range_status_or_length_never_appends(self):
        for bad in ('status', 'range', 'length', 'encoding'):
            with self.subTest(bad=bad):
                directory = self.root / bad
                directory.mkdir()
                part = directory / '.config.json.part'
                original = self.payloads['config.json'][:5]
                part.write_bytes(original)
                def response(request):
                    data = self.payloads['config.json']
                    headers = {'Content-Length': str(len(data)),
                               'Content-Range': f'bytes 0-{len(data)-1}/{len(data)}'}
                    status = 206
                    if bad == 'status':
                        status = 200
                    elif bad == 'range':
                        headers['Content-Range'] = 'bytes 1-2/3'
                    elif bad == 'length':
                        headers['Content-Length'] = '999'
                    else:
                        headers['Content-Encoding'] = 'gzip'
                    return httpx.Response(status, headers=headers, stream=httpx.ByteStream(data))
                m = self.manager(response)
                m.start_download(directory)
                self.finish(m, 'error')
                self.assertEqual(part.read_bytes(), original)

    def test_zero_byte_part_can_resume(self):
        directory = self.root / 'download'
        directory.mkdir()
        (directory / '.config.json.part').touch()
        m = self.manager()
        m.start_download(directory)
        self.finish(m)

    @unittest.skipUnless(os.name == 'nt', 'Windows no-clobber rename fallback')
    def test_windows_disk_without_hardlinks_can_finish(self):
        m = self.manager()
        with patch('model_manager.os.link', side_effect=OSError('hardlinks unavailable')):
            m.start_download()
            self.finish(m)
        self.assertIsNotNone(m.resolve_model())

    def test_truncated_stream_retains_partial_and_can_resume(self):
        data = self.payloads['config.json']
        def truncated(request):
            return httpx.Response(200, headers={'Content-Length': str(len(data))},
                                  stream=httpx.ByteStream(data[:5]))
        m = self.manager(truncated)
        m.start_download()
        self.finish(m, 'error')
        self.assertEqual((self.root / 'models/large-v3/.config.json.part').read_bytes(), data[:5])
        self.assertIsNone(m.resolve_model())
        resumed = self.manager()
        resumed.start_download()
        self.finish(resumed)

    def test_excess_response_bytes_cannot_become_ready(self):
        data = self.payloads['config.json']
        def oversized(request):
            return httpx.Response(200, headers={'Content-Length': str(len(data))},
                                  stream=httpx.ByteStream(data + b'extra'))
        m = self.manager(oversized)
        m.start_download()
        self.finish(m, 'error')
        self.assertFalse(m.registry.exists())

    def test_failed_new_import_preserves_previous_valid_registration(self):
        original = self.existing()
        bad = self.existing('bad')
        (bad / 'model.bin').write_bytes(b'bad')
        m = self.manager()
        m.use_existing(original)
        self.finish(m)
        before = m.registry.read_bytes()
        m.use_existing(bad)
        self.finish(m, 'error')
        self.assertEqual(m.registry.read_bytes(), before)
        self.assertEqual(m.resolve_model(), str(original))

    def test_pause_retains_partial_then_resume(self):
        holder = {}
        data = self.payloads['config.json']
        class Stream(httpx.SyncByteStream):
            def __iter__(self):
                yield data[:4]
                holder['manager'].pause_download()
                yield data[4:]
        def response(request):
            return httpx.Response(200, headers={'Content-Length': str(len(data))}, stream=Stream())
        m = self.manager(response)
        holder['manager'] = m
        m.CHUNK = 4
        m.start_download()
        self.finish(m, 'paused')
        part = self.root / 'models/large-v3/.config.json.part'
        self.assertEqual(part.read_bytes(), data[:4])
        self.assertIsNone(m.resolve_model())
        resumed = self.manager()
        resumed.start_download()
        self.finish(resumed)

    def test_import_and_download_mutually_exclusive(self):
        directory = self.existing()
        started = threading.Event()
        release = threading.Event()
        m = self.manager()
        original = m._verify
        def blocked(*args):
            started.set()
            release.wait(5)
            return original(*args)
        with patch.object(m, '_verify', blocked):
            m.use_existing(directory)
            self.assertTrue(started.wait(3))
            try:
                self.assertFalse(m.start_download()['ok'])
                self.assertFalse(m.use_existing(directory)['ok'])
                other = self.manager()
                other.start_download()
                self.finish(other, 'error')
            finally:
                release.set()
            self.finish(m)

    def test_offline_error_is_background_and_sanitized(self):
        def offline(request):
            raise httpx.ConnectError('secret signed-url should not escape', request=request)
        m = self.manager(offline)
        self.assertTrue(m.start_download()['ok'])
        self.finish(m, 'error')
        self.assertNotIn('secret', m.status()['error'])
        self.assertIsNone(m.resolve_model())

    def test_redirects_followed_only_to_official_https(self):
        for target in ('https://evil.example/file', 'http://huggingface.co/file'):
            m = self.manager(lambda request: httpx.Response(302, headers={'Location': target}))
            before = len(self.calls)
            m.start_download()
            self.finish(m, 'error')
            self.assertEqual(len(self.calls), before + 1)
        def good(request):
            name = request.url.path.rsplit('/', 1)[-1]
            if request.url.host == 'huggingface.co':
                return httpx.Response(302, headers={'Location': 'https://cdn-lfs.hf.co/' + name})
            return httpx.Response(200, content=self.payloads[name])
        m = self.manager(good)
        m.start_download()
        self.finish(m)

    def test_space_check_precedes_network(self):
        m = self.manager()
        with patch('model_manager.shutil.disk_usage', return_value=shutil._ntuple_diskusage(1, 1, 0)):
            m.start_download()
            self.finish(m, 'error')
        self.assertEqual(self.calls, [])

    def test_path_traversal_and_windows_special_names_rejected(self):
        for name in ('../model.bin', '/model.bin', 'sub/model.bin', 'sub\\model.bin',
                     'model.bin:stream', 'CON.json', 'LPT1.bin', 'model.bin.'):
            with self.subTest(name=name):
                self.manifest['files'][0]['name'] = name
                with self.assertRaises(ValueError):
                    self.manager()

    def test_file_change_during_hash_prevents_activation(self):
        directory = self.existing()
        m = self.manager()
        original = m._verify
        def changing(base, item):
            result = original(base, item)
            if item['name'] == 'model.bin':
                (base / 'config.json').write_bytes(b'changed')
            return result
        with patch.object(m, '_verify', changing):
            m.use_existing(directory)
            self.finish(m, 'error')
        self.assertFalse(m.registry.exists())


if __name__ == '__main__':
    unittest.main()
