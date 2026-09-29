"""Budgeted packets over real synthetic VFR video. No real sessions or AI."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import agent_cli
import visual_evidence as evidence
import visual_nodes as visual
import test_visual_nodes as fixtures


class EvidencePlanTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.VisualNodesTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.folder=self.fixture.folder
        self.root=self.fixture.root
        self.value,self.index=self.fixture.extract()
        self.plan=Path(evidence.create_plan(self.value['index'],self.root/'plan',total=12,initial=4,review=2)['plan'])

    def test_optional_image_stats_never_seek_or_spend_budget(self):
        protected=[self.plan,self.plan.parent/'budget.json',Path(self.value['index'])]
        before={str(p):evidence._hash(p) for p in protected}
        with patch.object(visual,'_decode') as decode, patch.object(visual,'_existing_image_stats',wraps=visual._existing_image_stats) as stats:
            plain=visual.read_candidates(self.value['index'],start=0,end=3)
            self.assertNotIn('image_stats',plain)
            stats.assert_not_called()
            hinted=visual.read_candidates(self.value['index'],start=.58,end=1.5,image_stats=True)
            self.assertFalse(hinted['actual_image_inspection'])
            self.assertTrue(hinted['image_stats']['pictures'])
            self.assertEqual(hinted['columns'][-1],'frame_hints')
            self.assertLessEqual(stats.call_count,12)
            decode.assert_not_called()
        output=io.StringIO()
        with redirect_stdout(output):
            code=agent_cli.main(['visual-candidates',self.value['index'],'--start','0','--end','3','--image-stats'])
        self.assertEqual(code,0)
        self.assertIn('image_stats',json.loads(output.getvalue())['data'])
        self.assertEqual(before,{str(p):evidence._hash(p) for p in protected})

    def test_pixel_stats_describe_bright_corner_and_uniform_grey_without_classification(self):
        import av
        directory=Path(self.value['index']).parent/'images'
        for grey in (0,23):
            rgb=np.full((72,128,3),grey,np.uint8)
            rgb[0:2,0:2]=255
            content=visual._jpeg(av.VideoFrame.from_ndarray(rgb,format='rgb24'))
            path=directory/(hashlib.sha256(content).hexdigest()+'.jpg')
            path.write_bytes(content)
            row=visual._existing_image_stats(path)
            self.assertEqual(row['state'],'measured')
            self.assertGreater(row['rgb_max'],10)
            self.assertAlmostEqual(row['rgb_mean'],grey,delta=1)
            if grey==0:self.assertGreater(row['pixels_all_channels_below_10'],.99)
            else:self.assertLess(row['pixels_all_channels_below_10'],.01)
            self.assertNotIn('low_information',row)
            self.assertNotIn('usable',row)
        changed=directory/('0'*64+'.jpg')
        changed.write_bytes(content)
        self.assertEqual(visual._existing_image_stats(changed)['reason'],'image_hash_mismatch')

    def test_image_hints_bound_unique_reads_and_keep_unknowns_and_original_times(self):
        index_path=Path(self.value['index'])
        image_dir=index_path.parent/'images'
        refs=[]
        for i in range(14):
            name=f'{i:064x}.jpg'
            (image_dir/name).write_bytes(b'only mocked statistics read this')
            refs.append(dict(time=i,role='representative',path='images/'+name))
        refs += [dict(refs[0]),dict(time=14.3,role='after',path=None)]
        records=[dict(row=dict(frames=refs))]
        with patch.object(visual,'_existing_image_stats',return_value={'state':'measured'}) as stats:
            hints,measured=visual._candidate_image_hints(index_path,records,1,12)
        self.assertEqual(stats.call_count,12)
        self.assertEqual(len(measured),12)
        self.assertEqual(hints[0][12][-1],'inspection_limit')
        self.assertEqual(hints[0][14][-1],hints[0][0][-1])
        self.assertEqual(hints[0][-1],[14.3,'after',False,'unpictured'])

    def test_decoder_eof_is_unknown_and_does_not_hide_following_candidates(self):
        import av
        index_path=Path(self.value['index'])
        paths=list((index_path.parent/'images').glob('*.jpg'))[:2]
        self.assertEqual(len(paths),2)
        refs=[dict(time=i,role='representative',path='images/'+p.name) for i,p in enumerate(paths)]
        original_open=av.open
        calls=[]
        def fail_once(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:raise av.error.EOFError(541478725,'Synthetic image EOF')
            return original_open(*args,**kwargs)
        with patch('av.open',side_effect=fail_once):
            hints,measured=visual._candidate_image_hints(index_path,[dict(row=dict(frames=refs))],0,2)
        self.assertEqual(len(hints[0]),2)
        self.assertEqual(measured['p01'],dict(state='unknown',reason='image_read_failed'))
        self.assertEqual(measured['p02']['state'],'measured')

    def test_pixel_stats_stop_before_oversize_file_open_or_explicit_frame_decode(self):
        oversize=self.root/'oversize.jpg'
        oversize.write_bytes(b'0'*(16*1024*1024+1))
        with patch('av.open') as opened:
            self.assertEqual(visual._existing_image_stats(oversize)['reason'],'image_size_limit')
            opened.assert_not_called()
        path=next((Path(self.value['index']).parent/'images').glob('*.jpg'))
        container=MagicMock()
        container.__enter__.return_value=container
        container.streams.video[0].width=4000
        container.streams.video[0].height=4000
        with patch('av.open',return_value=container):
            self.assertEqual(visual._existing_image_stats(path)['reason'],'image_dimensions_limit')
        container.decode.assert_not_called()
        container.__exit__.assert_called_once()

    def test_plan_does_not_count_generation_as_inspection_or_change_source(self):
        self.assertEqual(evidence.budget_status(self.plan)['issued'],0)
        result=evidence.packet(self.plan,'first',phase='initial',question='查看主要过程')
        self.assertEqual(result['state'],'ready')
        self.assertLessEqual(len(result['frames']),4)
        self.assertFalse(result['actual_image_inspection'])
        self.assertTrue(all(Path(f['path']).is_relative_to(self.plan.parent/'images') for f in result['frames']))
        self.assertEqual(self.fixture.original,{p.name:evidence._hash(p) for p in self.folder.iterdir()})

    def test_same_receipt_is_idempotent_but_review_is_charged_again(self):
        first=evidence.packet(self.plan,'first',phase='initial',question='查看主要过程')
        replay=evidence.packet(self.plan,'first',phase='initial',question='查看主要过程')
        self.assertTrue(replay['replayed'])
        self.assertEqual(first['budget']['issued'],replay['budget']['issued'])
        again=evidence.packet(self.plan,'check',phase='review',question='核对同一画面',times=[first['frames'][0]['time']])
        self.assertEqual(again['budget']['issued'],first['budget']['issued']+1)
        with self.assertRaises(ValueError):
            evidence.packet(self.plan,'first',phase='initial',question='另一个问题')

    def test_shared_budget_preserves_review_reserve_and_does_not_extract_when_rejected(self):
        p=Path(evidence.create_plan(self.value['index'],self.root/'small',total=4,initial=2,review=2)['plan'])
        evidence.packet(p,'first',phase='initial',question='先看')
        if evidence.budget_status(p)['remaining']>2:
            evidence.packet(p,'fill',phase='inspect',question='使用首轮未发满的剩余名额',times=[1])
        with patch.object(evidence,'_frame') as frame:
            denied=evidence.packet(p,'extra',phase='inspect',question='还有一张',times=[.625])
        self.assertEqual(denied['state'],'budget_exceeded')
        frame.assert_not_called()
        checked=evidence.packet(p,'check',phase='review',question='复核前后',times=[.58,.85])
        self.assertEqual(checked['budget']['remaining'],0)
        self.assertEqual(evidence.packet(p,'too-many',phase='review',question='再看',times=[1])['state'],'budget_exceeded')

    def test_window_packet_includes_short_popup_and_actual_vfr_time(self):
        result=evidence.packet(self.plan,'popup',phase='inspect',question='短弹窗是否出现并恢复',start=.58,end=.85,limit=6)
        self.assertEqual(result['state'],'ready')
        self.assertTrue(any(.6<=f['time']<.8 for f in result['frames']))
        self.assertIn(.85,[f['requested_time'] for f in result['frames']])
        vfr=evidence.packet(self.plan,'vfr',phase='review',question='跨帧位置',times=[.70])
        self.assertAlmostEqual(vfr['frames'][0]['time'],.67)
        self.assertEqual(vfr['frames'][0]['requested_time'],.70)

    def test_initial_budget_is_not_multiplied_by_multiple_workers(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(lambda i:evidence.packet(self.plan,f'first-{i}',phase='initial',question='查看'),range(4)))
        self.assertEqual(sum(r['state']=='ready' for r in results),1)
        self.assertLessEqual(evidence.budget_status(self.plan)['issued'],4)

    def test_failed_attempt_is_retained_and_never_silently_retried(self):
        with patch.object(evidence,'_frame',side_effect=ValueError('synthetic failure')):
            with self.assertRaisesRegex(ValueError,'synthetic failure'):
                evidence.packet(self.plan,'fail',phase='inspect',question='缺口',times=[.625])
        self.assertEqual(evidence.budget_status(self.plan)['issued'],1)
        with patch.object(evidence,'_frame') as frame:
            retry=evidence.packet(self.plan,'fail',phase='inspect',question='缺口',times=[.625])
        self.assertEqual(retry['state'],'failed')
        frame.assert_not_called()

    def test_stale_source_and_changed_index_reject_old_plan_and_receipt(self):
        evidence.packet(self.plan,'first',phase='initial',question='查看')
        self.fixture.meta['input_offset_seconds']=.9
        self.fixture.write('session.json',self.fixture.meta)
        with self.assertRaisesRegex(ValueError,'过期'):
            evidence.packet(self.plan,'first',phase='initial',question='查看')

    def test_receipt_rejects_corrupted_cached_image(self):
        result=evidence.packet(self.plan,'first',phase='initial',question='查看')
        Path(result['frames'][0]['path']).write_bytes(b'corrupted fixture')
        with self.assertRaisesRegex(ValueError,'校验失败'):
            evidence.packet(self.plan,'first',phase='initial',question='查看')

    def test_source_change_during_extraction_does_not_publish_receipt(self):
        original=evidence._frame
        def changed(video,at):
            result=original(video,at)
            self.fixture.meta['input_offset_seconds']=.9
            self.fixture.write('session.json',self.fixture.meta)
            return result
        with patch.object(evidence,'_frame',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'过期'):
                evidence.packet(self.plan,'changed',phase='inspect',question='核对',times=[.625])
        self.assertFalse((self.plan.parent/'requests/changed.json').exists())
        ledger=evidence._load(self.plan.parent/'budget.json')
        self.assertEqual(ledger['requests']['changed']['state'],'failed')

    def test_index_change_rejects_bound_plan(self):
        index_path=Path(self.value['index'])
        index_path.write_text(index_path.read_text(encoding='utf-8')+'\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'过期'):
            evidence.budget_status(self.plan)

    def test_plan_and_requests_validate_boundaries(self):
        for kwargs in (dict(total=2,initial=2,review=1),dict(total=True),dict(total=201)):
            with self.assertRaises(ValueError): evidence.create_plan(self.value['index'],self.root/'bad',**kwargs)
        with self.assertRaises(ValueError): evidence.create_plan(self.value['index'],self.folder/'bad')
        for kwargs in (dict(request_id='../escape',phase='review',question='查看',times=[1]),
                       dict(request_id='empty',phase='review',question=' ',times=[1]),
                       dict(request_id='out',phase='review',question='查看',times=[99]),
                       dict(request_id='bad',phase='inspect',question='查看',start=0,end=200)):
            with self.assertRaises(ValueError): evidence.packet(self.plan,**kwargs)

    def test_near_pixel_grouping_is_consecutive_not_global_deduplication(self):
        index=dict(self.index,nodes=[])
        for i in range(4):
            index['nodes'].append(dict(id=str(i),start=i,end=i,kind='context',
                                      frames=[dict(time=i,path='images/mock.jpg')]))
        a=np.zeros((36,64,3),dtype='float32');b=np.full_like(a,200)
        with patch.object(evidence,'_picture',return_value=Path('mock')), \
                patch.object(evidence,'_signature',side_effect=[a,a,b,a]):
            groups,_=evidence._groups(index,Path(self.value['index']))
        self.assertEqual([g['times'] for g in groups],[[0,1],[2],[3]])

    def test_legacy_initial_transient_bundle_remains_compatible(self):
        groups=[dict(id='a',kind='appearance',times=[0]),
                dict(id='b',kind='transient',times=[1,1.1,1.2]),
                dict(id='c',kind='appearance',times=[3])]
        chosen,deferred=evidence._initial_times_legacy(groups,6)
        self.assertTrue({1,1.1,1.2}.issubset(chosen));self.assertFalse(deferred)
        chosen,deferred=evidence._initial_times_legacy(groups,4)
        self.assertFalse({1,1.1,1.2}.intersection(chosen));self.assertEqual(deferred,['b'])

    def test_initial_transitions_do_not_displace_broad_temporal_orientation(self):
        groups=[dict(id=str(i),kind='appearance',times=[i]) for i in range(101)]
        groups += [dict(id='early',kind='transient',times=[1,1.1,1.2]),
                   dict(id='late',kind='transient',times=[98,98.1,98.2])]
        chosen,deferred=evidence._initial_times(groups,8)
        self.assertEqual(len(chosen),8)
        self.assertTrue(any(20<=at<=35 for at in chosen))
        self.assertTrue(any(45<=at<=55 for at in chosen))
        self.assertTrue(any(70<=at<=85 for at in chosen))
        self.assertTrue(deferred)

    def test_initial_skips_near_black_and_does_not_fill_with_adjacent_burst_frames(self):
        groups=[dict(id=str(t),kind='appearance',times=[t]) for t in (0,1,10,10.1,10.2,30,50,80,100)]
        pictures={0:dict(near_black=True),1:dict(near_black=True)}
        selected,_=evidence._initial_times(groups,8,pictures)
        self.assertNotIn(0,selected);self.assertNotIn(1,selected)
        self.assertEqual(sum(10<=t<=10.2 for t in selected),1)
        self.assertLess(len(selected),8)

    def test_readable_weak_state_can_outrank_a_dense_primary_tail(self):
        # Different lengths and locations guard against fitting one real timestamp.
        for start,end,popup in ((0,25,6),(30,80,61),(0,5,1.7)):
            duration=(end-start)/30
            weak=dict(kind='change',start=popup,end=popup+duration,
                      frames=[dict(time=popup,role='before'),dict(time=popup+duration,role='after')],
                      metrics=dict(adjacent_global=.006,moving_tile_fraction=.1))
            tail=dict(id='tail',kind='transient',start=end-.15,end=end,
                      frames=[dict(time=end-.15,role='before'),dict(time=end-.1,role='peak'),dict(time=end,role='after')],
                      metrics=dict(adjacent_global=.3,moving_tile_fraction=.8))
            motion=dict(id='m',kind='motion',start=start,end=end,
                        frames=[dict(time=start,role='before'),dict(time=end,role='after')],motion_observations=[weak])
            index=dict(source=dict(duration_seconds=end),range=dict(start=start,end=end),nodes=[motion,tail])
            selected,_,decisions=evidence._window_choice(index,start,end,4)
            self.assertIn((weak['start']+weak['end'])/2,selected)
            self.assertIn(start,selected);self.assertIn(end,selected)
            self.assertTrue(any(d['level']=='weak' for d in decisions))
            self.assertEqual(sum(end-.2<=t<=end for t in selected),1)

    def test_plan_without_selection_version_uses_legacy_window_and_preserves_receipt(self):
        plan=evidence._load(self.plan)
        plan['version']=1
        plan.pop('selection_version')
        evidence.write(self.plan,plan)
        with patch.object(evidence,'_window_choice',side_effect=AssertionError('must retain legacy')):
            first=evidence.packet(self.plan,'legacy',phase='inspect',question='既有计划',start=.58,end=.85,limit=4)
            replay=evidence.packet(self.plan,'legacy',phase='inspect',question='既有计划',start=.58,end=.85,limit=4)
        self.assertTrue(replay['replayed'])
        self.assertEqual(first['frames'],replay['frames'])
        self.assertEqual(first['budget'],replay['budget'])

    def test_compact_interval_read_is_bounded_and_filters_nested_observations(self):
        index_path=Path(self.value['index'])
        index=json.loads(index_path.read_text(encoding='utf-8'))
        node=index['nodes'][0]
        node['start']=0;node['end']=3
        node['transcript']=[dict(text='not-to-repeat'*10000)]
        node['motion_observations']=[dict(kind='change',start=i/100,end=i/100+.01,frames=[])
                                     for i in range(300)]
        index_path.write_text(json.dumps(index),encoding='utf-8')
        result=visual.read_candidates(index_path,start=.6,end=.8,limit=3)
        self.assertEqual(len(result['rows']),3)
        self.assertIsNotNone(result['next_offset'])
        self.assertLess(result['read_metrics']['data_characters_without_read_metrics'],2500)
        self.assertNotIn('not-to-repeat',json.dumps(result))
        page=visual.read_candidates(index_path,start=.6,end=.8,limit=60)
        for row in page['rows']:
            self.assertGreaterEqual(row[4],.6);self.assertLessEqual(row[3],.8)
        self.assertTrue(any(row[1]=='weak' for row in page['rows']))

    def test_primary_navigation_is_bounded_and_weak_evidence_is_expandable(self):
        path=Path(self.value['index'])
        index=evidence._load(path)
        motion=dict(id='motion',kind='motion',start=0,end=3,frames=[],
                    motion_observations=[dict(kind='change',start=i/100,end=i/100+.01,frames=[])
                                         for i in range(250)])
        later=dict(id='later',kind='context',start=2.6,end=3,frames=[])
        index['nodes']=[motion,later]
        index['coverage']['node_index_complete']=False
        index['stats']['detector'].update(omitted_nodes=0,omitted_weak_motion_observations=12,
                                        omitted_time_range=[2.7,3])
        path.write_text(json.dumps(index),encoding='utf-8')
        digest=evidence._hash(path)
        all_rows=visual.read_candidates(path,start=0,end=3,limit=24)
        self.assertNotIn('later',[r[0] for r in all_rows['rows']])
        primary=visual.read_candidates(path,start=0,end=3,level='primary',limit=24)
        self.assertEqual([r[0] for r in primary['rows']],['motion','later'])
        self.assertEqual(primary['matching_by_level'],dict(primary=2,weak=250))
        self.assertIsNone(primary['next_offset'])
        self.assertFalse(primary['node_index_complete'])
        self.assertEqual(primary['omissions']['weak_observations'],12)
        self.assertTrue(primary['omissions']['overlaps_query'])
        counts=primary['columns'].index('retained_weak_in_range')
        self.assertEqual(primary['rows'][0][counts],250)
        weak=visual.read_candidates(path,start=0,end=.2,level='weak',parent='motion',limit=5)
        self.assertEqual(len(weak['rows']),5)
        self.assertEqual(weak['next_offset'],5)
        self.assertEqual([r[0] for r in weak['rows']], [f'motion/w{i}' for i in range(1,6)])
        self.assertFalse(weak['omissions']['overlaps_query'])
        for kwargs in (dict(level='invalid'),dict(level='primary',parent='motion'),
                       dict(level='weak',parent='missing')):
            with self.assertRaises(ValueError):visual.read_candidates(path,start=0,end=3,**kwargs)
        output=io.StringIO()
        with redirect_stdout(output):
            code=agent_cli.main(['visual-candidates',str(path),'--start','0','--end','3','--level','primary'])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(output.getvalue())['data']['total_matching'],2)
        self.assertEqual(evidence._hash(path),digest)

    def test_compact_candidates_cli_and_limits(self):
        output=io.StringIO()
        with redirect_stdout(output):
            code=agent_cli.main(['visual-candidates',self.value['index'],'--start','0','--end','1','--limit','2'])
        self.assertEqual(code,0)
        self.assertLessEqual(len(json.loads(output.getvalue())['data']['rows']),2)
        for kwargs in (dict(start=0,end=0),dict(start=0,end=1,limit=61),dict(start=0,end=999)):
            with self.assertRaises(ValueError):visual.read_candidates(self.value['index'],**kwargs)

    def test_cli_budget_is_json_without_images(self):
        output=io.StringIO()
        with redirect_stdout(output): code=agent_cli.main(['visual-budget',str(self.plan)])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(output.getvalue())['data']['issued'],0)


if __name__=='__main__': unittest.main()
