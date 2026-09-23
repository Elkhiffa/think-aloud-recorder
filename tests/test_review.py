"""Synthetic session files exercise real rendering and the restricted viewer API."""
import json
import hashlib
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile

import recorder
from review_runtime import ReviewAPI, prepare_window, render_player, review_payload


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / '合成 资料库' / '场次' / 'synthetic'
        self.folder.mkdir(parents=True)
        self.meta = dict(id='synthetic', game='合成测试 <script> %%CSS%%', state='可回看', test=True)
        self.segments = [dict(start=0, end=5, text='测试 </script><script>alert(1)</script>'),
                         dict(start=15, end=20, text='第二段测试原话')]
        recorder.write(self.folder / 'session.json', self.meta)
        recorder.write(self.folder / '录像.whisper.json', {'segments': self.segments})
        (self.folder / '录像.mp4').write_bytes(b'synthetic placeholder, never claimed playable')
        (self.folder / '独立回看.html').write_text('old immutable review', encoding='utf-8')
        (self.folder / '复盘.md').write_text('user note sentinel', encoding='utf-8')

    def test_old_session_uses_new_renderer_without_rewriting_notes_or_transcript(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        # Application templates are real; only the temporary page directory is isolated.
        with patch('review_runtime.render_player', wraps=lambda root, payload: render_player(recorder.ROOT, payload)):
            page, payload = prepare_window(self.root, recorder.Session(self.folder))
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir() if p.name != '.processing.lock'})
        self.assertTrue(page.is_relative_to(self.root / 'state/reviews'))
        self.assertTrue(payload['video'].startswith('file:///'))
        self.assertIn('%20', payload['video'])
        html = page.read_text(encoding='utf-8')
        self.assertIn('new Plyr', html)
        self.assertIn('合成测试 &lt;script&gt; %%CSS%%', html)
        self.assertNotIn('</script><script>alert(1)</script>', html)
        self.assertIn('\\u003c/script>', html)

    def test_export_refreshes_player_and_contains_no_absolute_desktop_paths(self):
        archive = recorder.Session(self.folder).package()
        with zipfile.ZipFile(archive) as bundle:
            page = bundle.read('场次/synthetic/独立回看.html').decode('utf-8')
            self.assertIn('seekTime:15', page)
            self.assertNotIn(str(self.root), page)
            self.assertNotIn(self.folder.as_uri(), page)
            self.assertIn('Permission is hereby granted', page)
            self.assertFalse(any(name.startswith('.obsidian/') for name in bundle.namelist()))
        self.assertEqual((self.folder / '独立回看.html').read_text(encoding='utf-8'), 'old immutable review')

    def test_viewer_commands_remain_bound_to_original_session(self):
        api = ReviewAPI(self.folder, {})
        with patch('review_runtime.os.startfile') as start, patch('review_runtime.copy_text') as copy:
            self.assertTrue(api.open_folder()['ok'])
            start.assert_called_once_with(self.folder.resolve())
            self.assertTrue(api.copy_path('video')['ok'])
            copy.assert_called_once_with(str((self.folder / '录像.mp4').resolve()))
            self.assertFalse(api.copy_path('../outside')['ok'])
            self.assertFalse(api.open_document('../outside')['ok'])
            self.assertTrue(api.open_document('notes')['ok'])
        self.assertEqual({name for name in dir(api) if not name.startswith('_')},
                         {'ready', 'open_folder', 'copy_path', 'open_document', 'get_layout', 'save_layout', 'get_snapshot', 'rename_session', 'set_input_offset'})

    def test_input_offset_is_per_session_metadata_and_never_rewrites_captured_facts(self):
        recorder.write(self.folder/'input-events.json',dict(version=1,state='complete',duration=10,
            timebase='video_seconds',intervals=[dict(id='a',device='keyboard',code='A',start=3,end=3.1)],gaps=[]))
        source=(self.folder/'input-events.json').read_bytes()
        api=ReviewAPI(self.folder,{})
        previous=api.get_snapshot()['data']['revision']
        result=api.set_input_offset(-1.8)
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['offset_seconds'],-1.8)
        self.assertEqual(result['data']['source'],'manual')
        snapshot=api.get_snapshot(previous)['data']
        self.assertNotEqual(snapshot['revision'],previous)
        self.assertEqual(snapshot['inputs']['intervals'][0]['start'],3)
        self.assertEqual(snapshot['inputs']['alignment'],result['data'])
        recorder.Session(self.folder).update(state='转写中')
        self.assertEqual(api.get_snapshot()['data']['inputs']['alignment']['offset_seconds'],-1.8)
        self.assertEqual((self.folder/'input-events.json').read_bytes(),source)

    def test_manual_input_offset_overrides_measured_and_reset_restores_measured(self):
        recorder.Session(self.folder).update(input_alignment=dict(method='final_video_stop_boundary_v1',
            offset_seconds=1.4,uncertainty_seconds=.1))
        api=ReviewAPI(self.folder,{})
        self.assertEqual(api.get_snapshot()['data']['inputs']['alignment']['offset_seconds'],1.4)
        self.assertEqual(api.set_input_offset(0)['data']['source'],'manual')
        self.assertEqual(api.set_input_offset(None)['data']['offset_seconds'],1.4)
        self.assertEqual(api.get_snapshot()['data']['inputs']['alignment']['source'],'measured')

    def test_invalid_input_offset_does_not_touch_session_metadata(self):
        api=ReviewAPI(self.folder,{})
        before=(self.folder/'session.json').read_bytes()
        for invalid in (True,False,'1.8',[],{},float('nan'),float('inf'),31,-30.01):
            self.assertFalse(api.set_input_offset(invalid)['ok'],repr(invalid))
        self.assertEqual((self.folder/'session.json').read_bytes(),before)

    def test_unknown_or_low_confidence_alignment_is_not_presented_as_measured(self):
        for value in ({'offset_seconds':1.8,'uncertainty_seconds':.1},
                      {'method':'final_video_stop_boundary_v1','offset_seconds':1.8,'uncertainty_seconds':.251},
                      {'method':'final_video_stop_boundary_v1','offset_seconds':float('nan'),'uncertainty_seconds':.1}):
            recorder.Session(self.folder).update(input_alignment=value)
            alignment=ReviewAPI(self.folder,{}).get_snapshot()['data']['inputs']['alignment']
            self.assertEqual(alignment['source'],'uncalibrated')
            self.assertEqual(alignment['offset_seconds'],0)

    def test_export_keeps_the_same_alignment_as_desktop_review(self):
        api=ReviewAPI(self.folder,{})
        api.set_input_offset(-1.8)
        desktop=api.get_snapshot()['data']['inputs']['alignment']
        with zipfile.ZipFile(recorder.Session(self.folder).package()) as archive:
            exported=json.loads(archive.read('场次/synthetic/session.json'))
            page=archive.read('场次/synthetic/独立回看.html').decode('utf-8')
        self.assertEqual(exported['input_offset_seconds'],-1.8)
        self.assertIn(json.dumps(desktop,ensure_ascii=False),page)

    def test_video_review_opens_while_transcription_owns_processing_lock(self):
        import msvcrt
        (self.folder / '录像.whisper.json').unlink()
        recorder.Session(self.folder).update(state='转写中', transcription_state='pending')
        with (self.folder / '.processing.lock').open('a+b') as lock:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with patch('review_runtime.render_player', wraps=lambda root, payload: render_player(recorder.ROOT, payload)):
                    page, payload = prepare_window(self.root, recorder.Session(self.folder))
                self.assertTrue(page.is_file())
                self.assertEqual(payload['transcription']['state'], 'pending')
                self.assertEqual(payload['segments'], [])
            finally:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def test_snapshot_moves_pending_failed_ready_without_changing_video(self):
        (self.folder / '录像.whisper.json').unlink()
        session = recorder.Session(self.folder)
        session.update(state='转写中', transcription_state='pending')
        api = ReviewAPI(self.folder, {})
        pending = api.get_snapshot()['data']
        session.update(state='失败', transcription_state='failed', error='synthetic sk-secret123')
        failed = api.get_snapshot()['data']
        self.assertEqual(failed['transcription']['state'], 'failed')
        self.assertNotIn('sk-secret123', failed['transcription']['error'])
        recorder.write(self.folder / '录像.whisper.json', {'segments': self.segments})
        session.update(state='可回看', transcription_state='ready')
        ready = api.get_snapshot()['data']
        self.assertEqual(ready['transcription']['state'], 'ready')
        self.assertEqual(ready['segments'], self.segments)
        self.assertEqual(pending['video'], failed['video'])
        self.assertEqual(pending['video'], ready['video'])

    def test_rename_survives_stale_processing_metadata_and_never_moves_files(self):
        old_worker = recorder.Session(self.folder)
        api = ReviewAPI(self.folder, {})
        self.assertTrue(api.rename_session('新的场次名')['ok'])
        old_worker.update(state='转写中', step='transcribing')
        snapshot = api.get_snapshot()['data']
        self.assertEqual(snapshot['title'], '新的场次名')
        self.assertEqual(snapshot['game'], self.meta['game'])
        self.assertTrue((self.folder / '录像.mp4').is_file())
        self.assertFalse(api.rename_session('x' * 121)['ok'])
        self.assertFalse(api.rename_session('bad\nname')['ok'])
        self.assertTrue(api.rename_session('')['ok'])
        self.assertEqual(api.get_snapshot()['data']['title'], self.meta['game'])

    def test_vault_copy_uses_actual_library_and_input_payload_is_allowlisted(self):
        api = ReviewAPI(self.folder, {})
        with patch('review_runtime.copy_text') as copy:
            self.assertTrue(api.copy_path('vault')['ok'])
            copy.assert_called_once_with(str(self.folder.parent.parent.resolve()))
        recorder.write(self.folder / 'input-events.json', dict(version=1, state='complete', duration=5,
            timebase='video_seconds', intervals=[dict(id='i1', start=1, end=2, device='keyboard',
                code='KeyW', label='W', kind='button', raw_text='private text')], gaps=[], secret='private key'))
        payload = api.get_snapshot()['data']
        self.assertEqual(payload['vault_path'], str(self.folder.parent.parent.resolve()))
        self.assertEqual(payload['inputs']['intervals'][0]['label'], 'W')
        self.assertNotIn('private', json.dumps(payload))

    def test_gap_devices_are_retained_only_for_supported_device_families(self):
        recorder.write(self.folder / 'input-events.json', dict(version=1, state='complete', duration=5,
            timebase='video_seconds', intervals=[], gaps=[
                dict(start=1,end=2,type='disconnect',reason='synthetic',device='dualsense'),
                dict(start=3,end=4,type='capture',reason='synthetic',device='private-device-serial')]))
        gaps=ReviewAPI(self.folder,{}).get_snapshot()['data']['inputs']['gaps']
        self.assertEqual(gaps[0]['device'],'dualsense')
        self.assertNotIn('device',gaps[1])

    def test_missing_ready_transcript_is_failed_but_video_stays_available(self):
        (self.folder/'录像.whisper.json').unlink()
        for state in (None,'ready'):
            meta={**self.meta,'transcription_state':state}
            recorder.write(self.folder/'session.json',meta)
            value=ReviewAPI(self.folder,{}).get_snapshot()
            self.assertTrue(value['ok'])
            self.assertEqual(value['data']['transcription']['state'],'failed')
            self.assertIn('逐字稿文件缺失',value['data']['transcription']['error'])
            self.assertEqual(value['data']['segments'],[])
            self.assertEqual(value['data']['video'],(self.folder/'录像.mp4').resolve().as_uri())
            self.assertEqual(review_payload(self.folder,meta,[])['transcription']['state'],'failed')

    def test_unchanged_snapshot_uses_only_stat_and_never_reads_large_sidecars(self):
        api=ReviewAPI(self.folder,{})
        first=api.get_snapshot()['data']
        self.assertRegex(first['revision'],r'^[a-f0-9]{64}$')
        self.assertNotIn(str(self.folder),first['revision'])
        with patch('review_runtime.session_review_payload',side_effect=AssertionError('full read must be skipped')) as full, \
             patch.object(Path,'read_text',side_effect=AssertionError('sidecar must not be opened')):
            value=api.get_snapshot(first['revision'])
            self.assertEqual(value,{'ok':True,'data':{'unchanged':True,'revision':first['revision']}})
            full.assert_not_called()

    def test_snapshot_revision_detects_rename_transcript_publish_and_missing_file(self):
        api=ReviewAPI(self.folder,{})
        first=api.get_snapshot()['data']
        self.assertTrue(api.rename_session('Revision rename')['ok'])
        renamed=api.get_snapshot(first['revision'])['data']
        self.assertNotIn('unchanged',renamed)
        self.assertEqual(renamed['title'],'Revision rename')
        recorder.write(self.folder/'录像.whisper.json',{'segments':[{'start':1,'end':2,'text':'Newly published transcript'}]})
        transcript=api.get_snapshot(renamed['revision'])['data']
        self.assertNotIn('unchanged',transcript)
        self.assertEqual(transcript['segments'][0]['text'],'Newly published transcript')
        recorder.write(self.folder/'input-events.json',dict(version=1,state='complete',duration=3,timebase='video_seconds',
            intervals=[dict(id='i',device='keyboard',code='W',label='W',kind='button',start=1,end=2)],gaps=[]))
        inputs=api.get_snapshot(transcript['revision'])['data']
        self.assertEqual(inputs['inputs']['intervals'][0]['code'],'W')
        (self.folder/'录像.whisper.json').unlink()
        missing=api.get_snapshot(inputs['revision'])['data']
        self.assertEqual(missing['transcription']['state'],'failed')
        self.assertIn('缺失',missing['transcription']['error'])
        self.assertNotEqual(missing['revision'],inputs['revision'])
        # No argument remains backwards compatible and always returns full data.
        self.assertIn('segments',api.get_snapshot()['data'])

    def test_export_uses_one_metadata_snapshot_while_rename_remains_responsive(self):
        session=recorder.Session(self.folder)
        api=ReviewAPI(self.folder,{})
        self.assertTrue(api.rename_session('Export snapshot name')['ok'])
        entered,release=threading.Event(),threading.Event()
        results=[];errors=[]
        original_open=zipfile.ZipFile.open
        def zip_open(bundle,name,mode='r',*args,**kwargs):
            if mode=='w' and str(name).endswith('/录像.mp4'):
                entered.set();release.wait(3)
            return original_open(bundle,name,mode,*args,**kwargs)
        def package():
            try:results.append(session.package())
            except Exception as error:errors.append(error)
        with patch.object(zipfile.ZipFile,'open',side_effect=zip_open,autospec=True):
            worker=threading.Thread(target=package)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.assertTrue(api.rename_session('Newer current name')['ok'])
            finally:
                release.set();worker.join(4)
        self.assertFalse(errors,errors)
        self.assertFalse(worker.is_alive())
        with zipfile.ZipFile(results[0]) as bundle:
            prefix='场次/synthetic/'
            metadata_bytes=bundle.read(prefix+'session.json')
            self.assertEqual(json.loads(metadata_bytes)['session_name'],'Export snapshot name')
            page=bundle.read(prefix+'独立回看.html').decode('utf-8')
            self.assertIn('Export snapshot name',page)
            self.assertNotIn('Newer current name',page)
            hashes=json.loads(bundle.read('校验清单.json'))
            self.assertEqual(hashes[prefix+'session.json'],hashlib.sha256(metadata_bytes).hexdigest())
            for name,digest in hashes.items():self.assertEqual(digest,hashlib.sha256(bundle.read(name)).hexdigest())
        self.assertEqual(api.get_snapshot()['data']['session_name'],'Newer current name')

    def test_export_digest_hashes_bytes_written_even_if_source_changes_after_read(self):
        file=self.folder/'changing.bin'
        file.write_bytes(b'archived bytes')
        original_open=zipfile.ZipFile.open
        class Output:
            def __init__(self,stream):self.stream=stream
            def __enter__(self):return self
            def __exit__(self,*args):
                self.stream.close()
                file.write_bytes(b'new bytes after archive write')
            def write(self,data):return self.stream.write(data)
        def zip_open(bundle,name,mode='r',*args,**kwargs):
            stream=original_open(bundle,name,mode,*args,**kwargs)
            return Output(stream) if mode=='w' and str(name).endswith('/changing.bin') else stream
        with patch.object(zipfile.ZipFile,'open',side_effect=zip_open,autospec=True):
            archive=recorder.Session(self.folder).package()
        with zipfile.ZipFile(archive) as bundle:
            path='场次/synthetic/changing.bin'
            self.assertEqual(bundle.read(path),b'archived bytes')
            hashes=json.loads(bundle.read('校验清单.json'))
            self.assertEqual(hashes[path],hashlib.sha256(b'archived bytes').hexdigest())

    def test_export_uses_same_public_inputs_as_html_and_excludes_recovery_files(self):
        recorder.write(self.folder/'input-events.json',dict(version=1,state='complete',duration=5,timebase='video_seconds',
            intervals=[dict(id='safe',device='keyboard',code='W',label='W',kind='button',start=.5,end=1),
                       dict(id='revoked',device='keyboard',code='A',label='A',kind='button',start=3,end=4)],gaps=[],
            active=[dict(code='private checkpoint field')],journal='input-events.journal'))
        (self.folder/'input-events.journal').write_text('private raw journal sentinel',encoding='utf-8')
        recorder.write(self.folder/'input-events.revocation.json',dict(version=1,invalid_from=2))
        original={p:p.read_bytes() for p in self.folder.glob('input-events.*')}
        with patch('review_runtime.render_player',wraps=render_player) as render:
            archive=recorder.Session(self.folder).package()
        with zipfile.ZipFile(archive) as bundle:
            name='场次/synthetic/input-events.json'
            data=bundle.read(name)
            public=json.loads(data)
            self.assertEqual([row['code'] for row in public['intervals']],['W'])
            self.assertNotIn('active',public)
            self.assertNotIn('journal',public)
            self.assertEqual(public,render.call_args.args[1]['inputs'])
            self.assertEqual(json.loads(bundle.read('校验清单.json'))[name],hashlib.sha256(data).hexdigest())
            self.assertEqual([n for n in bundle.namelist() if '/input-events.' in n],[name])
        for path,data in original.items():self.assertEqual(path.read_bytes(),data)

    def test_revocation_alone_changes_revision_and_hides_stale_input_file(self):
        recorder.write(self.folder/'input-events.json',dict(version=1,state='complete',duration=5,timebase='video_seconds',
            intervals=[dict(id='one',device='keyboard',code='A',kind='button',start=1,end=4)],gaps=[]))
        api=ReviewAPI(self.folder,{})
        first=api.get_snapshot()['data']
        recorder.write(self.folder/'input-events.revocation.json',dict(version=1,invalid_from=2))
        second=api.get_snapshot(first['revision'])['data']
        self.assertNotEqual(first['revision'],second['revision'])
        self.assertEqual(second['inputs']['intervals'][0]['end'],2)
        self.assertEqual(second['inputs']['state'],'failed')
        (self.folder/'input-events.revocation.json').write_text('invalid synthetic marker',encoding='utf-8')
        third=api.get_snapshot(second['revision'])['data']
        self.assertEqual(third['inputs']['intervals'],[])
        self.assertEqual(third['inputs']['state'],'failed')

    def test_layout_preferences_merge_between_windows_without_changing_session(self):
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        preferences = self.root / 'state/review-layout.json'
        first = ReviewAPI(self.folder, {}, preferences)
        second = ReviewAPI(self.folder, {}, preferences)
        self.assertEqual(first.get_layout()['data'], {})
        self.assertTrue(first.save_layout('columns', .7)['ok'])
        self.assertTrue(second.save_layout('rows', .45)['ok'])
        reopened = ReviewAPI(self.folder, {}, preferences)
        self.assertEqual(reopened.get_layout()['data'], {'columns': .7, 'rows': .45})
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.folder.iterdir()})
        for axis, value in [('columns', float('nan')), ('rows', True), ('rows', .99), ('../config', .5)]:
            self.assertFalse(first.save_layout(axis, value)['ok'])
        self.assertEqual(reopened.get_layout()['data'], {'columns': .7, 'rows': .45})

    def test_corrupt_layout_preferences_do_not_block_review(self):
        preferences = self.root / 'layout.json'
        api = ReviewAPI(self.folder, {}, preferences)
        for content in ('invalid JSON', '[]', '{"columns":false,"rows":0.6,"other":0.2}'):
            preferences.write_text(content, encoding='utf-8')
            self.assertEqual(api.get_layout()['data'], {'rows': .6} if 'rows' in content else {})
        self.assertTrue(api.save_layout('columns', .5)['ok'])
        self.assertEqual(api.get_layout()['data'], {'columns': .5, 'rows': .6})

    def test_invalid_timestamps_fail_before_display(self):
        for start, end in [(float('nan'), 2), (-1, 2), (3, 2), (0, float('inf'))]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                review_payload(self.folder, self.meta, [{'start': start, 'end': end}])


if __name__ == '__main__':
    unittest.main()
