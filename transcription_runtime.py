"""Local transcription settings and optional Windows GPU runtime loading."""
import ctypes
import os
import sys
from pathlib import Path

_dll_handles = []


def profile(settings):
    if settings.get('transcription_provider', 'local') == 'qwen':
        from qwen_transcription import MODEL
        return {
            'schema': 1, 'provider': 'qwen',
            'model': settings.get('qwen_model', MODEL),
            'region': settings.get('qwen_region', 'beijing'),
            'language': settings.get('language', 'zh'),
            'hotwords': settings.get('hotwords', '').strip(),
            'word_timestamps': True, 'system_reserved_filter': False,
        }
    return {
        'schema': 2,
        'model': settings.get('model', 'small'),
        'device': settings.get('device', 'cpu'),
        'compute_type': settings.get('compute_type', 'int8'),
        'language': settings.get('language', 'zh'),
        'beam_size': 5,
        'condition_on_previous_text': False,
        'word_timestamps': True,
        'vad_filter': False,
        'no_speech_threshold': 0.6,
        'hotwords': settings.get('hotwords', '').strip(),
    }


def refinement_settings(config, previous):
    result = dict(previous['settings'])
    for key in ('model', 'device', 'compute_type', 'transcription_provider', 'qwen_region', 'qwen_model'):
        if key in config:
            result[key] = config[key]
    game_settings = config.get('games', {}).get(previous['game'], {})
    for key in ('language', 'hotwords'):
        if key in game_settings:
            result[key] = game_settings[key]
    return result


def prepare_gpu_runtime():
    if os.name != 'nt' or _dll_handles:
        return
    package_root = Path(sys.prefix) / 'Lib/site-packages/nvidia'
    directories = sorted(p for p in package_root.glob('*/bin') if p.is_dir())
    if not directories:
        raise RuntimeError('本机显卡转写依赖缺失，请恢复应用的 NVIDIA 运行库。')
    for directory in directories:
        _dll_handles.append(os.add_dll_directory(str(directory)))
    # Only this worker's search path changes. Preload one consistent cuDNN release.
    os.environ['PATH'] = os.pathsep.join(map(str, directories)) + os.pathsep + os.environ.get('PATH', '')
    for name in ('cublasLt64_12.dll', 'cublas64_12.dll', 'cudnn64_9.dll'):
        library = next((p / name for p in directories if (p / name).is_file()), None)
        if library is None:
            raise RuntimeError('本机显卡转写依赖不完整：' + name)
        _dll_handles.append(ctypes.WinDLL(str(library)))
