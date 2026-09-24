"""First-run setup for the self-contained Windows edition; no network required."""
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import time
import uuid
from copy import deepcopy
from app_paths import installation_root


def _read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        for attempt in range(40):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(.05)
    finally:
        temporary.unlink(missing_ok=True)


def machine_identity():
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Cryptography',
                       0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        machine = winreg.QueryValueEx(key, 'MachineGuid')[0]
    return hashlib.sha256((machine + '|' + getpass.getuser()).encode()).hexdigest()


def _free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _setup_obs(root, cfg):
    obs = root / 'tools/obs/config/obs-studio'
    _write(obs / 'plugin_config/obs-websocket/config.json', {
        'server_enabled': True, 'server_port': cfg['port'], 'auth_required': True,
        'server_password': cfg['password'], 'alerts_enabled': False, 'first_load': False,
    })
    basic = ('[General]\nFirstRun=false\nLastVersion=536870912\n\n'
             '[Basic]\nProfile=Experience\nProfileDir=Experience\n'
             'SceneCollection=Experience\nSceneCollectionFile=Experience\n\n'
             '[BasicWindow]\nWarnBeforeStartingStream=true\n')
    (obs / 'global.ini').write_text(basic, encoding='utf-8')
    (obs / 'user.ini').write_text(basic, encoding='utf-8')
    profile = obs / 'basic/profiles/Experience'
    profile.mkdir(parents=True, exist_ok=True)
    (profile / 'basic.ini').write_text(
        '[General]\nName=Experience\n\n[Video]\nBaseCX=1920\nBaseCY=1080\n'
        'OutputCX=1920\nOutputCY=1080\nFPSType=0\nFPSCommon=30\n\n'
        '[Output]\nMode=Advanced\nFilenameFormatting=%CCYY-%MM-%DD_%hh-%mm-%ss\n\n'
        '[AdvOut]\nRecType=Standard\nRecFormat2=mkv\nRecEncoder=obs_x264\nRecTracks=3\n'
        'RecAudioEncoder=ffmpeg_aac\nTrack1Bitrate=192\nTrack2Bitrate=160\n'
        'RecFilePath=' + str(root / 'staging') + '\n\n'
        '[Audio]\nSampleRate=48000\nChannelSetup=Stereo\n', encoding='utf-8')
    _write(profile / 'recordEncoder.json', {
        'rate_control': 'CRF', 'crf': 20, 'preset': 'veryfast', 'profile': 'high',
    })
    _write(obs / 'basic/scenes/Experience.json', {
        'name': 'Experience', 'current_scene': 'Experience', 'current_program_scene': 'Experience',
        'scene_order': [{'name': 'Experience'}],
        'sources': [{'name': 'Experience', 'id': 'scene', 'settings': {'items': []}}],
    })
    (root / 'staging').mkdir(exist_ok=True)


def stored_settings(root, cfg):
    """Keep an in-folder library relative even after the settings dialog saves it."""
    root = Path(root).resolve()
    result = deepcopy(cfg)
    if (root / 'portable.json').is_file():
        for settings in _recording_settings(result):
            if settings.get('vault'):
                vault = Path(settings['vault'])
                if vault.is_absolute():
                    try:
                        settings['vault'] = vault.resolve().relative_to(installation_root(root)).as_posix()
                    except ValueError:
                        pass
    return result


def _recording_settings(cfg):
    yield cfg
    presets = cfg.get('presets', {})
    if isinstance(presets, dict):
        yield from (value for value in presets.values() if isinstance(value, dict))


def default_vault_path(root):
    """Sibling database survives replacing/versioning the application folder."""
    return installation_root(root).parent / 'think-aloud-database'


def initialize(root, identity=None):
    root = Path(root).resolve()
    if not (root / 'portable.json').is_file():
        return
    # An independent lock also protects setup by the diagnostic and worker entries.
    import msvcrt
    with (root / '.portable-setup.lock').open('a+b') as lock:
        for attempt in range(100):
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if attempt == 99:
                    raise RuntimeError('另一个记录器正在准备便携环境，请稍后重试。')
                time.sleep(.1)
        try:
            _initialize_locked(root, identity or machine_identity())
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def _initialize_locked(root, identity):
    path = root / 'config.json'
    cfg = _read(path) if path.is_file() else {
        'vault': str(default_vault_path(root)), 'language': 'zh', 'preset': '均衡 1080p30',
        'source': '游戏窗口', 'window': '', 'monitor': '', 'mic': 'default',
        'game': '自由探索', 'model': 'large-v3', 'device': 'cpu',
        'compute_type': 'float32', 'transcription_provider': 'later',
        'hotwords': '', 'configured': False, 'games': {}, 'record_inputs': False,
    }
    previous_root = cfg.get('_portable_root')
    changed_machine = cfg.get('_portable_machine') != identity
    install = installation_root(root)
    moved = previous_root != str(install)
    if not changed_machine and not moved:
        return
    if previous_root:
        for settings in _recording_settings(cfg):
            if settings.get('vault') and Path(settings['vault']).is_absolute():
                try:
                    settings['vault'] = Path(settings['vault']).relative_to(previous_root).as_posix()
                except ValueError:
                    pass
    if changed_machine:
        for settings in _recording_settings(cfg):
            settings.update(configured=False, window='', monitor='', mic='default')
        cfg.update(device='cpu', compute_type='float32')
        for preset in cfg.get('games', {}).values():
            preset.update(window='', monitor='', mic='default')
    # Each new location owns its OBS connection; it cannot control an old copy.
    cfg.update(port=_free_port(), password=secrets.token_urlsafe(24),
               _portable_root=str(install), _portable_machine=identity)
    _setup_obs(root, cfg)
    _write(path, stored_settings(root, cfg))


def load_settings(root):
    root = Path(root)
    initialize(root)
    cfg = _read(root / 'config.json')
    if (root / 'portable.json').is_file():
        for settings in _recording_settings(cfg):
            if settings.get('vault') and not Path(settings['vault']).is_absolute():
                settings['vault'] = str((installation_root(root) / settings['vault']).resolve())
    return cfg
