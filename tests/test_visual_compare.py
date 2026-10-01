"""Local-state retrieval on synthetic pixels/video, not semantic acceptance."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from fractions import Fraction
import io
import json
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import av
import numpy as np

import agent_cli
import visual_compare as compare
import visual_evidence as evidence
import test_visual_nodes as fixtures


def picture(value=0):
    return np.full((90, 160, 3), value, dtype=np.uint8)


def samples(pictures):
    for i, rgb in enumerate(pictures):
        yield dict(time=i/30, pts=i, time_base='1/30', pts_origin_seconds=0), \
            av.VideoFrame.from_ndarray(rgb, format='rgb24')


class LocalPixelTests(unittest.TestCase):
    def runs(self, pictures, region=None):
        return compare._occurrences(samples(pictures), region or [0,0,1,1])[0]

    def test_static_and_minor_pixel_noise_do_not_create_states(self):
        self.assertEqual(len(self.runs([picture(50)]*8)), 1)
        self.assertEqual(len(self.runs([picture(n) for n in (50,51,49,52,50)])), 1)

    def test_a_b_a_and_one_frame_state_keep_adjacent_order(self):
        runs = self.runs([picture(),picture(),picture(200),picture(),picture()])
        self.assertEqual([r['time'] for r in runs], [0,2/30,3/30])
        self.assertEqual([r['samples'] for r in runs], [2,1,2])
        self.assertEqual([r['pts'] for r in runs], [0,2,3])

    def test_high_motion_outside_roi_does_not_hide_small_local_change(self):
        images=[]
        for i in range(6):
            rgb=picture(200 if i%2 else 0)
            rgb[20:40,60:80]=50
            if i in (2,3): rgb[25:35,65:75]=210
            images.append(rgb)
        full=self.runs(images)
        local=self.runs(images, [60/160,20/90,20/160,20/90])
        self.assertEqual(len(full),6)
        self.assertEqual([r['time'] for r in local],[0,2/30,4/30])

    def test_animation_inside_roi_remains_candidates_not_semantic_filtering(self):
        images=[]
        for i in range(8):
            rgb=picture()
            rgb[20:40,5+i*15:20+i*15]=220
            images.append(rgb)
        self.assertGreater(len(self.runs(images)),1)

    def test_gradual_change_compares_occurrence_anchor_not_only_previous_frame(self):
        runs=self.runs([picture(n) for n in range(50,70,2)])
        self.assertGreater(len(runs),1)


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.VisualNodesTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root,self.folder=self.fixture.root,self.fixture.folder
        self.value,self.index=self.fixture.extract()
        self.plan=Path(evidence.create_plan(self.value['index'],self.root/'plan',
                                            total=4,initial=1,review=1)['plan'])

    def run_compare(self, ident='local', **kwargs):
        options=dict(question='Which local changes precede and follow the action?',
                     start=0,end=3,mode='scan',limit=12)
        options.update(kwargs)
        return compare.compare(self.plan,ident,**options)

    def timing_fixture(self, *, coding_gap=False, drop_decoded_frame=False):
        # Millisecond-quantized B-frame PTS order 0,67,33,100; coding order
        # durations 34,33,33,34 cannot be used as presentation durations.
        base=Fraction(1,1000)
        frames=[SimpleNamespace(pts=t,time_base=base,duration=d)
                for t,d in ((0,34),(33,33),(67,33),(100,34))]
        decoded=[[],[frames[0]],[] if drop_decoded_frame else [frames[1]],
                 [frames[2]],[frames[3]]]
        packets=[]
        data=[(0,-67,34),(67,-33,33),(33,1 if coding_gap else 0,33),
              (100,34 if coding_gap else 33,34),(None,None,0)]
        for (pts,dts,duration),result in zip(data,decoded):
            packets.append(SimpleNamespace(pts=pts,dts=dts,duration=duration,time_base=base,
                                           size=1 if pts is not None else 0,
                                           decode=lambda result=result:result))
        stream=SimpleNamespace(width=160,height=90,time_base=base)
        container=SimpleNamespace(demux=lambda stream:iter(packets),seek=lambda *a,**kw:None,
                                  close=lambda:None)
        return container,stream,0.

    def test_b_frame_quantization_uses_presentation_pts_not_decode_duration(self):
        with patch.object(compare.visual,'_open_video',return_value=self.timing_fixture()), \
                patch.object(compare,'_signature',return_value=np.zeros((8,8,3),np.float32)):
            result=self.run_compare(end=.09)
        self.assertTrue(result['coverage']['complete_decoding'])
        self.assertEqual(result['coverage']['undecoded_ranges'],[])
        self.assertEqual(result['cost']['presentation_duration_mismatches'],2)
        self.assertEqual(result['occurrences'][0]['frame_end'],.033)
        self.assertEqual(result['occurrences'][0]['declared_frame_end'],.034)
        self.assertEqual(result['occurrences'][0]['frame_end_basis'],'next_source_pts')
        self.assertFalse(result['coverage']['recording_drop_detection'])

    def test_one_tick_coding_discontinuity_remains_unknown_not_rounded_away(self):
        with patch.object(compare.visual,'_open_video',return_value=self.timing_fixture(coding_gap=True)), \
                patch.object(compare,'_signature',return_value=np.zeros((8,8,3),np.float32)):
            result=self.run_compare(end=.09)
        self.assertFalse(result['coverage']['complete_decoding'])
        self.assertEqual(result['cost']['coding_timing_discontinuities'],1)
        self.assertEqual(result['cost']['coding_timing_examples'],[[0.,.001]])
        self.assertEqual(result['coverage']['undecoded_ranges'],[])

    def test_packet_not_returned_by_decoder_is_not_hidden_by_next_pts_boundary(self):
        with patch.object(compare.visual,'_open_video',return_value=self.timing_fixture(drop_decoded_frame=True)), \
                patch.object(compare,'_signature',return_value=np.zeros((8,8,3),np.float32)):
            result=self.run_compare(end=.09)
        self.assertFalse(result['coverage']['complete_decoding'])
        self.assertEqual(result['cost']['unaccounted_packet_pts'],[.033])
        self.assertEqual(result['cost']['unaccounted_packet_pts_count'],1)

    def test_timing_algorithm_change_does_not_silently_reuse_old_comparison(self):
        self.run_compare()
        receipt_path=self.plan.parent/'comparisons/local.json'
        old=evidence._load(receipt_path)
        old['spec'].pop('timing_version')
        evidence.write(receipt_path,old)
        before=receipt_path.read_bytes()
        with self.assertRaisesRegex(ValueError,'编号'):self.run_compare()
        self.assertEqual(receipt_path.read_bytes(),before)

    def test_real_vfr_scan_preserves_source_pts_and_short_return(self):
        result=self.run_compare(end=2.96)
        self.assertEqual(result['state'],'ready')
        self.assertEqual(len(result['occurrences']),3)
        self.assertEqual(result['selected_times'],[0,.62,.85])
        self.assertEqual(result['cost']['compared_frames'],len(self.fixture.pts))
        self.assertTrue(result['coverage']['complete_decoding'])
        self.assertFalse(result['actual_image_inspection'])
        self.assertEqual(result['cost']['images_issued'],0)
        self.assertEqual(evidence.budget_status(self.plan)['issued'],0)
        for row in result['occurrences']:
            self.assertEqual(row['time'],float(row['pts']*Fraction(row['time_base']))-row['pts_origin_seconds'])

    def test_early_eof_reports_uncovered_tail_and_does_not_resolve_distant_target(self):
        result=self.run_compare(mode='candidates')
        self.assertFalse(result['coverage']['complete_decoding'])
        self.assertIn(3,result['cost']['unresolved_target_times'])
        self.assertEqual(result['coverage']['undecoded_ranges'][-1][1],3)
        self.assertNotIn(3,[r.get('requested_time') for r in result['occurrences']])
        scan=self.run_compare('scan-tail')
        self.assertFalse(scan['coverage']['complete_decoding'])
        self.assertAlmostEqual(scan['coverage']['resume_start'],2.9833125)

    def test_vfr_preceding_boundary_preserves_pts_and_respects_plan_subset(self):
        # The frame at .4 remains visible when a sub-plan begins at .5.
        plan=evidence._load(self.plan)
        plan['range']['start']=.5
        evidence.write(self.plan,plan)
        result=self.run_compare(start=.5,end=.55,mode='candidates')
        self.assertEqual(result['occurrences'][0]['time'],.4)
        self.assertFalse(result['occurrences'][0]['packet_eligible'])
        self.assertEqual(result['selected_times'],[])
        self.assertTrue(result['coverage']['complete_decoding'])
        extended=self.run_compare('later-eligible',start=.5,end=.6,mode='scan')
        self.assertEqual(extended['occurrences'][0]['first_sample'],.4)
        self.assertEqual(extended['selected_times'],[.58])
        self.assertTrue(extended['occurrences'][0]['packet_eligible'])

    def test_candidates_metadata_is_traceable_and_read_only(self):
        protected=[self.plan,self.plan.parent/'budget.json',Path(self.value['index']),
                   *self.folder.iterdir()]
        before={str(p):evidence._hash(p) for p in protected if p.is_file()}
        result=self.run_compare(mode='candidates')
        self.assertTrue(result['coverage']['unsampled_intervals_possible'])
        self.assertTrue(result['selected_times'])
        self.assertIn('candidate_refs',result['occurrences'][0])
        self.assertEqual(before,{str(p):evidence._hash(Path(p)) for p in before})
        self.assertFalse(list((self.plan.parent/'images').iterdir()))
        self.assertFalse(list((self.plan.parent/'requests').iterdir()))

    def test_result_limit_does_not_drop_adjacent_b_state_and_reports_next_occurrence(self):
        result=self.run_compare(limit=2)
        self.assertEqual(result['selected_times'],[0,.62])
        self.assertEqual(result['total_occurrences'],3)
        self.assertEqual(result['omitted_occurrences'],1)
        self.assertEqual(result['next_start'],.85)
        resumed=self.run_compare('resume',start=result['next_start'])
        self.assertEqual(resumed['selected_times'],[.85])

    def test_existing_candidate_cap_fails_without_uniform_sampling(self):
        with patch.object(compare,'MAX_CANDIDATES',1):
            with self.assertRaisesRegex(ValueError,'不静默抽稀'):
                self.run_compare(mode='candidates')
        receipt=evidence._load(self.plan.parent/'comparisons/local.json')
        self.assertEqual(receipt['state'],'failed')
        self.assertEqual(receipt['cost']['decoder_frames'],0)

    def test_explicit_scan_finds_brief_state_absent_from_sparse_candidates(self):
        index=evidence._load(self.value['index'])
        index['nodes']=[dict(id='only',kind='context',start=0,end=3,
                            frames=[dict(time=0,role='before'),dict(time=2.95,role='after')])]
        path=self.root/'sparse-index.json'
        evidence.write(path,index)
        plan=evidence._load(self.plan)
        plan['index']=str(path)
        plan['index_sha256']=evidence._hash(path)
        evidence.write(self.plan,plan)
        coarse=self.run_compare('coarse',mode='candidates')
        fine=self.run_compare('fine',mode='scan')
        self.assertEqual(coarse['total_occurrences'],1)
        self.assertEqual(fine['total_occurrences'],3)
        self.assertIn(.62,fine['selected_times'])

    def test_decode_cap_is_hard_and_partial_not_complete(self):
        with patch.object(compare,'MAX_DECODE_FRAMES',4):
            result=self.run_compare()
        self.assertEqual(result['cost']['decoder_frames'],4)
        self.assertTrue(result['cost']['stopped_at_decode_limit'])
        self.assertFalse(result['coverage']['complete_decoding'])
        self.assertLess(result['coverage']['sampled_range'][1],3)

    def test_region_validation_and_short_scan_bounds(self):
        for region in ([0,0,0,1],[-.1,0,1,1],[0,0,2,1],[0,0,float('nan'),1],
                       [0,0,float('inf'),1],[False,0,1,1],[0,1,1,1],[0,0,1]):
            with self.assertRaises(ValueError):self.run_compare(region=region)
        for options in (dict(start=1,end=1),dict(end=31),dict(mode='bad'),dict(limit=0),
                        dict(limit=True),dict(limit=25),dict(start=-1),dict(question=' ')):
            with self.assertRaises(ValueError):self.run_compare(**options)
        with self.assertRaises(ValueError):self.run_compare('../escape')
        with self.assertRaisesRegex(ValueError,'2×2'):
            self.run_compare(region=[0,0,.001,.001])

    def test_replay_and_request_identity_do_not_decode_again(self):
        first=self.run_compare()
        path=self.plan.parent/'comparisons/local.json'
        before=path.read_bytes()
        with patch.object(compare,'_frames',side_effect=AssertionError('No decode on replay')):
            replay=self.run_compare()
        self.assertTrue(replay['replayed'])
        self.assertEqual(first['selected_times'],replay['selected_times'])
        self.assertEqual(before,path.read_bytes())
        for kwargs in (dict(question='Different'),dict(mode='candidates'),dict(region=[0,0,.5,1]),
                       dict(limit=5),dict(start=.1)):
            with self.assertRaisesRegex(ValueError,'编号'):self.run_compare(**kwargs)

    def test_parallel_identical_request_has_single_decode(self):
        original=compare._frames
        with patch.object(compare,'_frames',wraps=original) as decode:
            with ThreadPoolExecutor(max_workers=3) as pool:
                results=list(pool.map(lambda _:self.run_compare(),range(3)))
            self.assertEqual(decode.call_count,1)
        self.assertEqual(sum(not r['replayed'] for r in results),1)
        self.assertEqual(self.run_compare()['state'],'ready')

    def test_stale_source_before_and_during_comparison_never_publishes_candidates(self):
        original=compare._occurrences
        def changed(*args,**kwargs):
            result=original(*args,**kwargs)
            self.fixture.meta['input_offset_seconds']=.75
            self.fixture.write('session.json',self.fixture.meta)
            return result
        with patch.object(compare,'_occurrences',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'过期'):
                self.run_compare()
        receipt=evidence._load(self.plan.parent/'comparisons/local.json')
        self.assertEqual(receipt['state'],'failed')
        self.assertNotIn('selected_times',receipt)
        with self.assertRaisesRegex(ValueError,'过期'):self.run_compare('after')

    def test_tampered_bound_index_and_plan_reject_reuse(self):
        self.run_compare()
        path=Path(self.value['index'])
        path.write_bytes(path.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'过期'):self.run_compare()

    def test_plan_change_during_comparison_rejects_results(self):
        original=compare._occurrences
        def changed(*args,**kwargs):
            result=original(*args,**kwargs)
            self.plan.write_bytes(self.plan.read_bytes()+b'\n')
            return result
        with patch.object(compare,'_occurrences',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'计划改变'):self.run_compare()

    def test_source_pts_use_original_budget_and_high_resolution_contract(self):
        result=self.run_compare()
        at=result['selected_times'][1]
        packet=evidence.packet(self.plan,'from-compare',phase='review',question='Read selected state',
                               times=[at],image_width=1920)
        self.assertEqual(packet['frames'][0]['time'],at)
        self.assertEqual(packet['budget']['issued'],1)
        self.run_compare('second')
        self.assertEqual(evidence.budget_status(self.plan)['issued'],1)
        evidence.packet(self.plan,'fill',phase='review',question='Use allowance',times=[0,.1,.23])
        denied=evidence.packet(self.plan,'denied',phase='review',question='No hidden allowance',times=[at])
        self.assertEqual(denied['state'],'budget_exceeded')
        with self.assertRaises(ValueError):
            evidence.packet(self.plan,'too-many-hd',phase='review',question='HD limit',
                            times=result['selected_times'],image_width=1920)

    def test_cli_json_output_includes_no_image_payload(self):
        out=io.StringIO()
        with redirect_stdout(out):
            code=agent_cli.main(['visual-compare',str(self.plan),'--request-id','cli',
                                '--question','Read local state','--start','0','--end','3',
                                '--region','0','0','1','1','--mode','scan','--limit','2'])
        self.assertEqual(code,0)
        value=json.loads(out.getvalue())['data']
        self.assertEqual(value['selected_times'],[0,.62])
        self.assertNotIn('frames',value)
        self.assertEqual(value['cost']['images_issued'],0)


if __name__=='__main__':unittest.main()
