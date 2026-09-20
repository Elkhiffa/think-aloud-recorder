"""Thread-safe desktop bridge. Only native capture/worker acknowledgements are success.

The service never accepts arbitrary session paths, returns credentials, or starts
capture with a synthetic source. UI polling is read-only; a single admitted job
owns recorder mutations, including periodic health checks.
"""
from copy import deepcopy
from pathlib import Path
import os
import re
import shutil
import threading
import time
import webbrowser
import tempfile
import uuid
from obsws_python.error import OBSSDKError
from websocket import WebSocketException

import recorder
from hotword_files import (merge_files, split_words, validate_words, compile_hotword_snapshots,
                           read_dictionary_snapshots, SOGOU_DICTIONARIES)
from model_manager import ModelManager
from portable_config import load_settings, stored_settings
from processing import process_isolated
import secret_store


PUBLIC_KEYS = ('game', 'vault', 'preset', 'source', 'window', 'monitor', 'mic',
               'language', 'hotwords', 'hotword_files', 'hotword_manual',
               'transcription_provider', 'obsidian_exe', 'configured')
EDITABLE_KEYS = set(PUBLIC_KEYS) - {'configured'}
PRESET_KEYS = ('preset', 'source', 'window', 'monitor', 'mic', 'language', 'hotwords',
               'hotword_files', 'hotword_manual')
SUSPECT_STATES = {'录制中', '启动中', '保存中'}
READINESS_MAX_AGE = 15


def ok(data=None):
    return {'ok': True, 'data': data}


class DesktopService:
    def __init__(self, root=None):
        self.root = Path(root or recorder.ROOT).resolve()
        self._lock = threading.RLock()
        self._operation_lock = threading.RLock()
        self._readiness_thread = None
        self._dialog_open = False
        self._startup_launch_attempted = False
        self._window = None
        self._job = None
        self._active = None
        self._uncertain_ids = set()
        self._obs_uncertain = False
        self._closed = threading.Event()
        self._devices = {'mic': [], 'window': [], 'monitor': []}
        self._device_labels = {'mic': {}, 'window': {}, 'monitor': {}}
        self._readiness = dict(ready=False, checking=True, errors=[], checked_at=None)
        self._cfg = load_settings(self.root)
        self._cfg.setdefault('transcription_provider', 'later')
        self._cfg.setdefault('obsidian_exe', '')
        self._initialize_presets()
        self._model = ModelManager(self.root)
        self._activity = dict(busy=False, kind='idle', status='待开始', detail='',
                              active_id=None, elapsed_seconds=0)
        self._launch('devices', self._startup, status='检查上次场次')
        self._monitor = threading.Thread(target=self._monitor_loop, daemon=True,
                                         name='recording-health')
        self._monitor.start()

    def set_window(self, window):
        self._window = window
        return ok()

    def _safe_text(self, value):
        text = str(value or '')
        password = self._cfg.get('password')
        if password:
            text = text.replace(str(password), '[已隐藏]')
        port = self._cfg.get('port')
        if port:
            text = re.sub(r'(?<!\d)' + re.escape(str(port)) + r'(?!\d)', '[端口已隐藏]', text)
        # Cloud exceptions can contain headers or signed upload URLs. Neither is
        # useful in a desktop snapshot. Credentials themselves are never cached.
        text = re.sub(r'(?i)\b(?:sk|dsk)-[\w-]+', '[已隐藏]', text)
        text = re.sub(r'(?i)(authorization|api[_ -]?key|password|token)\s*[:=]\s*\S+', r'\1=[已隐藏]', text)
        text = re.sub(r'https?://\S+\?\S+', '[临时链接已隐藏]', text)
        return text[:3000]

    def _error(self, error):
        return {'ok': False, 'error': self._safe_text(error)}

    def _progress(self, text, *, status=None):
        with self._lock:
            self._activity['detail'] = self._safe_text(text)
            if status:
                self._activity['status'] = status

    def _guard(self, allow_active=False, allow_uncertain=False):
        if self._closed.is_set():
            raise RuntimeError('应用正在关闭。')
        if self._activity['busy']:
            raise RuntimeError('当前操作尚未结束，请稍候。')
        if self._dialog_open:
            raise RuntimeError('请先完成当前文件选择。')
        if self._active is not None and not allow_active:
            raise RuntimeError('当前场次仍在录制或等待确认停止，请先结束录制。')
        if (self._uncertain_ids or self._obs_uncertain) and not allow_uncertain and not allow_active:
            raise RuntimeError('上次录制状态尚未确认。请先刷新设备重新连接 OBS，避免覆盖仍在进行的录制。')

    def _launch(self, kind, operation, *, status=None, allow_active=False, allow_uncertain=False):
        with self._lock:
            try:
                self._guard(allow_active, allow_uncertain)
            except Exception as error:
                return self._error(error)
            self._activity.update(busy=True, kind=kind, status=status or '处理中', detail='')
            self._readiness.update(ready=False)

            def work():
                try:
                    with self._operation_lock:
                        operation()
                except Exception as error:
                    self._progress(error, status='操作未完成')
                finally:
                    with self._lock:
                        self._activity['busy'] = False
                        self._activity['kind'] = 'recording' if self._active else 'idle'
                        self._activity['active_id'] = self._active.meta['id'] if self._active else None
                        if self._active is not None:
                            self._readiness.update(ready=False, checking=False)

            self._job = threading.Thread(target=work, daemon=True, name='desktop-' + kind)
            self._job.start()
            return ok({'started': True})

    def _public_config(self):
        result = {key: deepcopy(self._cfg.get(key, '')) for key in PUBLIC_KEYS}
        result['vault'] = str(Path(self._cfg['vault']).resolve())
        result['configured'] = bool(self._cfg.get('configured'))
        result['games'] = {
            name: {key: deepcopy(values[key]) for key in PRESET_KEYS if key in values}
            for name, values in self._cfg.get('games', {}).items()
            if isinstance(name, str) and isinstance(values, dict)
        }
        return result

    def _initialize_presets(self):
        self._normalize_hotword_config(self._cfg)
        migrated = 'presets' not in self._cfg
        if migrated:
            self._cfg['presets'] = {}
            self._cfg['active_preset_id'] = None
            if self._cfg.get('configured'):
                self._cfg['presets']['legacy'] = self._preset_snapshot(self._cfg)
                self._cfg['active_preset_id'] = 'legacy'
        for value in self._cfg['presets'].values():
            self._normalize_hotword_config(value)
            if value.get('vault') and not Path(value['vault']).is_absolute():
                value['vault'] = str((self.root / value['vault']).resolve())
        ident = self._cfg.get('active_preset_id')
        selected = self._cfg['presets'].get(ident)
        if selected:
            self._cfg.update({key: deepcopy(selected[key]) for key in PUBLIC_KEYS if key in selected})
        else:
            self._cfg['active_preset_id'] = None
            self._cfg['configured'] = False
        if migrated and (self.root / 'config.json').exists():
            self._persist(self._cfg)

    @staticmethod
    def _normalize_hotword_config(cfg):
        if 'hotword_files' not in cfg and 'hotword_manual' not in cfg:
            files, manual = [], cfg.get('hotwords', '')
        else:
            files, manual = cfg.get('hotword_files', []), cfg.get('hotword_manual', '')
        # Loading old presets does not newly reject them under provider-specific
        # limits; selecting/saving a provider performs that validation below.
        cfg.update(compile_hotword_snapshots(files, manual, qwen=False))

    @staticmethod
    def _preset_snapshot(cfg):
        return {**{key: deepcopy(cfg.get(key, '')) for key in PUBLIC_KEYS},
                'name': cfg.get('game') or '自由探索'}

    def _persist(self, cfg):
        stored = stored_settings(self.root, deepcopy(cfg))
        if (self.root / 'portable.json').is_file():
            for preset in stored.get('presets', {}).values():
                try:
                    preset['vault'] = Path(preset['vault']).resolve().relative_to(self.root).as_posix()
                except (KeyError, ValueError):
                    pass
        recorder.write(self.root / 'config.json', stored)

    def _preset_list(self):
        return [dict(id=ident, name=value.get('name', value.get('game', '')),
                     vault=value.get('vault', '')) for ident, value in self._cfg.get('presets', {}).items()]

    def _session_paths(self):
        vault = Path(self._cfg['vault']).resolve()
        base = vault / '场次'
        result = {}
        if base.resolve().parent != vault:
            return result
        for file in base.glob('*/session.json'):
            try:
                directory = file.parent.resolve()
                if directory.parent != base.resolve() or file.resolve().parent != directory:
                    continue
                meta = recorder.read(file)
                if not isinstance(meta, dict):
                    continue
                ident = meta.get('id')
                if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', ident):
                    continue
                if ident in result:
                    # Ambiguous IDs must not choose a different session by chance.
                    result[ident] = None
                else:
                    result[ident] = directory
            except (OSError, ValueError, TypeError):
                continue
        return {ident: path for ident, path in result.items() if path is not None}

    def _session(self, ident):
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', ident):
            raise ValueError('请从当前资料库选择有效场次。')
        path = self._session_paths().get(ident)
        if path is None:
            raise ValueError('场次不存在、编号重复或不属于当前资料库。')
        return recorder.Session(path)

    @staticmethod
    def _contained_file(session, name):
        file = (session.path / name).resolve()
        if not file.is_relative_to(session.path.resolve()) or not file.is_file():
            raise ValueError('场次文件不存在或不属于此场次。')
        return file

    def get_state(self):
        try:
            with self._lock:
                sessions = []
                for ident, path in self._session_paths().items():
                    try:
                        meta = recorder.read(path / 'session.json')
                        media = meta.get('media', {})
                        if not isinstance(media, dict):
                            media = {}
                        sessions.append(dict(id=ident, game=meta.get('game', ''),
                                             created=meta.get('created', ''), state=meta.get('state', ''),
                                             duration=media.get('duration', 0),
                                             segments=meta.get('segments', 0),
                                             warning=self._safe_text(meta.get('warning')),
                                             error=self._safe_text(meta.get('error')),
                                             path=str(path), test=bool(meta.get('test'))))
                    except (OSError, ValueError, TypeError):
                        continue
                sessions.sort(key=lambda item: item['created'], reverse=True)
                activity = dict(self._activity)
                if self._active:
                    activity['active_id'] = self._active.meta['id']
                    activity['elapsed_seconds'] = max(0, time.time() - self._active.meta.get('started', time.time()))
                else:
                    activity['elapsed_seconds'] = 0
                model = self._model.status()
                model = {key: model.get(key) for key in ('state', 'model', 'path', 'downloaded_bytes',
                         'total_bytes', 'error', 'source', 'revision')}
                model['error'] = self._safe_text(model.get('error'))
                return ok(dict(config=self._public_config(), sessions=sessions,
                               readiness=self._visible_readiness(),
                               presets=self._preset_list(), active_preset_id=self._cfg.get('active_preset_id'),
                               activity=activity, devices=deepcopy(self._devices), model=model,
                               capabilities=dict(cloud_key=self._has_key(),
                                   obsidian=self._obsidian_available(),
                                   obs=(self.root / 'tools/obs/bin/64bit/obs64.exe').is_file(),
                                   local_model=model['state'] == 'ready')))
        except Exception as error:
            return self._error(error)

    def _has_key(self):
        return secret_store.has_key(directory=self.root / 'state/secrets')

    def _startup(self):
        self._recover()
        with self._lock:
            initialize = (not self._startup_launch_attempted and self._cfg.get('configured')
                          and self._cfg.get('active_preset_id') and self._active is None
                          and not self._obs_uncertain and not self._uncertain_ids
                          and (self.root / 'tools/obs/bin/64bit/obs64.exe').is_file())
            if initialize:
                self._startup_launch_attempted = True
        if initialize:
            try:
                # The existing client connects before considering a launch and
                # never launches another instance after a readiness failure.
                client = recorder.client(launch=True, progress=self._progress)
                client.disconnect()
            except Exception:
                # The following actual probe supplies the actionable readiness
                # error. Routine checks never repeat this automatic launch.
                pass
        readiness = self._update_readiness()
        with self._lock:
            if initialize and readiness['ready'] and self._activity['status'] == '待开始':
                self._activity['detail'] = ''

    def _readiness_is_fresh(self):
        checked = self._readiness.get('checked_at')
        return (self._readiness.get('ready') is True and isinstance(checked, (int, float))
                and 0 <= time.time() - checked <= READINESS_MAX_AGE)

    def _visible_readiness(self):
        result = deepcopy(self._readiness)
        if result['ready'] and not self._readiness_is_fresh():
            result['ready'] = False
            result['checking'] = bool(self._readiness_thread and self._readiness_thread.is_alive())
            result['errors'] = [*result['errors'], dict(code='READINESS_STALE', step=1,
                message='录制条件检查结果已过期，请等待重新确认或点击“重新检查”。')]
        return result

    def _mark_readiness_checking(self, invalidate):
        if invalidate or not self._readiness_is_fresh():
            self._readiness.update(ready=False, checking=True)
        # A routine refresh keeps a fresh verified success usable. Its worker is
        # still tracked independently; Start always performs another full check.

    def _cache_devices(self, devices):
        with self._lock:
            self._devices = {key: [{field: item.get(field) for field in ('itemName', 'itemValue', 'itemEnabled')}
                                  for item in devices.get(key, [])] for key in self._devices}
            for key, items in self._devices.items():
                for item in items:
                    self._device_labels[key][str(item.get('itemValue'))] = str(item.get('itemName', ''))

    def _device_label(self, kind, value):
        name = self._device_labels[kind].get(str(value))
        if name:
            return name
        if kind == 'window':
            parts = str(value).split(':')
            title = parts[0].replace('#3A', ':').replace('#22', '"')
            executable = parts[-1] if len(parts) > 1 else ''
            return title + (f'（{executable}）' if executable else '')
        return str(value or '尚未选择')

    def _probe_obs_devices(self):
        """Read actual OBS properties; disabled temporary sources exist only idle.

        Never switch profiles/collections, configure capture, or stop outputs.
        Service jobs hold the same operation lock, so Start cannot interleave.
        """
        client = recorder.client(False)
        temporary = []
        try:
            if client.get_record_status().output_active or client.get_stream_status().output_active:
                return None, ('OBS_BUSY', 'OBS 正在录制或推流，请先结束已有输出。')
            if (client.get_profile_list().current_profile_name != 'Experience'
                    or client.get_scene_collection_list().current_scene_collection_name != 'Experience'):
                return None, ('OBS_CONFIGURATION', 'OBS 当前不是记录器专用配置，请使用“重新检查”恢复设备列表。')
            inputs = client.get_input_list().inputs
            result = {}
            for key, kind, prop, settings in (
                ('mic', 'wasapi_input_capture', 'device_id', {'device_id': 'default'}),
                ('window', 'window_capture', 'window', {}),
                ('monitor', 'monitor_capture', 'monitor_id', {}),
            ):
                name = next((item['inputName'] for item in inputs if item.get('inputKind') == kind), None)
                if name is None:
                    # Check again before any temporary input creation. No source
                    # is added when a user has started an output in OBS itself.
                    if client.get_record_status().output_active or client.get_stream_status().output_active:
                        return None, ('OBS_BUSY', 'OBS 正在录制或推流，请先结束已有输出。')
                    name = '就绪检查-' + key + '-' + uuid.uuid4().hex
                    client.create_input('Experience', name, kind, settings, False)
                    temporary.append(name)
                result[key] = client.get_input_properties_list_property_items(name, prop).property_items
            return result, None
        finally:
            for name in reversed(temporary):
                try:
                    client.remove_input(name)
                except Exception:
                    pass
            try:
                client.disconnect()
            except Exception:
                pass

    def _probe_location(self, vault):
        path = Path(self._validate_vault(vault))
        if not path.is_dir():
            raise OSError('保存目录不存在。')
        # An actual create/write/flush proves ACL access; os.access on Windows
        # alone does not. Only this disposable probe is removed on close.
        with tempfile.TemporaryFile(dir=path, prefix='.recorder-readiness-') as probe:
            probe.write(b'1')
            probe.flush()
            os.fsync(probe.fileno())
        return shutil.disk_usage(path).free

    def _update_readiness(self, *, devices=None, invalidate=True):
        """Called only while holding the operation lock; never under snapshot I/O lock."""
        with self._lock:
            cfg = deepcopy(self._cfg)
            has_setup = bool(cfg.get('configured') and cfg.get('active_preset_id'))
            blocked = self._active is not None or self._obs_uncertain or bool(self._uncertain_ids)
            self._mark_readiness_checking(invalidate or blocked)
        errors = []
        def error(code, message, step):
            errors.append(dict(code=code, message=self._safe_text(message), step=step))
        try:
            if blocked:
                error('RECORDING_UNCONFIRMED', '当前录制尚未结束或归属未确认，请先结束录制。', 1)
            if not has_setup:
                error('SETUP_REQUIRED', '请先完成并保存录制设置。', 1)
            obs_file = self.root / 'tools/obs/bin/64bit/obs64.exe'
            if not obs_file.is_file():
                error('OBS_MISSING', '录制引擎文件缺失，请恢复完整应用文件夹。', 1)
            elif not blocked:
                try:
                    if devices is None:
                        devices, problem = self._probe_obs_devices()
                        if problem:
                            error(problem[0], problem[1], 1)
                    if devices is not None:
                        self._cache_devices(devices)
                        source = 'window' if cfg.get('source') == '游戏窗口' else 'monitor'
                        for key in (source, 'mic'):
                            value = cfg.get(key)
                            available = any(str(item.get('itemValue')) == str(value) and item.get('itemEnabled', False)
                                            for item in devices.get(key, []))
                            if not value or not available:
                                label = self._device_label(key, value)
                                if key == 'mic':
                                    error('MIC_UNAVAILABLE', f'麦克风“{label}”未连接或不可用，请重新连接或选择麦克风。', 1)
                                elif key == 'window':
                                    error('WINDOW_UNAVAILABLE', f'游戏窗口“{label}”未打开或已关闭，请先打开该窗口。', 1)
                                else:
                                    error('MONITOR_UNAVAILABLE', f'显示器“{label}”未连接或不可用。', 1)
                except Exception:
                    error('OBS_UNAVAILABLE', '无法连接录制引擎。请使用“重新检查”启动或重新连接 OBS。', 1)
            provider = cfg.get('transcription_provider', 'later')
            if provider == 'local' and not self._model.resolve_model():
                error('LOCAL_MODEL_MISSING', '已选本地转写，但模型缺失、已移动或校验失效；请导入/下载模型，或改为仅录制。', 2)
            elif provider == 'qwen' and not self._has_key():
                exists = (self.root / 'state/secrets/dashscope-beijing.dpapi').exists()
                error('CLOUD_KEY_UNREADABLE' if exists else 'CLOUD_KEY_MISSING',
                      '本机保存的云端密钥无法读取或解密，请重新填写密钥。' if exists else '已选云端转写，但尚未保存本机 API Key。', 2)
            elif provider not in ('later', 'local', 'qwen'):
                error('TRANSCRIPTION_INVALID', '请选择有效转写方式并保存设置。', 2)
            try:
                free = self._probe_location(cfg.get('vault', ''))
                if free < 5 * 1024 ** 3:
                    error('OUTPUT_SPACE_LOW', f'保存位置剩余 {free / 1024 ** 3:.1f} GB，不足录制所需的 5 GB。', 3)
            except Exception:
                error('OUTPUT_UNAVAILABLE', '保存位置无法访问或写入，请连接保存磁盘，或重新选择可写文件夹。', 3)
        except Exception:
            error('READINESS_FAILED', '录制条件检查未完成，请重新检查后再开始。', 1)
        if not has_setup:
            # Onboarding has one actionable next step. Device probing above still
            # populates the wizard, but absent selections are not user errors yet.
            errors = [dict(code='SETUP_REQUIRED', message='请先完成并保存录制设置。', step=1)]
        with self._lock:
            self._readiness = dict(ready=not errors, checking=False, errors=errors, checked_at=time.time())
            return deepcopy(self._readiness)

    def _request_readiness(self, *, invalidate=False):
        with self._lock:
            if (self._closed.is_set() or self._active is not None or self._activity['busy']
                    or (self._readiness_thread and self._readiness_thread.is_alive())):
                return False
            self._mark_readiness_checking(invalidate)
            def work():
                with self._operation_lock:
                    with self._lock:
                        if self._closed.is_set() or self._active is not None or self._activity['busy']:
                            self._readiness.update(ready=False, checking=False)
                            return
                    self._update_readiness(invalidate=invalidate)
            self._readiness_thread = threading.Thread(target=work, daemon=True, name='idle-readiness')
            self._readiness_thread.start()
            return True

    def _obsidian_available(self):
        from review_runtime import find_obsidian
        return find_obsidian(self._cfg.get('obsidian_exe')) is not None

    def _validate_vault(self, value):
        if not isinstance(value, str) or not value.strip() or '\x00' in value:
            raise ValueError('请选择资料库的绝对路径。')
        path = Path(value)
        if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
            raise ValueError('请选择本机磁盘上的资料库绝对路径。')
        if any(part.lower() == '.obsidian' or re.search(r'[<>:"|?*]', part)
               or part.endswith((' ', '.')) for part in path.parts[1:]):
            raise ValueError('资料库路径包含内部配置目录或无效名称。')
        path = path.resolve()
        if path == Path(path.anchor) or any(part.lower() == '.obsidian' for part in path.parts):
            raise ValueError('请选择专用资料库目录，不要选择磁盘根目录或 .obsidian 配置目录。')
        protected = [self.root / name for name in ('runtime', 'tools', 'models', 'state', 'ui', 'vault-template')]
        protected.extend(Path(os.environ[name]) for name in ('WINDIR', 'PROGRAMFILES', 'PROGRAMFILES(X86)') if os.environ.get(name))
        if path == self.root or any(path.is_relative_to(item.resolve()) for item in protected):
            raise ValueError('保存位置不能是应用文件或系统程序目录，请选择专用资料库。')
        if path.exists() and not path.is_dir():
            raise ValueError('保存位置必须是文件夹。')
        return str(path)

    def _validated_settings(self, payload, base=None):
        if not isinstance(payload, dict) or set(payload) - EDITABLE_KEYS:
            raise ValueError('设置包含不支持的字段。')
        if any(not isinstance(value, str) for key, value in payload.items() if key != 'hotword_files'):
            raise ValueError('设置格式不正确。')
        updated = deepcopy(self._cfg if base is None else base)
        updated.update(deepcopy(payload))
        updated['vault'] = self._validate_vault(updated.get('vault'))
        for key, allowed in [('preset', recorder.PRESETS), ('source', ['游戏窗口', '整个显示器']),
                             ('language', ['zh', 'en', 'ja', '']),
                             ('transcription_provider', ['later', 'local', 'qwen'])]:
            if updated.get(key) not in allowed:
                raise ValueError('设置选项无效：' + key)
        for key in EDITABLE_KEYS - {'hotwords', 'hotword_files', 'hotword_manual'}:
            value = updated.get(key, '')
            if not isinstance(value, str) or len(value) > 4096 or any(ord(char) < 32 for char in value):
                raise ValueError('设置文本包含无效内容：' + key)
        updated['game'] = updated.get('game', '').strip()[:120] or '自由探索'
        if 'hotwords' in payload and not {'hotword_files', 'hotword_manual'}.intersection(payload):
            # Compatibility with a legacy text-only editor explicitly replacing
            # its vocabulary. New structured fields always win over flattened text.
            files, manual = [], payload['hotwords']
        elif 'hotword_files' not in updated and 'hotword_manual' not in updated:
            files, manual = [], updated.get('hotwords', '')
        else:
            files, manual = updated.get('hotword_files', []), updated.get('hotword_manual', '')
        updated.update(compile_hotword_snapshots(files, manual,
                       qwen=updated['transcription_provider'] == 'qwen'))
        exe = updated.get('obsidian_exe', '')
        if exe:
            path = Path(exe)
            if not path.is_absolute() or path.name.lower() != 'obsidian.exe' or not path.is_file():
                raise ValueError('请选择已安装的 Obsidian.exe。')
            updated['obsidian_exe'] = str(path.resolve())
        # Saved selections remain editable even while devices are disconnected.
        # Availability is a readiness gate, not a reason to discard a preset.
        updated['configured'] = bool(updated.get('mic') and updated.get('window' if updated['source'] == '游戏窗口' else 'monitor'))
        # Full presets are keyed by stable ID. Keep any legacy games map intact
        # for compatibility, but never publish new settings into a name-keyed map.
        return updated

    def _install_vault(self, vault):
        vault = Path(vault)
        vault.mkdir(parents=True, exist_ok=True)
        for name in ('场次', '打包'):
            if (vault / name).resolve().parent != vault.resolve():
                raise ValueError('资料目录指向外部位置，已停止写入。')
        source = self.root / 'vault-template/.obsidian'
        for file in source.rglob('*'):
            if file.is_file():
                dest = vault / '.obsidian' / file.relative_to(source)
                if not dest.resolve().is_relative_to(vault.resolve()):
                    raise ValueError('资料库插件目录指向外部位置，已停止写入。')
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists():
                    shutil.copy2(file, dest)
        enabled = vault / '.obsidian/community-plugins.json'
        if not enabled.resolve().is_relative_to(vault.resolve()):
            raise ValueError('资料库配置文件指向外部位置。')
        plugins = recorder.read(enabled) if enabled.exists() else []
        if not isinstance(plugins, list) or not all(isinstance(name, str) for name in plugins):
            raise ValueError('资料库插件清单格式不正确，已保留原文件。')
        for name in ['media-transcript', 'experience-opener']:
            if name not in plugins:
                plugins.append(name)
        recorder.write(enabled, plugins)
        instructions = vault / '办公室打开说明.md'
        if not instructions.exists():
            instructions.write_text(recorder.OFFICE, encoding='utf-8')

    def _save(self, payload, preset_id=None, base=None):
        cfg = self._validated_settings(payload, base)
        self._install_vault(cfg['vault'])
        ident = preset_id or cfg.get('active_preset_id') or uuid.uuid4().hex
        cfg.setdefault('presets', {})[ident] = self._preset_snapshot(cfg)
        cfg['active_preset_id'] = ident
        self._persist(cfg)
        self._cfg = cfg
        self._readiness.update(ready=False, checking=True, checked_at=None)
        return self._public_config()

    def save_settings(self, payload):
        with self._lock:
            try:
                self._guard()
            except Exception as error:
                return self._error(error)
        with self._operation_lock, self._lock:
            try:
                self._guard()
                data = self._save(payload)
                self._progress('设置与当前游戏预设已保存。', status='已保存')
                self._request_readiness()
                return ok(data)
            except Exception as error:
                return self._error(error)

    def save_preset(self, payload, preset_id=None):
        with self._lock:
            try:
                self._guard()
            except Exception as error:
                return self._error(error)
        with self._operation_lock, self._lock:
            try:
                self._guard()
                if not isinstance(payload, dict):
                    raise ValueError('预设格式不正确。')
                payload = dict(payload)
                name = payload.pop('name', payload.get('game', ''))
                if not isinstance(name, str):
                    raise ValueError('游戏或项目名称必须是文本。')
                name = name.strip()
                if not name or len(name) > 120 or any(ord(char) < 32 for char in name):
                    raise ValueError('请填写 1 至 120 字的游戏或项目名称。')
                payload['game'] = name
                if preset_id is not None and preset_id not in self._cfg.get('presets', {}):
                    raise ValueError('要编辑的预设不存在。')
                ident = preset_id or uuid.uuid4().hex
                base = deepcopy(self._cfg)
                if preset_id:
                    selected = base['presets'][preset_id]
                    base.update({key: deepcopy(selected[key]) for key in PUBLIC_KEYS if key in selected})
                data = self._save(payload, ident, base)
                self._devices = {'mic': [], 'window': [], 'monitor': []}
                self._request_readiness()
                self._progress('录制预设已保存。', status='已保存')
                return ok(dict(id=ident, active_preset_id=ident, config=data))
            except Exception as error:
                return self._error(error)

    def select_preset(self, id):
        with self._lock:
            try:
                self._guard()
            except Exception as error:
                return self._error(error)
        with self._operation_lock, self._lock:
            try:
                self._guard()
                if not isinstance(id, str) or id not in self._cfg.get('presets', {}):
                    raise ValueError('请选择有效的录制预设。')
                cfg = deepcopy(self._cfg)
                selected = cfg['presets'][id]
                cfg.update({key: deepcopy(selected[key]) for key in PUBLIC_KEYS if key in selected})
                cfg['active_preset_id'] = id
                self._persist(cfg)
                self._cfg = cfg
                self._devices = {'mic': [], 'window': [], 'monitor': []}
                self._readiness.update(ready=False, checking=True, checked_at=None, errors=[])
                self._request_readiness()
                self._progress('已切换录制预设，正在检查保存的配置。', status='已切换预设')
                return ok(dict(active_preset_id=id, config=self._public_config()))
            except Exception as error:
                return self._error(error)

    def refresh_devices(self):
        def work():
            with self._lock:
                self._readiness.update(ready=False, checking=True)
            self._recover()
            if self._active is not None:
                self._update_readiness()
                return
            try:
                result = recorder.devices(progress=self._progress)
            except Exception:
                self._update_readiness()
                raise
            self._cache_devices(result)
            self._recover()
            self._update_readiness(devices=result)
            self._progress('设备列表已从 OBS 刷新；未开始电平检测。', status='设备已就绪')
        return self._launch('devices', work, status='正在读取设备', allow_uncertain=True)

    def _dialog(self, kind, **kwargs):
        with self._lock:
            self._guard()
            if self._window is None:
                raise RuntimeError('桌面窗口尚未就绪。')
            window = self._window
            self._dialog_open = True
        try:
            import webview
            dialog_type = webview.FOLDER_DIALOG if kind == 'folder' else webview.OPEN_DIALOG
            return window.create_file_dialog(dialog_type, **kwargs) or ()
        finally:
            with self._lock:
                self._dialog_open = False

    def choose_directory(self, kind):
        try:
            if kind not in ('vault', 'model', 'download'):
                raise ValueError('未知目录类型。')
            paths = self._dialog('folder')
            return ok({'path': str(Path(paths[0]).resolve()) if paths else None})
        except Exception as error:
            return self._error(error)

    def choose_obsidian(self):
        try:
            paths = self._dialog('file', allow_multiple=False, file_types=('Obsidian executable (*.exe)',))
            if paths and Path(paths[0]).name.lower() != 'obsidian.exe':
                raise ValueError('请选择 Obsidian.exe。')
            return ok({'path': str(Path(paths[0]).resolve()) if paths else None})
        except Exception as error:
            return self._error(error)

    def import_hotwords(self, current_text=None):
        try:
            with self._lock:
                self._guard()
                if current_text is None:
                    current_text = self._cfg.get('hotwords', '')
                qwen = self._cfg['transcription_provider'] == 'qwen'
            if not isinstance(current_text, str) or len(current_text) > 128000:
                raise ValueError('当前词库内容必须是文本，且不能超过 128000 个字符。')
            validate_words(split_words(current_text), qwen=qwen)
            paths = self._dialog('file', allow_multiple=True, file_types=('Hotword dictionaries (*.txt;*.scel)',))
            if not paths:
                return ok({'text': current_text, 'count': 0})
            words, count = merge_files(current_text, paths, qwen=qwen)
            return ok({'text': '\n'.join(words), 'count': count})
        except Exception as error:
            return self._error(error)

    def choose_hotword_files(self):
        try:
            paths = self._dialog('file', allow_multiple=True,
                                 file_types=('Hotword dictionaries (*.txt;*.scel)',))
            return ok({'files': read_dictionary_snapshots(paths)})
        except Exception as error:
            return self._error(error)

    def open_dictionary_site(self):
        try:
            if not webbrowser.open(SOGOU_DICTIONARIES):
                raise RuntimeError('未能请求浏览器打开搜狗词库下载页。')
            return ok({'requested': True})
        except Exception:
            return self._error('未能请求浏览器打开搜狗词库下载页。')

    def _require_transcription(self, cfg, allow_later=False):
        provider = cfg.get('transcription_provider', 'later')
        if provider == 'later':
            if not allow_later:
                raise RuntimeError('当前为仅录制。请在设置中选择本地模型或 Qwen 云端，再开始整理。')
        elif provider == 'local':
            if not self._model.resolve_model():
                raise RuntimeError('尚未准备本地模型。可下载或导入模型，或选择“仅录制，稍后整理”。')
        elif provider == 'qwen':
            if not self._has_key():
                raise RuntimeError('请先保存 Qwen API Key，或选择“仅录制，稍后整理”。')
        else:
            raise ValueError('转写方式无效。')

    def start_recording(self, payload=None):
        def work():
            readiness = self._update_readiness()
            if not readiness['ready']:
                raise RuntimeError('\n'.join(item['message'] for item in readiness['errors']))
            try:
                session = recorder.Session.start(cfg)
                with self._lock:
                    self._active = session
                self._progress('OBS 已确认录制开始；未开始电平检测。', status='录制中')
            except Exception:
                # A lost start acknowledgement can leave OBS recording. Reattach
                # before reporting failure; never silently abandon ownership.
                for ident in set(self._session_paths()) - before:
                    candidate = self._session(ident)
                    if candidate.meta.get('started') and not candidate.meta.get('test'):
                        candidate.update(recording_uncertain=True)
                self._recover()
                raise
        with self._lock:
            try:
                self._guard()
                if payload not in (None, {}):
                    raise ValueError('开始录制只使用已保存的预设。请先保存设置，再开始。')
                if not self._cfg.get('configured') or not self._cfg.get('active_preset_id'):
                    raise RuntimeError('请先完成并保存录制预设。')
                cfg = deepcopy(self._cfg)
                # Session history must not copy every other project's presets.
                cfg.pop('presets', None)
                cfg.pop('active_preset_id', None)
                cfg.pop('games', None)
                before = set(self._session_paths())
                return self._launch('starting', work, status='正在启动录制')
            except Exception as error:
                return self._error(error)

    def stop_recording(self):
        with self._lock:
            if self._active is None:
                return self._error('当前没有本应用接管的录制。')
            session = self._active
            cfg = deepcopy(self._cfg)

        def work():
            try:
                session.stop()
            except Exception:
                # Keep the active handle unless OBS proves this recording ended.
                try:
                    client = recorder.client(False)
                    if not client.get_record_status().output_active:
                        with self._lock:
                            self._active = None
                        session.update(state='失败', error='录制已停止，但保存校验尚未完成。原文件已保留，请恢复整理。')
                except Exception:
                    pass
                raise
            with self._lock:
                self._active = None
                self._uncertain_ids.discard(session.meta['id'])
            if cfg['transcription_provider'] == 'later':
                session.update(state='待整理')
                self._progress('录像已保存。可选择转写方式后再整理。', status='待整理')
                return
            self._require_transcription(cfg)
            with self._lock:
                self._activity.update(kind='processing', status='正在整理')
            process_isolated(session, self._progress)
            self._progress('整理完成，原始录像与复盘已保留。', status='可回看')
        with self._lock:
            if self._active is not session:
                return self._error('录制归属已变化，请查看当前场次状态。')
            return self._launch('saving', work, status='正在保存录像', allow_active=True)

    def _ensure_not_recording(self, session):
        try:
            client = recorder.client(False)
        except (OSError, OBSSDKError, WebSocketException):
            if (session.meta['id'] in self._uncertain_ids or session.meta.get('state') in SUSPECT_STATES
                    or session.meta.get('recording_uncertain')):
                raise RuntimeError('尚无法确认上次录制已结束。请刷新设备重新连接 OBS，再恢复整理。')
            return
        if client.get_record_status().output_active:
            directory = Path(client.send('GetRecordDirectory').record_directory).resolve()
            if directory == session.path.resolve():
                raise RuntimeError('此场次仍在录制，请先结束录制。')
        self._uncertain_ids.discard(session.meta['id'])

    def _processing_settings(self, session):
        # A display name is not a preset identity. Historical language/vocabulary
        # belong to the session, even if its preset was renamed or another preset
        # now has the same name. Only the chosen transcription engine and its
        # execution options come from the current saved configuration.
        cfg = deepcopy(session.meta['settings'])
        for key in ('model', 'device', 'compute_type', 'transcription_provider', 'qwen_region', 'qwen_model'):
            if key in self._cfg:
                cfg[key] = deepcopy(self._cfg[key])
        self._require_transcription(cfg)
        for file in (session.path / '转写原始').glob('*/云端任务.json'):
            self._contained_file(session, str(file))
            job = recorder.read(file)
            if job.get('state') == 'SUBMITTING' and not job.get('task_id'):
                raise RuntimeError('此场次存在结果不明的云端提交。请先恢复原任务编号，避免重复上传和计费。')
        return cfg

    def process_session(self, id):
        def work():
            session = self._session(id)
            cfg = self._processing_settings(session)
            self._ensure_not_recording(session)
            # Supplying settings always invokes the existing version-preservation
            # mechanism, including retries after a previous failed refinement.
            process_isolated(session, self._progress, transcription_settings=cfg)
            self._progress('整理完成，已有逐字稿版本与复盘均已保留。', status='可回看')
        return self._launch('processing', work, status='正在整理')

    def open_review(self, id, mode='obsidian'):
        if mode not in ('obsidian', 'html'):
            return self._error('回看方式无效。')

        def work():
            session = self._session(id)
            if mode == 'html':
                file = self._contained_file(session, '独立回看.html')
                os.startfile(file)
                self._progress('已请求浏览器打开独立回看网页。', status='已请求打开')
            else:
                self._install_vault(self._cfg['vault'])
                result = recorder.open_review(session, self._progress)
                if result == 'obsidian':
                    self._progress('Obsidian 插件已确认打开同步回看。', status='回看已打开')
                else:
                    self._progress('Obsidian 未确认打开；已请求浏览器打开独立回看网页。', status='已请求网页回看')
        return self._launch('review', work, status='正在打开回看')

    def package_session(self, id):
        def work():
            session = self._session(id)
            self._ensure_not_recording(session)
            result = session.package()
            self._progress('已打包并校验：' + str(result), status='打包完成')
            os.startfile(result.parent)
        return self._launch('export', work, status='正在打包并校验')

    def open_folder(self, id=None):
        try:
            with self._lock:
                path = self._session(id).path if id is not None else Path(self._cfg['vault']).resolve()
            if not path.is_dir():
                raise ValueError('资料目录尚未创建，请先保存设置。')
            os.startfile(path)
            return ok({'requested': True})
        except Exception as error:
            return self._error(error)

    def open_raw(self, id):
        try:
            with self._lock:
                self._guard()
                session = self._session(id)
                files = sorted(session.path.glob('*.mkv'))
                if not files:
                    raise ValueError('此场次尚未找到原始录像。')
                file = self._contained_file(session, '原始录像.mkv' if (session.path / '原始录像.mkv').exists() else files[0].name)
                os.startfile(file)
                return ok({'requested': True})
        except Exception as error:
            return self._error(error)

    def save_cloud_key(self, key):
        with self._lock:
            try:
                self._guard()
                if not isinstance(key, str):
                    raise ValueError('请输入完整的 API Key。')
                secret_store.save_key(key, directory=self.root / 'state/secrets')
                self._readiness.update(ready=False, checking=True)
                self._request_readiness()
                return ok({'saved': True})
            except Exception:
                return self._error('密钥保存失败。请检查完整性；密钥只使用当前 Windows 用户的 DPAPI 加密保存。')

    def verify_cloud_key(self):
        def work():
            from qwen_transcription import check_connection, MODEL
            try:
                key = secret_store.load_key(directory=self.root / 'state/secrets')
                result = check_connection(key, {'region': 'beijing', 'model': MODEL})
            except Exception:
                raise RuntimeError('Qwen 密钥或上传权限验证未通过，请检查密钥、网络及北京地域权限。此次未上传录音。') from None
            self._progress(result, status='密钥验证完成')
        return self._launch('processing', work, status='验证 Qwen 权限（不上传录音）')

    def recover_cloud_task(self, id, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', task_id):
            return self._error('任务编号格式不正确。')

        def work():
            from qwen_transcription import restore_task
            session = self._session(id)
            self._ensure_not_recording(session)
            if session.meta.get('settings', {}).get('transcription_provider') != 'qwen':
                raise ValueError('此场次没有可恢复的 Qwen 转写任务。')
            self._require_transcription(session.meta['settings'])
            cache = session.meta.get('transcription_cache')
            if not isinstance(cache, str) or not cache:
                raise ValueError('此场次没有转写缓存，不能绑定云端任务。')
            folder = (session.path / cache).resolve()
            if not folder.is_relative_to((session.path / '转写原始').resolve()):
                raise ValueError('转写缓存路径无效。')
            job_file = self._contained_file(session, str(folder / '云端任务.json'))
            job = recorder.read(job_file)
            if job.get('task_id') and job['task_id'] != task_id:
                raise ValueError('已保存的任务编号不同，已拒绝覆盖。')
            # Preserve the exact recorded options/fingerprint: current settings
            # could otherwise switch cache and accidentally submit another task.
            recorder.session_lock(lambda owned: restore_task(folder, task_id))(session)
            process_isolated(session, self._progress)
            self._progress('已恢复查询原云端任务并完成整理。', status='可回看')
        return self._launch('processing', work, status='正在恢复原云端任务')

    def model_action(self, action, path=None):
        with self._lock:
            try:
                self._guard()
                if action == 'pause':
                    result = self._model.pause_download()
                elif action in ('download', 'import'):
                    if path is not None:
                        if not isinstance(path, str) or not Path(path).is_absolute():
                            raise ValueError('请选择模型目录的绝对路径。')
                    if action == 'download':
                        result = self._model.start_download(path)
                    elif path:
                        result = self._model.use_existing(path)
                    else:
                        raise ValueError('请选择已有模型目录。')
                else:
                    raise ValueError('模型操作无效。')
                if isinstance(result, dict) and not result.get('ok', True):
                    return self._error(result.get('error', '模型操作未完成。'))
                return ok(self.get_state()['data']['model'])
            except Exception as error:
                return self._error(error)

    def open_official_obsidian(self):
        try:
            requested = webbrowser.open('https://obsidian.md/download')
            if not requested:
                raise RuntimeError('未能请求浏览器打开，请访问 https://obsidian.md/download。')
            return ok({'requested': True})
        except Exception as error:
            return self._error(error)

    def _recover(self):
        connected = False
        recording_path = None
        interrupted = False
        active_unknown = False
        try:
            client = recorder.client(False)
            recording = client.get_record_status()
            if recording.output_active:
                # A positive status alone cannot establish whose recording this
                # is. Do not classify other sessions as stopped until its output
                # directory is also known.
                active_unknown = True
                directory = client.send('GetRecordDirectory').record_directory
                if not isinstance(directory, str) or not directory or not Path(directory).is_absolute():
                    raise ValueError('OBS 未返回可确认的录制目录。')
                recording_path = Path(directory).resolve()
                active_unknown = False
            connected = True
        except Exception:
            pass
        with self._lock:
            self._obs_uncertain = active_unknown or (self._obs_uncertain and not connected)
            for ident, path in self._session_paths().items():
                session = recorder.Session(path)
                if recording_path == path:
                    if session.meta.get('test'):
                        self._progress('OBS 正在录制合成测试场次，未接管或停止它。')
                        continue
                    self._active = session
                    self._uncertain_ids.discard(ident)
                    session.update(state='录制中', recording_uncertain=False)
                    self._progress('已接回 OBS 确认仍在进行的录制。', status='录制中')
                elif session.meta.get('state') in SUSPECT_STATES | {'转写中'} or session.meta.get('recording_uncertain'):
                    uncertain = not connected and (session.meta.get('state') in SUSPECT_STATES or session.meta.get('recording_uncertain'))
                    if uncertain:
                        self._uncertain_ids.add(ident)
                    else:
                        self._uncertain_ids.discard(ident)
                    try:
                        recorder.session_lock(lambda owned: owned.update(state='失败', recording_uncertain=bool(uncertain),
                            error='上次操作中断，原始资料已保留。请恢复整理；连接不明时先刷新设备。'))(session)
                        interrupted = True
                    except RuntimeError:
                        self._progress('有场次仍由另一整理进程持有，已保留其状态。', status='场次正在后台整理')
                elif connected:
                    self._uncertain_ids.discard(ident)
            if self._obs_uncertain:
                self._progress('OBS 曾确认仍在录制，但当前无法确认录制目录。请刷新设备重新连接；暂不允许开始新作业或退出。',
                               status='录制归属待确认')
            if (self._active is None and not self._uncertain_ids and not self._obs_uncertain
                    and self._activity['status'] in ('检查上次场次', '检查录制状态')):
                # A completed startup check must not keep showing an in-flight
                # label. Keep specific errors and external-worker warnings intact.
                if interrupted:
                    self._progress('发现上次中断的场次，原始资料已保留，可在场次页恢复整理。', status='有场次待恢复')
                else:
                    self._activity['status'] = '待开始'

    def _monitor_loop(self):
        while not self._closed.wait(5):
            with self._lock:
                if self._activity['busy']:
                    continue
                idle = self._active is None and not self._uncertain_ids and not self._obs_uncertain
            if idle:
                self._request_readiness()
                continue
            self._launch('recording' if self._active else 'devices', self._inspect_recording if self._active else self._recover,
                         status='检查录制状态', allow_active=True)

    def _inspect_recording(self):
        with self._lock:
            session = self._active
        if session is None:
            return
        try:
            client = recorder.client(False)
            state = client.get_record_status()
        except Exception:
            self._progress('无法连接 OBS，录像可能仍在继续。正在重连，请勿重复开始。', status='录制连接中断')
            return
        if not state.output_active:
            session.update(state='失败', error='OBS 录制意外停止。原录像已保留，请选择恢复整理。')
            with self._lock:
                self._active = None
            self._progress(session.meta['error'], status='录制已中断')
            return
        directory = Path(client.send('GetRecordDirectory').record_directory).resolve()
        if directory != session.path.resolve():
            session.update(state='失败', error='OBS 已切换到其他录制目录。本场次原文件已保留，未停止其他录制。')
            with self._lock:
                self._active = None
            self._progress(session.meta['error'], status='录制归属已变化')
            return
        if shutil.disk_usage(session.path).free < 2 * 1024 ** 3:
            session.stop()
            session.update(state='待整理', warning='磁盘剩余空间不足 2 GB，已停止并保存录像。')
            with self._lock:
                self._active = None
            self._progress(session.meta['warning'], status='待整理')
        else:
            self._progress('OBS 正在录制 ' + str(getattr(state, 'output_timecode', '')) + '；未开始电平检测。', status='录制中')

    def close_allowed(self):
        """Internal pywebview closing event handler; intentionally returns bool."""
        with self._lock:
            blocked = (self._activity['busy'] or self._active is not None or bool(self._uncertain_ids)
                       or self._obs_uncertain or self._dialog_open or self._readiness['checking']
                       or bool(self._readiness_thread and self._readiness_thread.is_alive()))
            if not blocked:
                self._model.pause_download()
                stopped = self._model.wait(timeout=0)
                state = self._model.status()['state']
                blocked = stopped is False or state in ('downloading', 'verifying')
            if blocked:
                self._progress('操作仍在后台进行，窗口已最小化。请等待录制、保存或模型写入安全结束后关闭。')
                return False
            self._closed.set()
            return True
