"""Opt-in real FFmpeg regression with generated media; never record or upload.

The fixture encoder may be the previously accepted private FFmpeg. Processing
uses --ffmpeg and the selected application's actual Session/run implementation.
Choose a fresh output directory; all fixtures, logs and failure evidence remain.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import time
import traceback
import wave
from unittest.mock import patch


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg',required=True,type=Path)
    parser.add_argument('--fixture-ffmpeg',required=True,type=Path)
    parser.add_argument('--app-root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--require-selected-cli',action='store_true',
                        help='Require the app resolver to select --ffmpeg without an override')
    parser.add_argument('--outdir',required=True,type=Path)
    args=parser.parse_args(argv)
    root=args.app_root.resolve();out=args.outdir.resolve()
    for exe in (args.ffmpeg,args.fixture_ffmpeg):
        if not exe.is_file():parser.error('Missing executable: '+str(exe))
    out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(root))
    import av
    import numpy as np
    import recorder
    assert Path(recorder.__file__).resolve().parent==root
    selected = Path(recorder.FFMPEG).resolve() == args.ffmpeg.resolve()
    if args.require_selected_cli and not selected:
        raise AssertionError('Application did not select the supplied media runtime')
    report={'scope':'Real synthetic media processing through the selected application; no OBS, microphone capture, cloud request or model inference.',
            'application_root':str(root),'ffmpeg':str(args.ffmpeg.resolve()),
            'fixture_encoder':str(args.fixture_ffmpeg.resolve()),'application_selected_cli':selected,
            'checks':[],'passed':False}

    def digest(path):
        h=hashlib.sha256()
        with Path(path).open('rb') as stream:
            for chunk in iter(lambda:stream.read(1024**2),b''):h.update(chunk)
        return h.hexdigest()

    def save():
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def record(name,**details):
        report['checks'].append({'name':name,'passed':True,**details});save();print(name,flush=True)

    def command(exe,arguments,name,timeout=90):
        with (out/(name+'.log')).open('wb') as log:
            process=subprocess.Popen([str(exe),'-nostdin','-hide_banner','-y',*map(str,arguments)],
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                creationflags=0x08000000 if sys.platform=='win32' else 0)
            # On timeout retain the process and evidence; never kill a worker.
            if process.wait(timeout=timeout):raise RuntimeError('Media command failed: '+name)

    def write_wav(path,samples,rate):
        with wave.open(str(path),'wb') as stream:
            stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(rate)
            stream.writeframes(samples.astype('<i2').tobytes())

    def read_wav(path):
        with wave.open(str(path),'rb') as stream:
            assert stream.getnchannels()==1 and stream.getsampwidth()==2
            return np.frombuffer(stream.readframes(stream.getnframes()),dtype='<i2').copy(),stream.getframerate()

    def audio(path,index=0):
        values=[]
        with av.open(str(path)) as container:
            selected=container.streams.audio[index]
            rate=selected.codec_context.sample_rate
            converter=av.AudioResampler(format='s16',layout='mono',rate=rate)
            for frame in container.decode(selected):
                values.extend(result.to_ndarray().reshape(-1) for result in converter.resample(frame))
            values.extend(result.to_ndarray().reshape(-1) for result in converter.resample(None))
        return np.concatenate(values),rate

    def packets(path):
        with av.open(str(path)) as container:
            kinds=[s.type for s in container.streams]
            hashes=[hashlib.sha256() for _ in kinds]
            for packet in container.demux():
                if packet.size:hashes[packet.stream.index].update(bytes(packet))
            return kinds,[h.hexdigest() for h in hashes]

    def energy(samples,rate,frequency):
        segment=samples[int(3*rate):int(4*rate)].astype(float)
        times=np.arange(len(segment))/rate
        return float(abs(np.dot(segment,np.exp(-2j*np.pi*frequency*times)))/len(segment))

    def session(folder):
        recorder.write(folder/'session.json',{'id':folder.name,'game':'Synthetic media regression',
            'test':True,'created':'2026-09-23T00:00:00+08:00','state':'待整理',
            'settings':{'transcription_provider':'qwen','qwen_region':'beijing','qwen_model':'qwen3-asr-flash-filetrans','language':'zh','hotwords':''}})
        return recorder.Session(folder)

    try:
        report['ffmpeg_sha256']=digest(args.ffmpeg)
        # Independent, distinguishable tones expose a wrong track selection.
        rate=48000;duration=7.;times=np.arange(int(rate*duration))/rate
        mic=(np.sin(2*np.pi*880*times)*4000*((times>=.75)&(times<4.75))).astype(np.int16)
        game=(np.sin(2*np.pi*220*times)*4000).astype(np.int16)
        mixed=(game.astype(np.int32)+mic).astype(np.int16)
        write_wav(out/'mic.wav',mic,rate);write_wav(out/'mixed.wav',mixed,rate)
        write_wav(out/'silent.wav',np.zeros_like(mic),rate)
        (out/'cue.srt').write_text('1\n00:00:01,000 --> 00:00:02,000\nSynthetic subtitle stream\n',encoding='utf-8')

        def make_fixture(folder,silent=False,live=False):
            folder.mkdir()
            arguments=['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=7',
                '-i',out/'mixed.wav','-itsoffset','1.25','-i',out/('silent.wav' if silent else 'mic.wav'),
                '-i',out/'cue.srt','-map','0:v:0','-map','1:a:0','-map','2:a:0','-map','3:s:0',
                '-c:v','libx264','-preset','ultrafast','-threads','1','-pix_fmt','yuv420p',
                '-c:a','aac','-b:a','192k','-c:s','srt','-t','7']
            if live:arguments+=['-live','1']
            command(args.fixture_ffmpeg,[*arguments,folder/'原始录像.mkv'],folder.name+'-fixture')

        folder=out/'normal';make_fixture(folder)
        raw=folder/'原始录像.mkv';raw_hash=digest(raw)
        with patch.object(recorder,'FFMPEG',str(args.ffmpeg.resolve())):
            current=session(folder);current.adopt_recording();current.prepare_video()
            recorder.run(['-i',raw,'-map','0:a:1','-af','aresample=16000:async=1:first_pts=0',
                '-ac','1','-c:a','flac',folder/'口述.flac'],folder/'process.log')
            voice,voice_rate=audio(folder/'口述.flac')
            playback,play_rate=audio(folder/'录像.mp4')
            assert voice_rate==16000 and len(voice)/voice_rate>6.9
            assert np.max(np.abs(voice[:int(1.7*voice_rate)].astype(np.int32)))<8
            assert energy(voice,voice_rate,880)>500
            assert energy(voice,voice_rate,220)<energy(voice,voice_rate,880)*.01
            assert energy(playback,play_rate,220)>500 and energy(playback,play_rate,880)>500
            assert digest(raw)==raw_hash
            kinds,encoded=packets(raw);video_kinds,video_encoded=packets(folder/'录像.mp4')
            assert video_kinds==['video','audio']
            assert video_encoded==[encoded[kinds.index('video')],encoded[kinds.index('audio')]]
            record('playback remux retains original video and mixed audio packets; only microphone is extracted',
                   sample_rate=voice_rate,voice_duration=len(voice)/voice_rate,video=current.meta['media'])
            record('asynchronous resampling pads microphone start to video zero and preserves silent timing')

            interrupted=out/'interrupted';make_fixture(interrupted,live=True)
            original=interrupted/'原始录像.mkv';before=digest(original)
            info=recorder.probe(original)
            assert info['duration']<=0,'Fixture must have no duration metadata to exercise real recovery'
            recovered=session(interrupted);recovered.adopt_recording()
            assert recovered.meta['processing_source']=='恢复录像.mkv'
            assert packets(original)==packets(interrupted/'恢复录像.mkv')
            recovered.prepare_video()
            assert digest(original)==before
            record('duration-less MKV recovery preserves every encoded stream and leaves original bytes intact',
                   stream_types=packets(original)[0])

            silent=out/'silent';make_fixture(silent,silent=True)
            silent_session=session(silent)
            # Any unintended cloud or model request is a test failure.
            with patch('qwen_transcription.transcribe',side_effect=AssertionError('Unexpected upload')), \
                 patch('secret_store.load_key',side_effect=AssertionError('Unexpected credential read')):
                silent_session.process()
            assert silent_session.meta['state']=='可回看'
            assert silent_session.meta['audio_check']['digital_silence'] is True
            assert recorder.read(silent/'录像.whisper.json')['segments']==[]
            assert (silent/'独立回看.html').is_file()
            record('silent microphone completes production processing and review generation without cloud or model access')

            long_rate=16000;long_samples=np.zeros(int(1201.2*long_rate),dtype=np.int16)
            for start,end,freq in ((.2,.5,400),(599.8,600.2,500),(1199.9,1200.3,700)):
                a,b=round(start*long_rate),round(end*long_rate)
                long_samples[a:b]=(np.sin(2*np.pi*freq*np.arange(b-a)/long_rate)*6000).astype(np.int16)
            write_wav(out/'long.wav',long_samples,long_rate)
            recorder.run(['-i',out/'long.wav','-c:a','flac',out/'long.flac'],out/'long.log')
            chunks=[]
            for offset in (0,600,1200):
                target=out/('chunk-'+str(offset)+'.wav')
                recorder.run(['-ss',str(offset),'-i',out/'long.flac','-t','600','-ar','16000','-ac','1',target],out/'long.log')
                samples,sample_rate=read_wav(target)
                expected=long_samples[offset*long_rate:(offset+600)*long_rate]
                assert sample_rate==long_rate and np.array_equal(samples,expected),offset
                chunks.append({'offset':offset,'samples':len(samples),'seconds':len(samples)/sample_rate})
            record('600-second FLAC-to-WAV segmentation preserves exact samples at both boundaries',chunks=chunks)
        report['passed']=True;save()
    except BaseException:
        report['error']=traceback.format_exc();save();raise
    print(json.dumps({'passed':True,'checks':len(report['checks']),'report':str(out/'report.json')}),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
