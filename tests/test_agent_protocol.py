"""Synthetic evidence exercises the actual local protocol, never an AI service."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
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

    def test_input_correction_revises_evidence_preserves_analysis_and_exports_notice(self):
        self.complete()
        original = (self.folder / 'experience-events.json').read_bytes()
        api = ReviewAPI(self.folder, {})
        before = api.get_snapshot()['data']['revision']
        raw = (self.folder / 'input-events.json').read_bytes()
        row = json.loads(raw)['intervals'][0]
        recorder.write(self.folder / 'input-events.corrections.json', dict(version=1,
            source_sha256=hashlib.sha256(raw).hexdigest(), excluded=[dict(row, reason='Confirmed false hold')]))
        self.assertNotEqual(api.get_snapshot()['data']['revision'], before)
        self.assertEqual(agent.preprocessing_status(self.folder)['state'], 'stale')
        manifest = agent.publish_ready(self.folder)
        self.assertNotEqual(manifest['revision'], self.manifest['revision'])
        evidence = agent.evidence(self.folder, 0, 12)
        self.assertEqual(evidence['inputs']['intervals'], [])
        self.assertEqual(evidence['inputs']['input_corrections']['excluded_count'], 1)
        self.assertEqual((self.folder / 'experience-events.json').read_bytes(), original)
        self.assertEqual((self.folder / 'input-events.json').read_bytes(), raw)
        archive = recorder.Session(self.folder).package()
        with zipfile.ZipFile(archive) as package:
            name = next(n for n in package.namelist() if n.endswith('/input-events.json'))
            projected = json.loads(package.read(name))
            self.assertEqual(projected['intervals'], [])
            self.assertEqual(projected['input_corrections']['excluded_count'], 1)
            self.assertFalse(any(n.endswith('/input-events.corrections.json') for n in package.namelist()))

    def complete(self):
        job=agent.claim(self.folder,'synthetic-worker')
        agent.submit(self.folder,job['token'],self.candidate())
        return job

    def edit_request(self):
        from event_edits import editable
        state=agent.preprocessing_status(self.folder,include_result=True)
        return dict(**state['editing'],event_id='e1',fields=editable(state['result']['events'][0]))

    def test_manual_event_edit_preserves_sources_and_exports_projection(self):
        self.complete()
        source={name:(self.folder/name).read_bytes() for name in ('experience-events.json','agent-ready.json','录像.whisper.json','复盘.md')}
        request=self.edit_request()
        request['fields'].update(start=1.5,end=5,title='状态辨认困难',summary='尝试确认按钮状态。',issue='选中与完成状态难以区分。',notes='尚不能判断实现原因。')
        api=ReviewAPI(self.folder,{})
        before=api.get_snapshot()['data']['revision']
        response=api.edit_event(request)
        self.assertTrue(response['ok'],response)
        row=response['data']['result']['events'][0]
        for key,value in request['fields'].items(): self.assertEqual(row[key],value)
        self.assertTrue(row['manually_edited'])
        self.assertNotEqual(api.get_snapshot()['data']['revision'],before)
        for name,content in source.items(): self.assertEqual((self.folder/name).read_bytes(),content)
        from event_edits import context,FILE
        ctx=context(self.folder)
        self.assertEqual(len(ctx['history']),1)
        self.assertIn('-  "title": "按钮状态难以判断"',ctx['history'][0]['diff'])
        self.assertEqual(agent.evidence(self.folder)['manual_corrections'],ctx)
        self.assertEqual(session_review_payload(self.folder)['preprocessing']['result']['events'][0]['issue'],request['fields']['issue'])
        # A no-op save does not add a history entry or change the digest.
        api.edit_event(self.edit_request())
        self.assertEqual(context(self.folder),ctx)

    def test_manual_event_conflicts_validation_and_failures_preserve_previous_edits(self):
        import event_edits
        self.complete();request=self.edit_request()
        for field,value in [('start',-1),('end',99),('start',float('nan')),('title',''),('summary',''),('notes','x'*2001)]:
            bad=deepcopy(request);bad['fields'][field]=value
            with self.assertRaises(ValueError):event_edits.save(self.folder,bad)
        request['fields']['notes']='第一次修正'
        event_edits.save(self.folder,request)
        with self.assertRaisesRegex(ValueError,'已更新'):event_edits.save(self.folder,request)
        current=self.edit_request();current['fields']['notes']='第二次修正'
        with patch('agent_protocol.os.replace',side_effect=OSError('synthetic write failure')):
            with self.assertRaises(OSError):event_edits.save(self.folder,current)
        self.assertEqual(self.edit_request()['fields']['notes'],'第一次修正')
        (self.folder/event_edits.FILE).write_text('{}',encoding='utf-8')
        state=agent.preprocessing_status(self.folder,include_result=True)
        self.assertEqual(state['state'],'complete')
        self.assertIn('error',state['editing'])
        with self.assertRaises(ValueError):agent.evidence(self.folder)

    def test_reanalysis_must_reconcile_latest_manual_diff_and_retains_history(self):
        import event_edits
        self.complete();request=self.edit_request();request['fields']['issue']='红点意义不清楚'
        event_edits.save(self.folder,request)
        job=agent.reprocess(self.folder,'another-worker','核对手动校准')
        candidate=self.candidate()
        with self.assertRaisesRegex(ValueError,'手动校准'):agent.submit(self.folder,job['token'],candidate)
        ctx=event_edits.context(self.folder)
        candidate['corrections_review']=dict(revision=ctx['revision'],summary='保留红点理解困惑，区分未核实机制。')
        candidate['events'][0]['issue']='红点意义不清楚'
        request=self.edit_request();request['fields']['notes']='又补充了判断边界'
        event_edits.save(self.folder,request)
        with self.assertRaisesRegex(ValueError,'手动校准'):agent.submit(self.folder,job['token'],candidate)
        candidate['corrections_review']['revision']=event_edits.context(self.folder)['revision']
        candidate['events'][0]['notes']='又补充了判断边界'
        agent.submit(self.folder,job['token'],candidate)
        raw=agent._load(self.folder,agent.RESULT)
        self.assertEqual(raw['corrections_review'],candidate['corrections_review'])
        # The old overlay never attaches to a reused ID in a different result.
        row=agent.preprocessing_status(self.folder,include_result=True)['result']['events'][0]
        self.assertNotIn('manually_edited',row)
        self.assertEqual(row['issue'],'红点意义不清楚')
        self.assertEqual(len(event_edits.context(self.folder)['history']),2)
        self.assertTrue(list((self.folder/'agent-history').glob('*.json')))

    def test_legacy_inline_notes_are_split_and_simultaneous_edits_are_fenced(self):
        import event_edits
        job=agent.claim(self.folder,'synthetic-worker')
        candidate=self.candidate();candidate['events'][0]['summary']='概述。\n\n备注：旧版限制。'
        agent.submit(self.folder,job['token'],candidate)
        request=self.edit_request()
        self.assertEqual(request['fields']['notes'],'旧版限制。')
        self.assertEqual(request['fields']['summary'],'概述。')
        def apply(number):
            edit=deepcopy(request);edit['fields']['title']=f'人工校准{number}'
            return ReviewAPI(self.folder,{}).edit_event(edit)
        with ThreadPoolExecutor(max_workers=4) as pool: replies=list(pool.map(apply,range(4)))
        self.assertEqual(sum(item['ok'] for item in replies),1)
        self.assertEqual(len(event_edits.context(self.folder)['history']),1)

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

    def test_completed_result_requires_explicit_reprocess(self):
        self.complete()
        before={name:(self.folder/name).read_bytes() for name in (agent.STATE,agent.RESULT)}
        self.assertEqual(agent.claim(self.folder,'another-worker')['reason'],'complete')
        self.assertFalse((self.folder/'agent-history').exists())
        for name,content in before.items():self.assertEqual((self.folder/name).read_bytes(),content)

    def test_reprocess_backs_up_exact_bytes_before_leasing_and_keeps_old_result_readable(self):
        self.complete()
        old=recorder.read(self.folder/agent.RESULT)
        # A noncanonical serialized result must survive byte for byte, including BOM/newlines.
        baseline=b'\xef\xbb\xbf'+json.dumps(old,ensure_ascii=False,indent=1).replace('\n','\r\n').encode('utf-8')
        (self.folder/agent.RESULT).write_bytes(baseline)
        write=agent._write
        def checked_write(folder,name,value):
            if name==agent.STATE:
                backup=Path(value['baseline']['path'])
                self.assertEqual(backup.read_bytes(),baseline)
                self.assertEqual(value['baseline']['sha256'],hashlib.sha256(baseline).hexdigest())
                self.assertEqual((self.folder/agent.RESULT).read_bytes(),baseline)
            return write(folder,name,value)
        with patch('agent_protocol._write',side_effect=checked_write):
            job=agent.reprocess(self.folder,'visual-worker','  采用新画面候选逻辑  ',120)
        self.assertTrue(job['claimed'])
        self.assertTrue(job['redo'])
        self.assertEqual(job['redo_reason'],'采用新画面候选逻辑')
        self.assertEqual(job['baseline']['bytes'],len(baseline))
        self.assertEqual(agent._load(self.folder,agent.STATE)['baseline'],job['baseline'])
        state=agent.preprocessing_status(self.folder,include_result=True)
        self.assertEqual((state['state'],state['reanalysis']['state']),('complete','processing'))
        self.assertEqual(state['result']['summary'],old['summary'])
        self.assertIn('旧结果仍可回看',state['label'])
        self.assertNotIn('token',json.dumps(state))
        self.assertEqual(agent.claim(self.folder,'ordinary-worker')['reason'],'busy')

    def test_reprocess_validates_reason_worker_lease_ready_and_existing_result(self):
        with self.assertRaisesRegex(ValueError,'claim'):
            agent.reprocess(self.folder,'worker','第一次不能重做')
        self.complete()
        before={name:(self.folder/name).read_bytes() for name in (agent.STATE,agent.RESULT)}
        for reason in (None,'','  ','x'*2001,'bad\x00reason',4):
            with self.subTest(reason_type=type(reason).__name__):
                with self.assertRaises(ValueError):agent.reprocess(self.folder,'worker',reason)
        for worker in (None,'','w'*161):
            with self.assertRaises(ValueError):agent.reprocess(self.folder,worker,'重新检查')
        for seconds in (True,59,86401,60.0):
            with self.assertRaises(ValueError):agent.reprocess(self.folder,'worker','重新检查',seconds)
        update_metadata(self.folder,dict(input_offset_seconds=2))
        with self.assertRaises(ValueError):agent.reprocess(self.folder,'worker','素材未重新发布')
        self.assertFalse((self.folder/'agent-history').exists())
        for name,content in before.items():self.assertEqual((self.folder/name).read_bytes(),content)

    def test_reprocess_backup_errors_never_change_result_or_lease(self):
        self.complete()
        before={name:(self.folder/name).read_bytes() for name in (agent.STATE,agent.RESULT)}
        original_open=Path.open
        def fail_backup(path,mode='r',*args,**kwargs):
            if path.parent.name=='agent-history' and mode=='xb':
                raise OSError('synthetic backup failure')
            return original_open(path,mode,*args,**kwargs)
        with patch.object(Path,'open',fail_backup),patch('agent_protocol._write') as write:
            with self.assertRaises(OSError):agent.reprocess(self.folder,'worker','备份失败测试')
            write.assert_not_called()
        with patch('agent_protocol._file_hash',return_value='wrong-readback-hash'),patch('agent_protocol._write') as write:
            with self.assertRaisesRegex(ValueError,'备份校验失败'):
                agent.reprocess(self.folder,'worker','备份读回失败测试')
            write.assert_not_called()
        for name,content in before.items():self.assertEqual((self.folder/name).read_bytes(),content)
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'complete')

    def test_reprocess_history_filename_collision_never_overwrites_history(self):
        self.complete()
        history=self.folder/'agent-history';history.mkdir()
        existing=history/'collision.json';existing.write_bytes(b'previous preserved history')
        before={name:(self.folder/name).read_bytes() for name in (agent.STATE,agent.RESULT)}
        with patch('agent_protocol.uuid.uuid4') as ident:
            ident.return_value.hex='collision'
            with self.assertRaises(FileExistsError):agent.reprocess(self.folder,'worker','文件名碰撞测试')
        self.assertEqual(existing.read_bytes(),b'previous preserved history')
        for name,content in before.items():self.assertEqual((self.folder/name).read_bytes(),content)

    def test_simultaneous_reprocess_calls_have_only_one_lease_and_backup(self):
        self.complete()
        with ThreadPoolExecutor(max_workers=8) as pool:
            jobs=list(pool.map(lambda i:agent.reprocess(self.folder,f'worker-{i}','并发重做测试'),range(8)))
        self.assertEqual(sum(job['claimed'] for job in jobs),1)
        self.assertEqual([job['reason'] for job in jobs if not job['claimed']],['busy']*7)
        self.assertEqual(len(list((self.folder/'agent-history').glob('*.json'))),1)
        self.assertEqual(agent.preprocessing_status(self.folder)['reanalysis']['state'],'processing')

    def test_reprocess_rejects_unfinished_lease_even_for_older_revision(self):
        self.complete()
        update_metadata(self.folder,dict(input_offset_seconds=2))
        agent.publish_ready(self.folder)
        agent.claim(self.folder,'pending-new-material')
        state=(self.folder/agent.STATE).read_bytes()
        update_metadata(self.folder,dict(input_offset_seconds=3))
        agent.publish_ready(self.folder)
        self.assertEqual(agent.reprocess(self.folder,'redo-worker','不能抢占旧租约')['reason'],'busy')
        self.assertEqual((self.folder/agent.STATE).read_bytes(),state)
        self.assertFalse((self.folder/'agent-history').exists())

    def test_failed_or_expired_reprocess_keeps_baseline_and_requires_explicit_retry(self):
        self.complete()
        baseline=(self.folder/agent.RESULT).read_bytes()
        first=agent.reprocess(self.folder,'first-redo','画面检查',60)
        agent.fail(self.folder,first['token'],'未检查完整；sk-secretvalue')
        state=agent.preprocessing_status(self.folder,include_result=True)
        self.assertEqual((state['state'],state['reanalysis']['state']),('complete','failed'))
        self.assertEqual(state['reanalysis']['reason'],'画面检查')
        self.assertNotIn('sk-secretvalue',state['reanalysis']['failure_reason'])
        self.assertEqual(agent.claim(self.folder,'ordinary-worker')['reason'],'complete')
        second=agent.reprocess(self.folder,'second-redo','继续核对',60)
        self.assertEqual(agent.preprocessing_status(self.folder)['reanalysis']['state'],'processing')
        with patch('agent_protocol.time.time',return_value=second['expires_at']+1):
            state=agent.preprocessing_status(self.folder,include_result=True)
            self.assertEqual((state['state'],state['reanalysis']['state']),('complete','interrupted'))
            self.assertEqual(state['result']['summary'],self.candidate()['summary'])
            self.assertEqual(agent.claim(self.folder,'ordinary-worker')['reason'],'complete')
            with self.assertRaises(ValueError):agent.submit(self.folder,second['token'],self.candidate())
            third=agent.reprocess(self.folder,'third-redo','显式重试')
        self.assertTrue(third['claimed'])
        self.assertEqual((self.folder/agent.RESULT).read_bytes(),baseline)
        self.assertIn('录像.mp4',session_review_payload(self.folder)['video'])
        self.assertNotIn('token',json.dumps(state))

    def test_reprocess_fences_old_workers_and_preserves_each_successful_version(self):
        original=self.complete()
        baseline=(self.folder/agent.RESULT).read_bytes()
        redo=agent.reprocess(self.folder,'visual-worker','第二轮画面检查')
        for operation in (
            lambda:agent.submit(self.folder,original['token'],self.candidate()),
            lambda:agent.renew(self.folder,original['token']),
            lambda:agent.fail(self.folder,original['token'],'不能覆盖新租约'),
        ):
            with self.assertRaises(ValueError):operation()
        invalid=self.candidate();invalid['events'][0]['end']=1
        with self.assertRaises(ValueError):agent.submit(self.folder,redo['token'],invalid)
        self.assertEqual((self.folder/agent.RESULT).read_bytes(),baseline)
        updated=self.candidate();updated['summary']='新画面检查后的整理';updated['events'][0]['title']='新发现的按钮状态问题'
        agent.submit(self.folder,redo['token'],updated)
        state=agent.preprocessing_status(self.folder,include_result=True)
        self.assertEqual(state['state'],'complete')
        self.assertEqual(state['result']['summary'],updated['summary'])
        self.assertNotIn('reanalysis',state)
        self.assertEqual(Path(redo['baseline']['path']).read_bytes(),baseline)
        self.assertEqual(len(list((self.folder/'agent-history').glob('*.json'))),1)
        second_version=(self.folder/agent.RESULT).read_bytes()
        next_job=agent.reprocess(self.folder,'third-worker','第三轮检查')
        self.assertEqual(Path(next_job['baseline']['path']).read_bytes(),second_version)
        updated['summary']='第三轮整理'
        agent.submit(self.folder,next_job['token'],updated)
        preserved=[path.read_bytes() for path in (self.folder/'agent-history').glob('*.json')]
        self.assertCountEqual(preserved,[baseline,second_version])
        self.assertEqual(agent.preprocessing_status(self.folder,include_result=True)['result']['summary'],'第三轮整理')

    def test_reprocess_submission_preserves_baseline_again_if_backup_was_damaged(self):
        self.complete()
        baseline=(self.folder/agent.RESULT).read_bytes()
        job=agent.reprocess(self.folder,'worker','合成损坏恢复测试')
        Path(job['baseline']['path']).write_bytes(b'synthetic damaged backup')
        updated=self.candidate();updated['summary']='重新整理'
        agent.submit(self.folder,job['token'],updated)
        preserved=[path.read_bytes() for path in (self.folder/'agent-history').glob('*.json')]
        self.assertIn(baseline,preserved)
        self.assertIn(b'synthetic damaged backup',preserved)
        self.assertEqual(agent.preprocessing_status(self.folder,include_result=True)['result']['summary'],'重新整理')

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

    def activity_candidate(self):
        context = agent.name_activities(self.folder)
        return dict(version=1, session_id=context['session_id'], revision=context['revision'],
                    result_sha256=context['result_sha256'], expected_name=context['expected_name'],
                    worker='synthetic-classifier', title='进城探索与角色培养',
                    activities=[dict(name=name, event_ids=['e1']) for name in ('任务', '探索', '养成', '战斗')])

    def test_activity_naming_preview_apply_replay_and_source_preservation(self):
        self.complete()
        protected = {p.name:p.read_bytes() for p in self.folder.iterdir() if p.is_file() and p.name!='.metadata.lock'}
        candidate=self.activity_candidate()
        self.assertNotIn('private-sentinel',json.dumps(agent.name_activities(self.folder)))
        preview=agent.name_activities(self.folder,candidate)
        self.assertEqual(preview['session_name'],'进城探索与角色培养')
        self.assertEqual(preview['activity_details'],'任务 + 探索 + 养成 + 战斗')
        for name,raw in protected.items():self.assertEqual((self.folder/name).read_bytes(),raw)
        applied=agent.name_activities(self.folder,candidate,apply=True)
        meta=recorder.read(self.folder/'session.json')
        self.assertEqual(meta['session_name_source'],'agent')
        self.assertEqual(meta['activity_naming']['activities'],candidate['activities'])
        self.assertEqual(meta['settings'],self.meta['settings'])
        self.assertEqual(agent.publish_ready(self.folder)['revision'],self.manifest['revision'])
        for name,raw in protected.items():
            if name!='session.json':self.assertEqual((self.folder/name).read_bytes(),raw)
        committed=(self.folder/'session.json').read_bytes()
        self.assertTrue(agent.name_activities(self.folder,candidate,apply=True)['replayed'])
        self.assertEqual((self.folder/'session.json').read_bytes(),committed)
        payload=session_review_payload(self.folder)
        self.assertEqual(payload['session_name'],applied['session_name'])
        self.assertEqual(payload['activity_details'],preview['activity_details'])

    def test_activity_naming_preserves_manual_title_and_updates_only_details(self):
        self.complete();rename_session(self.folder,'第一次进城【自己的备注】')
        candidate=self.activity_candidate()
        value=agent.name_activities(self.folder,candidate,apply=True)
        self.assertEqual(value['session_name'],'第一次进城【自己的备注】')
        self.assertTrue(value['manual_name_preserved'])
        self.assertFalse(value['manual_summary_appended'])
        candidate=self.activity_candidate();candidate['title']='尝试新路线'
        candidate['activities']=[dict(name='止戈',event_ids=['e1'])]
        value=agent.name_activities(self.folder,candidate,apply=True)
        self.assertEqual(value['session_name'],'第一次进城【自己的备注】')
        self.assertEqual(value['activity_details'],'止戈')

    def test_activity_naming_updates_agent_names_but_not_manual_edits(self):
        self.complete();agent.name_activities(self.folder,self.activity_candidate(),apply=True)
        candidate=self.activity_candidate();candidate['title']='探索城外的谜题'
        value=agent.name_activities(self.folder,candidate,apply=True)
        self.assertEqual(value['session_name'],'探索城外的谜题')
        rename_session(self.folder,value['session_name'])
        candidate=self.activity_candidate()
        self.assertEqual(agent.name_activities(self.folder,candidate,apply=True)['session_name'],'探索城外的谜题')
        rename_session(self.folder,'')
        self.assertEqual(session_review_payload(self.folder)['title'],self.meta['game'])
        self.assertTrue(agent.name_activities(self.folder)['can_auto_name'])

    def test_legacy_combined_names_split_on_read_without_rewriting_sources(self):
        from session_metadata import session_presentation
        self.complete()
        old='第一次进城 【任务+探索】'
        update_metadata(self.folder,dict(session_name=old,session_name_source='manual_with_summary',activity_naming=dict(
            naming_policy='append-content-v2',manual_name='第一次进城',suggested_name='【任务+探索】',applied_name=old,
            activities=[dict(name='任务'),dict(name='探索')])))
        before=(self.folder/'session.json').read_bytes()
        view=session_review_payload(self.folder)
        self.assertEqual(view['title'],'第一次进城');self.assertEqual(view['activity_details'],'任务 + 探索')
        self.assertEqual((self.folder/'session.json').read_bytes(),before)
        candidate=self.activity_candidate()
        self.assertEqual(candidate['expected_name'],old)
        self.assertEqual(agent.name_activities(self.folder,candidate,apply=True)['session_name'],'第一次进城')
        # Brackets alone never imply an agent-owned name.
        self.assertEqual(session_presentation({'session_name':'【自己的完整标题】'})['title'],'【自己的完整标题】')
        self.assertEqual(session_presentation({'game':'项目','activity_naming':{'activities':None}})['title'],'项目')

    def test_legacy_auto_name_moves_to_details_and_old_callers_cannot_restore_it(self):
        self.complete()
        old='【任务+探索】'
        update_metadata(self.folder,dict(session_name=old,session_name_source='agent',activity_naming=dict(
            naming_policy='append-content-v2',manual_name='',suggested_name=old,applied_name=old,
            activities=[dict(name='任务'),dict(name='探索')])))
        self.assertEqual(session_review_payload(self.folder)['title'],self.meta['game'])
        candidate=self.activity_candidate();candidate.pop('title')
        value=agent.name_activities(self.folder,candidate,apply=True)
        self.assertEqual(value['title'],self.meta['game'])
        self.assertEqual(value['session_name'],'')
        self.assertEqual(agent.name_activities(self.folder)['naming_policy'],'separate-title-v3')

    def test_activity_details_are_not_limited_by_short_title_or_manual_name(self):
        self.complete();manual='长'*4090;rename_session(self.folder,manual)
        candidate=self.activity_candidate()
        candidate['activities']=[dict(name=str(i)+'具体任务与探索内容'*2,event_ids=['e1']) for i in range(8)]
        value=agent.name_activities(self.folder,candidate,apply=True)
        self.assertGreater(len(value['activity_details']),100)
        self.assertEqual(value['session_name'],manual)
        before=(self.folder/'session.json').read_bytes()
        candidate=self.activity_candidate();candidate['title']='长'*61
        with self.assertRaisesRegex(ValueError,'60字'):agent.name_activities(self.folder,candidate,apply=True)
        self.assertEqual((self.folder/'session.json').read_bytes(),before)

    def test_activity_naming_fences_manual_changes_and_stale_analysis(self):
        self.complete()
        candidate = self.activity_candidate()
        rename_session(self.folder, '刚手动修改')
        before = (self.folder/'session.json').read_bytes()
        with self.assertRaisesRegex(ValueError, '名称已被修改'):
            agent.name_activities(self.folder, candidate, apply=True)
        self.assertEqual((self.folder/'session.json').read_bytes(), before)
        candidate = self.activity_candidate()
        raw = recorder.read(self.folder/agent.RESULT)
        raw['summary'] = '已在相同素材上完成另一轮分析'
        recorder.write(self.folder/agent.RESULT, raw)
        with self.assertRaisesRegex(ValueError, '预处理结果'):
            agent.name_activities(self.folder, candidate, apply=True)
        self.assertEqual((self.folder/'session.json').read_bytes(), before)
        candidate = self.activity_candidate()
        update_metadata(self.folder, {'input_offset_seconds': 2})
        agent.publish_ready(self.folder)
        with self.assertRaises(ValueError): agent.name_activities(self.folder, candidate, apply=True)

    def test_activity_naming_waits_for_current_completed_result(self):
        with self.assertRaises((ValueError, FileNotFoundError)):
            agent.name_activities(self.folder)
        self.complete()
        candidate = self.activity_candidate()
        job = agent.reprocess(self.folder, 'other-worker', '合成重新整理')
        with self.assertRaisesRegex(ValueError, '仍在预处理'):
            agent.name_activities(self.folder, candidate, apply=True)
        agent.fail(self.folder, job['token'], '合成停止；旧结果仍可用')
        self.assertEqual(agent.name_activities(self.folder, candidate, apply=True)['state'], 'complete')

    def test_activity_naming_rejects_untraceable_or_ambiguous_types(self):
        self.complete()
        candidate = self.activity_candidate()
        before = (self.folder/'session.json').read_bytes()
        changes = [dict(activities=[]), dict(expected_name=None), dict(version=True),
                   dict(activities=[dict(name='仅猜测', event_ids=['missing'])]),
                   dict(activities=[dict(name='探索', event_ids=[])]),
                   dict(activities=[dict(name='任务', event_ids=['e1']), dict(name='任务', event_ids=['e1'])])]
        # Include display delimiters and controls that would make the generated title ambiguous.
        changes.extend(dict(activities=[dict(name=label, event_ids=['e1'])])
                       for label in ('任务+探索', '【任务】', 'task\nlabel', '任务\x7f'))
        changes.append(dict(activities=[dict(name='过长的单个内容名称'*4, event_ids=['e1'])]))
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    agent.name_activities(self.folder, candidate | change, apply=True)
                self.assertEqual((self.folder/'session.json').read_bytes(), before)

    def test_activity_naming_cli_inspection_preview_and_apply(self):
        from contextlib import redirect_stdout
        from io import StringIO
        self.complete()
        file = self.root/'活动命名.json'
        recorder.write(file, self.activity_candidate())
        for arguments, expected in (([], None), (['--file', str(file)], 'preview'),
                                    (['--file', str(file), '--apply'], 'complete')):
            output = StringIO()
            with redirect_stdout(output):
                code = agent_cli.main(['name-activities', str(self.folder), *arguments])
            self.assertEqual(code, 0, output.getvalue())
            value = json.loads(output.getvalue())
            self.assertNotIn('private-sentinel', output.getvalue())
            if expected: self.assertEqual(value['data']['state'], expected)
        output = StringIO()
        with redirect_stdout(output):
            code = agent_cli.main(['name-activities', str(self.folder), '--apply'])
        self.assertEqual(code, 1)
        self.assertIn('--file', json.loads(output.getvalue())['error'])

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

    def test_unchanged_recorder_selection_preserves_material_and_completed_analysis(self):
        from speaker_roles import transcript_id
        recorder.write(self.folder/'录像.whisper.json',dict(segments=self.segments,speaker_analysis=dict(
            version=1,transcript_id=transcript_id(self.segments),suggested_id=0,
            confidence='recommended',reason='duration_and_level',speakers=[])))
        self.manifest=agent.publish_ready(self.folder)
        self.complete()
        api=ReviewAPI(self.folder,{})
        def snapshot():
            return {p.name:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.folder.iterdir() if p.is_file()}
        before=snapshot()
        for ident,automatic in [(0,False),(None,True),(0,False)]:
            result=api.set_recorder_speaker(ident,transcript_id(self.segments),automatic)
            self.assertTrue(result['ok'],result)
            self.assertEqual(result['data']['source'],'auto')
            self.assertEqual(agent.preprocessing_status(self.folder)['state'],'complete')
            self.assertEqual(snapshot(),before)
        self.assertTrue(api.set_recorder_speaker(1,transcript_id(self.segments))['ok'])
        self.assertEqual(agent.preprocessing_status(self.folder)['state'],'stale')
        before=snapshot()
        self.assertTrue(api.set_recorder_speaker(1,transcript_id(self.segments))['ok'])
        self.assertEqual(snapshot(),before)

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
        cli=Path(agent_cli.__file__).resolve()
        bootstrap=(f'import runpy,sys;sys.path.insert(0,{str(cli.parent)!r});'
                   f'sys.argv=[{str(cli)!r},*sys.argv[1:]];'
                   f'runpy.run_path({str(cli)!r},run_name="__main__")')
        run=subprocess.run([sys.executable,'-I','-B','-c',bootstrap,'evidence',str(self.folder),'--start','2','--end','4'],
                           capture_output=True,encoding='utf-8',creationflags=recorder.HIDDEN)
        self.assertEqual(run.returncode,0,run.stderr+run.stdout)
        self.assertEqual(json.loads(run.stdout)['data']['session_id'],'fixture')


if __name__=='__main__':unittest.main()
