"""Opt-in native WebView2 + OBS smoke using generated video/tone, never real devices.

Use a disposable prepared package: --app-root <package/app> --outdir <new folder>.
Creates clearly marked test media, exercises production Session and microphone
bridge, then closes only its own window and its verified owned OBS instance.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app-root', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.app_root.resolve(), args.outdir.resolve()
    if output.exists():
        parser.error('Select a new output folder; previous evidence is never overwritten.')
    if not (root / 'microphone_monitor.py').is_file():
        parser.error('The package must include the microphone monitor.')
    sys.path.insert(0, str(root))
    import recorder
    import webview
    import av
    import numpy as np
    from desktop_service import DesktopService
    from portable_config import load_settings
    assert recorder.ROOT.resolve() == root
    output.mkdir(parents=True)
    cfg = load_settings(root)
    # The supplied package must be disposable, never an installed user library.
    assert cfg.get('configured') is not True and not cfg.get('presets'), 'Use a fresh test package.'
    cfg.update(game='麦克风反馈 · 合成验证', vault=str(output / 'synthetic-library'),
               preset='省空间 720p30', record_inputs=False, transcription_provider='later')
    fixture = output / 'synthetic-tone.mkv'
    def tone(frequency, start, count):
        values = (8192 * np.sin(2 * np.pi * frequency * np.arange(start, start+count) / 48000)).astype(np.int16)
        frame = av.AudioFrame.from_ndarray(values.reshape(1, -1), format='s16', layout='mono')
        frame.sample_rate, frame.pts, frame.time_base = 48000, start, Fraction(1, 48000)
        return frame
    with av.open(str(fixture), 'w') as target:
        video, audio = target.add_stream('mpeg4', rate=30), target.add_stream('pcm_s16le', rate=48000)
        video.width, video.height, video.pix_fmt, audio.layout = 640, 360, 'yuv420p', 'mono'
        pixels = np.full((360, 640, 3), (56, 113, 90), dtype=np.uint8)
        for index in range(90):
            frame = av.VideoFrame.from_ndarray(pixels, format='rgb24')
            frame.pts, frame.time_base = index, Fraction(1, 30)
            for packet in video.encode(frame): target.mux(packet)
            for packet in audio.encode(tone(440, index * 1600, 1600)): target.mux(packet)
        for stream in (video, audio):
            for packet in stream.encode(): target.mux(packet)
    # A game-only tone verifies that it cannot light a silent narration meter.
    with av.open(str(output / '测试游戏声.wav'), 'w') as target:
        audio = target.add_stream('pcm_s16le', rate=48000)
        audio.layout = 'mono'
        for packet in audio.encode(tone(880, 0, 144000)): target.mux(packet)
        for packet in audio.encode(): target.mux(packet)
    service = DesktopService.__new__(DesktopService)
    service._lock = threading.RLock()
    service._active = None
    service._device_labels = {'mic': {'default': '合成测试音轨（未使用真实麦克风）'}}
    service._devices = {'mic': []}
    receipt = dict(synthetic=True, version=json.loads((root / 'portable.json').read_text())['version'], checks=[])

    class API:
        def get_state(self):
            session = service._active
            return dict(ok=True, data=dict(config=cfg,
                presets=[dict(id='synthetic-preset', name=cfg['game'])], active_preset_id='synthetic-preset',
                activity=dict(kind='recording' if session else 'idle', busy=False,
                    status='合成录制验证', active_id=session.meta['id'] if session else None,
                    elapsed_seconds=time.time()-session.meta['started'] if session else 0),
                readiness=dict(ready=False, checking=False, errors=[]), sessions=[],
                devices=dict(mic=[], window=[], monitor=[]), model=dict(state='missing'), capabilities={}))

        def get_microphone_state(self):
            return service.get_microphone_state()

    api = API()
    window = webview.create_window('Think Aloud · 麦克风合成验证', url=(root / 'ui/index.html').as_uri(),
        js_api=api, width=1240, height=960, background_color='#fcfaf5')
    loaded = threading.Event()
    window.events.loaded += loaded.set

    def expect(state, timeout=8):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            actual = window.evaluate_js("document.querySelector('#microphoneMonitor').dataset.state")
            if actual == state:
                data = service.get_microphone_state()['data']
                receipt['checks'].append(dict(state=state, backend=data['state'], level=data.get('level')))
                assert data['state'] == state
                return
            time.sleep(.1)
        raise AssertionError(f'Native meter did not reach {state}; last state: {actual}')

    def run():
        session = None
        try:
            assert loaded.wait(20), 'Native UI did not load'
            session = recorder.Session.start(cfg, test_file=fixture)
            service._active = session
            expect('signal')
            with recorder.obs_connection(False) as request:
                request.set_input_mute('测试素材', True)
                expect('muted')
                request.send('SetInputVolume', {'inputName': '测试素材', 'inputVolumeMul': 0})
                request.set_input_mute('测试素材', False)
                expect('quiet')
                # The threshold itself is exercised with an injected clock in
                # unit tests. Advance this synthetic monitor's quiet interval
                # instead of keeping native OBS recording for two minutes.
                with session._microphone_levels.lock:
                    session._microphone_levels.sound_at=time.monotonic()-121
                expect('silent')
                assert request.get_record_status().output_active, 'Meter warnings stopped recording'
                request.send('SetInputVolume', {'inputName': '测试素材', 'inputVolumeMul': 1})
                expect('signal')
                session.close_microphone_monitor()
                expect('unavailable')
                session.ensure_microphone_monitor(request)
                expect('signal')
            session.stop()
            service._active = None
            assert session._microphone_monitor is None
            assert (session.path / '录像.mp4').is_file()
            media = recorder.probe(session.path / '原始录像.mkv')
            assert media['audio'] == 2
            receipt.update(ok=True, two_tracks=True, video_saved=True, session=str(session.path))
        except Exception as error:
            receipt.update(ok=False, error=str(error))
        finally:
            if session is not None:
                session.close_microphone_monitor()
                if service._active is not None:
                    try:
                        session.stop()
                        service._active = None
                    except Exception as error:
                        receipt['stop_error'] = str(error)
            receipt['obs_cleanup'] = recorder.shutdown_owned_obs(root)
            (output / 'native-result.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
            window.destroy()

    threading.Thread(target=run, daemon=True).start()
    webview.settings['ALLOW_FILE_URLS'] = True
    webview.start(gui='edgechromium', private_mode=True)
    print(json.dumps(receipt, ensure_ascii=False))
    return 0 if receipt.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
