"""Synthetic microphone audio and HTTP fixtures; no cloud requests or personal media."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import httpx
import numpy as np

import recorder
from qwen_transcription import MODEL, normalize_result, transcribe
from review_runtime import ReviewAPI, review_payload
from speaker_roles import analyze_speakers, transcript_id, _solo_ranges
from transcription_runtime import profile, resume_profile


def segment(start, end, ident, text='synthetic speech'):
    return dict(start=start, end=end, speaker_id=ident, text=text,
                words=[dict(start=start, end=end, word=text)])


class SpeakerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.meta = dict(id='synthetic', game='合成说话人测试', state='可回看', test=True)
        recorder.write(self.folder/'session.json', self.meta)
        (self.folder/'录像.mp4').write_bytes(b'synthetic placeholder')

    def audio(self, spans, duration=20):
        samples = np.zeros(duration*16000, dtype=np.float64)
        for start, end, amplitude in spans:
            a, b = int(start*16000), int(end*16000)
            samples[a:b] += amplitude*np.sin(2*np.pi*220*np.arange(b-a)/16000)
        path = self.folder/'microphone.wav'
        with wave.open(str(path), 'wb') as output:
            output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            output.writeframes((samples.clip(-1, 1)*32767).astype('<i2').tobytes())
        return path

    def publish(self, segments, analysis=None):
        recorder.write(self.folder/'录像.whisper.json', dict(segments=segments, speaker_analysis=analysis))

    def test_duration_and_typical_level_choose_dominant_close_voice(self):
        parts = [segment(0, 12, 0), segment(12, 18, 1)]
        result = analyze_speakers(self.audio([(0, 12, .2), (12, 18, .025)]), parts)
        self.assertEqual(result['suggested_id'], 0)
        self.assertEqual(result['confidence'], 'recommended')
        self.assertEqual(result['speakers'][0]['speech_seconds'], 12)
        self.assertGreater(result['speakers'][0]['median_dbfs'], result['speakers'][1]['median_dbfs']+15)

    def test_short_loud_interjection_does_not_replace_regular_narrator(self):
        parts = [segment(0, 15, 0), segment(15, 15.5, 1)]
        result = analyze_speakers(self.audio([(0, 15, .1), (15, 15.5, .9)]), parts)
        self.assertEqual(result['suggested_id'], 0)

    def test_typical_level_is_not_the_loudest_spike(self):
        parts = [segment(0, 8, 0), segment(8, 16, 1)]
        result = analyze_speakers(self.audio([(0, 8, .04), (4, 4.03, .8), (8, 16, .04)]), parts)
        self.assertLess(abs(result['speakers'][0]['median_dbfs']-result['speakers'][1]['median_dbfs']), 1)
        self.assertEqual(result['confidence'], 'uncertain')

    def test_silence_and_missing_audio_never_invent_confident_speaker(self):
        parts = [segment(0, 8, 0)]
        for audio in (self.audio([]), self.folder/'missing.flac'):
            result = analyze_speakers(audio, parts)
            self.assertIsNone(result['suggested_id'])
            self.assertEqual(result['reason'], 'insufficient_audio')
            self.assertEqual(result['speakers'][0]['speaker_id'], 0)

    def test_overlaps_are_excluded_from_volume_and_pauses_from_speech_duration(self):
        self.assertEqual(_solo_ranges({0:[[0, 5]],1:[[3, 8]]}),[(0,3,0),(5,8,1)])
        parts=[segment(0,10,0)]
        parts[0]['words']=[dict(start=0,end=2),dict(start=8,end=10)]
        result=analyze_speakers(self.audio([(0,10,.2)]),parts)
        self.assertEqual(result['speakers'][0]['speech_seconds'],4)
        self.assertAlmostEqual(result['speakers'][0]['measured_seconds'],4,places=2)

    def test_old_transcripts_remain_unlabelled_and_unchanged(self):
        parts=[dict(start=0,end=5,text='old words')]
        self.publish(parts)
        before=(self.folder/'录像.whisper.json').read_bytes()
        result=review_payload(self.folder,self.meta,parts)
        self.assertEqual(result['segments'],parts)
        self.assertFalse(result['speakers']['available'])
        self.assertEqual(before,(self.folder/'录像.whisper.json').read_bytes())

    def test_manual_override_persists_reset_and_stale_transcript_rejection(self):
        parts=[segment(0,12,0),segment(12,18,1)]
        analysis=analyze_speakers(self.audio([(0,12,.2),(12,18,.02)]),parts)
        self.publish(parts,analysis)
        before=(self.folder/'录像.whisper.json').read_bytes()
        api=ReviewAPI(self.folder,{})
        revision=api.get_snapshot()['data']['revision']
        self.assertEqual(api.get_snapshot()['data']['speakers']['selected_id'],0)
        value=api.set_recorder_speaker(1,transcript_id(parts))
        self.assertTrue(value['ok'],value)
        self.assertEqual(value['data']['selected_id'],1)
        self.assertEqual(value['data']['source'],'manual')
        self.assertNotEqual(api.get_snapshot(revision)['data']['revision'],revision)
        self.assertEqual(ReviewAPI(self.folder,{}).get_snapshot()['data']['speakers']['selected_id'],1)
        self.assertEqual(api.set_recorder_speaker(None,transcript_id(parts))['data']['selected_id'],None)
        self.assertEqual(api.set_recorder_speaker(None,transcript_id(parts),True)['data']['selected_id'],0)
        self.assertFalse(api.set_recorder_speaker(999,transcript_id(parts))['ok'])
        self.assertFalse(api.set_recorder_speaker(True,transcript_id(parts))['ok'])
        self.assertEqual(before,(self.folder/'录像.whisper.json').read_bytes())
        api.set_recorder_speaker(1,transcript_id(parts))
        changed=[segment(0,12,1),segment(12,18,0)]
        self.publish(changed,analysis)
        self.assertFalse(api.set_recorder_speaker(0,transcript_id(parts))['ok'])
        self.assertIsNone(api.get_snapshot()['data']['speakers']['selected_id'])
        self.assertEqual(api.get_snapshot()['data']['speakers']['source'],'auto')

    def test_provider_ids_survive_and_missing_ids_stay_unknown(self):
        sentences=[dict(begin_time=0,end_time=2000,text='hello',speaker_id=0,
                        words=[dict(begin_time=0,end_time=2000,text='hello')]),
                   dict(begin_time=2000,end_time=3000,text='unknown',
                        words=[dict(begin_time=2000,end_time=3000,text='unknown')])]
        parts=normalize_result(dict(transcripts=[dict(channel_id=0,sentences=sentences)]),3)
        self.assertEqual(parts[0]['speaker_id'],0)
        self.assertNotIn('speaker_id',parts[1])
        self.publish(parts)
        self.assertEqual(review_payload(self.folder,self.meta,parts)['segments'][0]['speaker_id'],0)

    def test_qwen_request_enables_diarization_and_keeps_raw_result(self):
        audio=self.folder/'口述.flac';audio.write_bytes(b'synthetic HTTP fixture')
        raw=dict(properties=dict(original_duration_in_milliseconds=3000),transcripts=[dict(channel_id=0,
            sentences=[dict(begin_time=0,end_time=3000,text='合成文字',speaker_id=1,
                            words=[dict(begin_time=0,end_time=3000,text='合成文字')])])])
        calls=[]
        def request(req):
            calls.append(req)
            if req.method=='POST':
                self.assertIs(json.loads(req.content)['parameters']['diarization_enabled'],True)
                self.assertEqual(json.loads(req.content)['parameters']['channel_id'],[0])
                return httpx.Response(200,json=dict(output=dict(task_id='synthetic',task_status='PENDING')))
            if '/tasks/' in str(req.url):
                return httpx.Response(200,json=dict(output=dict(task_status='SUCCEEDED',results=[
                    dict(subtask_status='SUCCEEDED',transcription_url='https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/synthetic.json')])))
            return httpx.Response(200,json=raw)
        cache=self.folder/'cache'
        with httpx.Client(transport=httpx.MockTransport(request)) as client, patch('qwen_transcription._upload',return_value='oss://synthetic'):
            result=transcribe(audio,cache,profile(dict(transcription_provider='qwen')),3,lambda _:None,'test',client=client)
            self.assertEqual(result[0]['speaker_id'],1)
            self.assertEqual(recorder.read(cache/'云端原始结果.json'),raw)
            count=len(calls)
            self.assertEqual(transcribe(audio,cache,{},3,lambda _:None,'',client=client),result)
            self.assertEqual(len(calls),count)

    def test_upgrade_resumes_prior_task_without_new_paid_submission(self):
        cache=self.folder/'转写原始'/'previous';cache.mkdir(parents=True)
        old=dict(schema=1,provider='qwen',model=MODEL,region='beijing')
        recorder.write(cache/'配置.json',dict(options=old,audio_sha256='same-audio'))
        current=profile(dict(transcription_provider='qwen'))
        for state in ('SUBMITTING','PENDING','RUNNING','SUCCEEDED'):
            recorder.write(cache/'云端任务.json',dict(state=state,task_id='saved'))
            self.assertEqual(resume_profile(self.folder,'转写原始/previous',current,'same-audio'),old)
        with self.assertRaises(RuntimeError):
            resume_profile(self.folder,'转写原始/previous',current,'different-audio')
        recorder.write(cache/'云端原始结果.json',{})
        self.assertEqual(resume_profile(self.folder,'转写原始/previous',current,'same-audio'),current)


if __name__ == '__main__':
    unittest.main()
