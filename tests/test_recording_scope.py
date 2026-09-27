"""Explicit all-input recording: physical facts and window context are separate."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from input_capture import InputRecorder,recover_capture
from input_capture_windows import WindowsInputSource,TargetWindow,ForegroundLedger
from review_runtime import input_payload


class RecordingScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.now=100.
        self.capture=InputRecorder(self.temp.name,lambda:SimpleNamespace(start=lambda callback:None,stop=lambda:None),
                                   clock=lambda:self.now,flush_interval=1000,recording_scope='all')
        self.capture.start();self.addCleanup(self.capture.stop)
    def send(self,kind,t,**fields):
        self.now=100+t;self.capture.feed(dict(type=kind,timestamp=self.now,**fields))
    def key(self,device,code,t,down=True):
        self.send('button',t,device=device,code=code,down=down,foreground=False)

    def test_background_keyboard_mouse_and_controller_and_continuous_hold_are_retained(self):
        self.send('focus',.1,foreground=True)
        self.key('keyboard','W',1)
        self.send('focus',2,foreground=False)
        self.key('mouse','MouseLeft',3);self.key('xbox','A',4)
        self.key('keyboard','W',5,False);self.key('mouse','MouseLeft',6,False);self.key('xbox','A',7,False)
        self.send('focus',8,foreground=True)
        value=self.capture.stop(duration=9)
        self.assertEqual([(r['code'],r['start'],r['end']) for r in value['intervals']], [('W',1,5),('MouseLeft',3,6),('A',4,7)])
        self.assertEqual(value['recording_scope'],'all')
        self.assertEqual([(r['state'],r['start'],r['end']) for r in value['window_states']],
                         [('unknown',0,.1),('foreground',.1,2),('background',2,8),('foreground',8,9)])
        self.assertEqual(value['gaps'],[])

    def test_late_or_unavailable_window_state_never_erases_physical_input(self):
        self.send('focus',.1,foreground=True);self.key('keyboard','W',1)
        self.send('watermark',2);self.capture._flush()
        self.send('invalidate',1.5);self.key('keyboard','W',4,False)
        self.key('dualsense','Cross',5);self.key('dualsense','Cross',6,False)
        self.send('watermark',7)
        value=self.capture.stop(duration=7)
        self.assertEqual(value['state'],'complete');self.assertNotIn('error',value)
        self.assertEqual([(r['code'],r['end']) for r in value['intervals']],[('W',4),('Cross',6)])
        self.assertEqual(value['window_states'][-1],dict(start=1.5,end=7,state='unknown'))
        self.assertFalse(Path(self.temp.name,'input-events.revocation.json').exists())
        recovered=recover_capture(self.temp.name,7)
        self.assertEqual(recovered['intervals'],value['intervals'])
        self.assertEqual(recovered['window_states'],value['window_states'])

    def test_checkpoint_recovery_retains_window_context_and_real_gaps_separately(self):
        self.send('focus',1,foreground=False);self.key('xbox','A',2)
        self.send('watermark',3);self.capture._flush()
        # Recovery reads a stable live checkpoint into an independent directory.
        with TemporaryDirectory() as other:
            for name in ('input-events.json','input-events.journal'):
                Path(other,name).write_bytes(Path(self.temp.name,name).read_bytes())
            result=recover_capture(other,4)
            self.assertEqual(result['intervals'][0]['end'],3)
            self.assertEqual(result['window_states'][-1],dict(start=1,end=3,state='background'))
            self.assertTrue(any(g['start']==3 and g['end']==4 for g in result['gaps']))
            self.assertFalse(any(g['type']=='window' for g in result['gaps']))

    def test_video_trim_cuts_both_input_and_context_without_losing_prefix(self):
        self.send('focus',1,foreground=False);self.key('keyboard','A',2);self.key('keyboard','A',6,False)
        result=self.capture.stop(duration=7,trim_to=4)
        self.assertEqual(result['intervals'][0]['end'],4)
        self.assertEqual(result['window_states'][-1]['end'],4)
        self.assertIn('"type":"window"',self.capture.journal_path.read_text(encoding='utf-8'))

    def test_all_input_source_flushes_without_foreground_acknowledgements(self):
        source=WindowsInputSource(TargetWindow(1,2,3,'test'),'unused',lambda:110.,capture_all=True)
        source._capture_started=100
        source._observer=SimpleNamespace(ledger=ForegroundLedger(),error=None)
        result=[];source.callback=result.append
        source._foreground=lambda:False
        for device,code in [('keyboard','W'),('mouse','MouseLeft'),('xbox','A')]:
            source._emit(dict(type='button',timestamp=102,device=device,code=code,down=True))
        source._flush_pending()
        self.assertEqual([r['code'] for r in result if r['type']=='button'],['W','MouseLeft','A'])
        self.assertFalse(any(r['type']=='coverage_gap' for r in result))
        source._observer.error='synthetic observer failure'
        source._emit(dict(type='button',timestamp=104,device='keyboard',code='W',down=False))
        source._flush_pending()
        self.assertFalse(source._stop.is_set())
        self.assertEqual([r for r in result if r['type']=='button'][-1]['down'],False)
        self.assertTrue(any(r['type']=='focus_error' for r in result))

    def test_review_exposes_only_sanitized_window_context(self):
        self.send('focus',1,foreground=False);self.key('keyboard','A',2);self.key('keyboard','A',3,False)
        value=self.capture.stop(duration=4)
        value['window_states'][0]['window_title']='Do not export titles'
        self.capture.path.write_text(json.dumps(value),encoding='utf-8')
        payload=input_payload(self.temp.name,dict(media=dict(duration=4)))
        self.assertEqual(payload['recording_scope'],'all')
        self.assertEqual(len(payload['intervals']),1)
        self.assertNotIn('window_title',payload['window_states'][0])
        self.assertFalse(any(g.get('type')=='focus' for g in payload['gaps']))

    def test_production_preparation_selects_complete_recording_scope(self):
        from input_capture import prepare_capture
        target=TargetWindow(1,2,3,'test')
        with patch('input_capture.capture_readiness',return_value={'ready':True}), \
             patch('input_capture_windows.resolve_target',return_value=target), \
             patch('input_capture_devices.resolve_sdl',return_value='synthetic.dll'), \
             patch('input_capture_windows.WindowsInputSource') as native:
            capture=prepare_capture({'record_inputs':True,'window':'synthetic'},self.temp.name,clock=lambda:100)
            self.assertEqual(capture.recording_scope,'all')
            capture.source_factory()
            self.assertEqual(native.call_args.kwargs,{'capture_all':True})


if __name__=='__main__':unittest.main()
