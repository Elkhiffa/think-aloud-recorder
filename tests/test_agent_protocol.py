"""Synthetic evidence exercises the actual local protocol, never an AI service."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
import zipfile

import agent_cli
import agent_protocol as agent
import recorder
from review_runtime import ReviewAPI, session_review_payload
from session_metadata import rename_session, update_metadata
from speaker_roles import transcript_id


class AgentProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/'资料库 空格'/'场次'/'fixture'
        self.folder.mkdir(parents=True)
        self.meta = dict(id='fixture', game='合成体验', state='可回看', test=True,
                         transcription_state='ready', media=dict(duration=12),
                         settings=dict(record_inputs=True, password='private-sentinel'),
                         input_offset_seconds=1)
        self.segments = [dict(start=2, end=4, text=' 我不知道这个按钮的状态。 ', speaker_id=0),
                         dict(start=8, end=10, text='现在找到入口了。', speaker_id=1)]
        recorder.write(self.folder/'session.json', self.meta)
        recorder.write(self.folder/'录像.whisper.json', dict(segments=self.segments))
        recorder.write(self.folder/'input-events.json', dict(version=1, state='complete', duration=12,
             timebase='video_seconds', recording_scope='all', window_states=[dict(start=0,end=12,state='background')],
             intervals=[dict(id='raw1', start=2, end=2.2, device='keyboard', code='KeyX', label='X')], gaps=[]))
        (self.folder/'录像.mp4').write_bytes(b'Synthetic placeholder: protocol tests do not claim playback')
        (self.folder/'复盘.md').write_text('用户笔记，不可修改', encoding='utf-8')
        self.manifest = agent.publish_ready(self.folder)

    def candidate(self):
        return dict(version=1,session_id='fixture',revision=self.manifest['revision'],summary='合成预处理示例。',
                    coverage=dict(video_ranges=[dict(start=2,end=4)],transcript='full',inputs='full',limitations=['仅用于合成验证。']),
                    events=[dict(id='e1',start=2,end=4,title='按钮状态难以判断',summary='记录者明确表达了疑惑。',
                                 context='目标尚需核对。',basis='explicit',kind='friction',
                                 evidence=[dict(kind='quote',ref='t000001'),dict(kind='input',ref='i0000001'),
                                           dict(kind='video',start=3,end=3,observation='合成按钮仍在原处。')])],
                    questions=[dict(id='q1',event_id='e1',question='后来如何确认状态？',reason='当前片段未说明。')],
                    ideas=[dict(id='h1',event_id='e1',idea='比较不同状态的提示是否容易区分。',reason='原话表达了疑惑。')])

    def complete(self):
        job=agent.claim(self.folder,'synthetic-worker')
        agent.submit(self.folder,job['token'],self.candidate())
        return job

    def test_no_agent_has_no_extra_status_and_manifest_contains_no_configuration(self):
        self.assertEqual(agent.preprocessing_status(self.folder),dict(state='none'))
        self.assertNotIn('private-sentinel',json.dumps(self.manifest))
        self.assertNotIn(str(self.folder),json.dumps(self.manifest))
        path=self.folder/agent.READY
        timestamp=path.stat().st_mtime_ns
        self.assertEqual(agent.publish_ready(self.folder),self.manifest)
        self.assertEqual(path.stat().st_mtime_ns,timestamp)

    def test_pending_or_malformed_transcript_cannot_publish(self):
        update_metadata(self.folder,dict(state='转写中',transcription_state='pending'))
        with self.assertRaises(ValueError):agent.publish_ready(self.folder)
        self.assertFalse(agent.try_publish_ready(self.folder))
        self.assertEqual(recorder.read(self.folder/'session.json')['state'],'转写中')
        update_metadata(self.folder,dict(state='可回看',transcription_state='ready'))
        recorder.write(self.folder/'录像.whisper.json',dict(segments=[dict(start=0,end=99,text='invalid')]))
        with self.assertRaises(ValueError):agent.publish_ready(self.folder)

    def test_evidence_aligns_inputs_preserves_speaker_identity_and_original_text(self):
        value=agent.evidence(self.folder,2,4)
        self.assertEqual(value['inputs']['intervals'][0]['start'],3)
        self.assertEqual(value['inputs']['intervals'][0]['source_start'],2)
        self.assertEqual(value['coverage']['window_states'][0]['state'],'background')
        self.assertEqual(value['transcript'][0]['text'],self.segments[0]['text'])
        self.assertEqual(value['speakers']['transcript_id'],transcript_id(self.segments))
        self.assertNotIn('private-sentinel',json.dumps(value))
        self.assertNotIn('intervals',agent.evidence(self.folder)['inputs'])
        for pair in ((None,1),(0,None),(-1,2),(0,13),(0,float('nan'))):
            with self.assertRaises(ValueError):agent.evidence(self.folder,*pair)

    def test_simultaneous_claims_have_only_one_owner(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs=list(pool.map(lambda i:agent.claim(self.folder,f'worker-{i}'),range(8)))
        self.assertEqual(sum(job['claimed'] for job in jobs),1)
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'processing')

    def test_claim_fencing_renewal_and_expired_worker(self):
        first=agent.claim(self.folder,'one',60)
        with self.assertRaises(ValueError):agent.renew(self.folder,'wrong',60)
        agent.renew(self.folder,first['token'],120)
        self.assertGreater(agent._load(self.folder,agent.STATE)['expires_at'],first['expires_at'])
        with patch('agent_protocol.time.time',return_value=time.time()+200):
            self.assertEqual(agent.preprocessing_status(self.folder)['state'],'interrupted')
            second=agent.claim(self.folder,'two')
        self.assertTrue(second['claimed'])
        with self.assertRaises(ValueError):agent.submit(self.folder,first['token'],self.candidate())
        agent.submit(self.folder,second['token'],self.candidate())

    def test_atomic_completion_is_idempotent_and_preserves_recording_name_notes(self):
        before={name:(self.folder/name).read_bytes() for name in ('session.json','复盘.md','录像.whisper.json','input-events.json','录像.mp4')}
        job=self.complete()
        state=agent.preprocessing_status(self.folder,include_result=True)
        self.assertEqual((state['state'],state['events'],state['questions']),('complete',1,1))
        self.assertEqual(state['result']['events'][0]['evidence'][0]['text'],self.segments[0]['text'])
        self.assertFalse(agent.claim(self.folder,'again')['claimed'])
        with self.assertRaises(ValueError):agent.submit(self.folder,job['token'],self.candidate())
        for name,content in before.items():self.assertEqual((self.folder/name).read_bytes(),content)
        self.assertNotIn('token',json.dumps(state))

    def test_rename_does_not_change_revision_but_new_material_does(self):
        self.complete()
        rename_session(self.folder,'用户起的名字')
        self.assertEqual(agent.publish_ready(self.folder)['revision'],self.manifest['revision'])
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'complete')
        update_metadata(self.folder,dict(input_offset_seconds=2))
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'stale')
        self.manifest=agent.publish_ready(self.folder)
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'stale')
        job=agent.claim(self.folder,'new')
        candidate=self.candidate();candidate['events'][0]['end']=5
        agent.submit(self.folder,job['token'],candidate)
        self.assertEqual(len(list((self.folder/'agent-history').glob('*.json'))),1)
        self.assertEqual(recorder.read(self.folder/'session.json')['session_name'],'用户起的名字')

    def test_speaker_and_retranscription_invalidate_without_losing_old_result(self):
        self.complete()
        api=ReviewAPI(self.folder,session_review_payload(self.folder))
        self.assertTrue(api.set_recorder_speaker(1,transcript_id(self.segments))['ok'])
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'stale')
        self.assertTrue((self.folder/agent.RESULT).exists())
        updated=recorder.read(self.folder/'录像.whisper.json');updated['segments'][0]['text']='改正后的文字'
        recorder.write(self.folder/'录像.whisper.json',updated)
        with self.assertRaises(ValueError):agent.claim(self.folder,'new')
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'stale')

    def test_invalid_evidence_and_inferences_are_rejected_without_commit(self):
        tests=[]
        for change in (
            lambda x:x.update(revision='other'),
            lambda x:x['events'][0].update(end=1),
            lambda x:x['events'][0]['evidence'][0].update(ref='missing'),
            lambda x:x['events'][0]['evidence'][1].update(ref='missing'),
            lambda x:x['coverage'].update(video_ranges=[]),
            lambda x:x['events'][0].update(evidence=[]),
            lambda x:x['events'][0].update(start=True),
            lambda x:x['questions'][0].update(event_id='absent'),
        ):
            value=self.candidate();change(value);tests.append(value)
        for value in tests:
            with self.assertRaises(ValueError):agent.validate_result(self.folder,value)
        self.assertFalse((self.folder/agent.RESULT).exists())

    def test_revoked_inputs_are_not_valid_evidence(self):
        # Use the capture writer's actual marker schema.
        from input_capture import _record_revocation
        _record_revocation(self.folder/'input-events.revocation.json',1)
        self.manifest=agent.publish_ready(self.folder)
        with self.assertRaises(ValueError):agent.validate_result(self.folder,self.candidate())

    def test_failed_preprocessing_does_not_fail_or_hide_video_and_can_retry(self):
        job=agent.claim(self.folder,'worker')
        agent.fail(self.folder,job['token'],'未检查完整；sk-secretvalue')
        state=agent.preprocessing_status(self.folder)
        self.assertEqual(state['state'],'failed')
        self.assertNotIn('sk-secretvalue',state['reason'])
        self.assertEqual(recorder.read(self.folder/'session.json')['state'],'可回看')
        self.assertIn('录像.mp4',session_review_payload(self.folder)['video'])
        self.assertTrue(agent.claim(self.folder,'retry')['claimed'])

    def test_invalid_optional_json_never_breaks_playback_and_can_be_repaired(self):
        (self.folder/agent.RESULT).write_text('{invalid',encoding='utf-8')
        payload=session_review_payload(self.folder)
        self.assertEqual(payload['preprocessing']['state'],'invalid')
        self.assertEqual(payload['transcription']['state'],'ready')
        self.complete()
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'complete')

    def test_result_arrival_refreshes_review_snapshot_and_expiry_uses_clock(self):
        api=ReviewAPI(self.folder,session_review_payload(self.folder))
        first=api.get_snapshot()['data']
        job=agent.claim(self.folder,'worker',60)
        next=api.get_snapshot(first['revision'])['data']
        self.assertEqual(next['preprocessing']['state'],'processing')
        with patch('agent_protocol.time.time',return_value=time.time()+61):
            expired=api.get_snapshot(next['revision'])['data']
            self.assertEqual(expired['preprocessing']['state'],'interrupted')
        agent.submit(self.folder,job['token'],self.candidate())
        last=api.get_snapshot(expired['revision'])['data']
        self.assertEqual(last['preprocessing']['state'],'complete')

    def test_unchanged_status_does_not_reread_large_artifacts(self):
        self.complete()
        agent.preprocessing_status(self.folder,self.meta)
        with patch.object(Path,'read_text',side_effect=AssertionError('no reads on cached status')):
            self.assertEqual(agent.preprocessing_status(self.folder,self.meta)['state'],'complete')

    def test_export_contains_optional_result_but_no_worker_leases(self):
        self.complete()
        with zipfile.ZipFile(recorder.Session(self.folder).package()) as archive:
            names=archive.namelist()
            self.assertFalse(any('agent-' in name for name in names))
            result=json.loads(archive.read('场次/fixture/体验事件.json'))
            self.assertEqual(len(result['events']),1)
            page=archive.read('场次/fixture/独立回看.html').decode('utf-8')
            self.assertIn('按钮状态难以判断',page)

    def test_scan_is_explicit_old_session_enrollment_and_skips_test_fixtures(self):
        (self.folder/agent.READY).unlink()
        self.assertEqual(agent_cli.scan(self.folder.parent.parent)['sessions'],[])
        self.assertEqual(agent_cli.scan(self.folder.parent.parent,include_test=True)['sessions'],[])
        value=agent_cli.scan(self.folder.parent.parent,publish=True,include_test=True)
        self.assertEqual(len(value['sessions']),1)

    def test_cli_works_with_spaces_unicode_and_json_only_output(self):
        run=subprocess.run([sys.executable,str(Path(agent_cli.__file__)),'evidence',str(self.folder),'--start','2','--end','4'],
                           capture_output=True,encoding='utf-8',creationflags=recorder.HIDDEN)
        self.assertEqual(run.returncode,0,run.stderr+run.stdout)
        self.assertEqual(json.loads(run.stdout)['data']['session_id'],'fixture')


if __name__=='__main__':unittest.main()
