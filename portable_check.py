"""Portable runtime diagnostic; optional end-to-end test uses synthetic media only."""
import argparse
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import time
import traceback
from app_paths import installation_root


def settings_for_check(root, *, synthetic_recording=False):
    """A diagnostic must not initialize/migrate a moved portable installation."""
    root = Path(root)
    if synthetic_recording:
        from portable_config import load_settings
        return load_settings(root)
    path = root / 'config.json'
    cfg = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
    from portable_config import default_vault_path
    vault = Path(cfg.get('vault') or default_vault_path(root))
    cfg['vault'] = str(vault if vault.is_absolute() else (installation_root(root) / vault).resolve())
    return cfg


def main():
    for stream in (sys.stdout, sys.stderr):
        if stream is not None:
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--report')
    parser.add_argument('--sample', type=Path)
    parser.add_argument('--resume-session', type=Path)
    parser.add_argument('--review-test', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    destination = Path(args.report) if args.report else root / '环境自检结果.json'
    report = {'ok': False, 'root': str(root), 'python': sys.version,
              'executable': sys.executable, 'platform': platform.platform(), 'checks': {}}
    checks = report['checks']
    try:
        assert Path(sys.executable).is_relative_to(root / 'runtime'), '解释器不在整合包中'
        assert sys.flags.isolated and sys.flags.ignore_environment, 'Python 环境未隔离'
        modules = {}
        for name in ('tkinter', 'ssl', 'ctypes', 'av', 'imageio_ffmpeg', 'obsws_python',
                     'httpx', 'numpy', 'ctranslate2', 'faster_whisper', 'onnxruntime',
                     'webview', 'app', 'desktop_service', 'model_manager',
                     'qwen_transcription', 'secret_store', 'input_capture',
                     'input_capture_windows', 'input_capture_devices', 'session_metadata'):
            module = importlib.import_module(name)
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(root), f'{name} 加载了包外文件：{path}'
            modules[name] = str(path.relative_to(root))
        checks['private_imports'] = modules
        import tkinter as tk
        window = tk.Tk()
        window.withdraw()
        checks['tk'] = window.tk.call('info', 'patchlevel')
        window.destroy()
        from recorder import probe, Session, client, open_review, read, FFMPEG
        cfg = settings_for_check(root, synthetic_recording=bool(args.sample or args.resume_session))
        assert Path(FFMPEG).resolve().is_relative_to(root)
        checks['ffmpeg'] = str(Path(FFMPEG).relative_to(root))
        from media_runtime import MEDIA_EXECUTABLE, verify_media
        assert checks['ffmpeg'].replace('\\', '/') == MEDIA_EXECUTABLE, '未使用独立音视频组件'
        media = verify_media(root)
        import subprocess
        result = subprocess.run([FFMPEG, '-version'], capture_output=True, timeout=20,
                                creationflags=0x08000000 if os.name == 'nt' else 0)
        assert result.returncode == 0, '音视频组件无法启动'
        checks['media_runtime'] = {'version': media['version'], 'files': len(media['files']),
                                  'version_output': result.stdout.decode(errors='replace').splitlines()[0]}
        checks['library'] = cfg['vault']
        from model_manager import ModelManager
        checks['model_available'] = ModelManager(root).resolve_model() is not None
        checks['model_optional'] = True
        checks['record_engine'] = (root / 'tools/obs/bin/64bit/obs64.exe').is_file()
        checks['default_mode'] = cfg.get('transcription_provider', 'later')
        assert checks['record_engine'], '缺少 OBS 录制引擎'
        assert (root / 'ui/index.html').is_file(), '缺少桌面界面'
        assert (root / 'player.html').is_file(), '缺少独立回看模板'
        for asset in ('review.js', 'review.css', 'vendor/plyr/plyr.min.js', 'vendor/plyr/plyr.css', 'vendor/plyr/plyr.svg'):
            assert (root / 'ui' / asset).is_file(), '缺少回看资源：' + asset
        import ctypes
        import hashlib
        sdl_path = root / 'tools/input/SDL2.dll'
        provenance = json.loads((root / 'tools/input/provenance.json').read_text(encoding='utf-8'))
        assert hashlib.sha256(sdl_path.read_bytes()).hexdigest() == provenance['dll_sha256'], '手柄运行库校验失败'
        # Loading/querying the DLL does not initialize event listeners or record input.
        sdl = ctypes.CDLL(str(sdl_path))
        version_bytes = (ctypes.c_uint8 * 3)()
        sdl.SDL_GetVersion.argtypes = [ctypes.c_void_p]
        sdl.SDL_GetVersion.restype = None
        sdl.SDL_GetVersion(ctypes.byref(version_bytes))
        version = '.'.join(str(value) for value in version_bytes)
        assert version == provenance['version'], '手柄运行库版本不一致'
        checks['controller_runtime'] = {'path': 'tools/input/SDL2.dll', 'version': version,
                                        'sha256': provenance['dll_sha256'], 'capture_started': False}
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        kernel.GetModuleHandleW.restype = ctypes.c_void_p
        kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
        paths = {}
        for name in ('python312.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
            handle = kernel.GetModuleHandleW(name)
            assert handle, '缺少运行库：' + name
            buffer = ctypes.create_unicode_buffer(32768)
            kernel.GetModuleFileNameW(handle, buffer, len(buffer))
            path = Path(buffer.value).resolve()
            assert path.is_relative_to(root), '运行库来自包外：' + str(path)
            paths[name] = str(path.relative_to(root))
        checks['private_dlls'] = paths
        if args.sample or args.resume_session:
            from desktop_service import DesktopService
            from processing import process_isolated
            service = DesktopService(root)
            service._install_vault(cfg['vault'])
            cfg.update(game='整合版验证（合成画面与语音）', preset='省空间 720p30',
                       transcription_provider='local', model='large-v3', device='cpu', compute_type='float32')
            if args.resume_session:
                session = Session(args.resume_session)
                assert session.meta.get('test'), '仅可自动重试合成验证场次'
            else:
                assert args.sample.is_file()
                session = Session.start(cfg, args.sample.resolve())
            report['session'] = str(session.path)
            recording = not args.resume_session
            try:
                if recording:
                    client(False).trigger_media_input_action('测试素材', 'OBS_WEBSOCKET_MEDIA_INPUT_ACTION_RESTART')
                    time.sleep(min(probe(args.sample)['duration'] + 1, 30))
                    session.stop()
                    recording = False
                checks['raw'] = probe(session.path / '原始录像.mkv')
                assert checks['raw']['audio'] == 2
                process_isolated(session)
                assert session.meta['state'] == '可回看'
                transcript = read(session.path / '录像.whisper.json')
                segments = transcript['segments']
                assert segments and any(segment.get('words') for segment in segments)
                checks['transcript'] = {'segments': len(segments), 'text': ''.join(s['text'] for s in segments)}
                checks['playback'] = probe(session.path / '录像.mp4')
                checks['session_package'] = str(session.package())
                if args.review_test:
                    checks['review'] = open_review(session)
                    assert checks['review'] == 'browser-requested'
                    checks['review_notice'] = '仅请求浏览器打开，实际播放需桌面验证'
            finally:
                if recording:
                    session.stop()
        report['ok'] = True
    except Exception:
        report['error'] = traceback.format_exc()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if sys.stdout:
        print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
