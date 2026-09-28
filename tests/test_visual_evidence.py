"""Budgeted packets over real synthetic VFR video. No real sessions or AI."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

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

    def test_transient_bundle_is_kept_whole_or_explicitly_deferred(self):
        groups=[dict(id='a',kind='appearance',times=[0]),
                dict(id='b',kind='transient',times=[1,1.1,1.2]),
                dict(id='c',kind='appearance',times=[3])]
        chosen,deferred=evidence._initial_times(groups,6)
        self.assertTrue({1,1.1,1.2}.issubset(chosen));self.assertFalse(deferred)
        chosen,deferred=evidence._initial_times(groups,4)
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

    def test_cli_budget_is_json_without_images(self):
        output=io.StringIO()
        with redirect_stdout(output): code=agent_cli.main(['visual-budget',str(self.plan)])
        self.assertEqual(code,0)
        self.assertEqual(json.loads(output.getvalue())['data']['issued'],0)


if __name__=='__main__': unittest.main()
