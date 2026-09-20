# Desktop bridge contract (v1)

Every public method returns `{ok: true, data: ...}` or `{ok: false, error: "user-readable message"}`. JavaScript uses `window.pywebview.api`. Never return or log saved secrets. Long operations launch a tracked background task; the UI polls `get_state()` every 1 second. Mutations are rejected while recording or a conflicting task is running. Native directory/file dialogs are handled by the service via `set_window(window)`.

`get_state()` data:
- `presets`: list of {id,name,vault}; `active_preset_id`: current stable ID or null. Presets independently save complete user-facing settings. Secret/model resources remain app-scoped.
- `readiness`: {ready,checking,errors:[{code,message,step}],checked_at}. Applies only to persisted active preset. step=1 capture,2 transcription,3 location. Idle checks are asynchronous; frontend must not infer readiness from saved IDs or paths. Never enables capture from stale or failed checks.
- `config`: game, vault (resolved absolute path), preset, source (游戏窗口/整个显示器), window, monitor, mic, language (zh/en/ja/empty), hotwords, transcription_provider (later/local/qwen), obsidian_exe, configured, games. No OBS password or port, no cloud keys.
- `sessions`: list of {id, game, created, state, duration, segments, warning, error, path, test} sorted newest first. IDs are resolved within the configured vault; no arbitrary session paths accepted by action APIs.
- `activity`: {busy, kind, status, detail, active_id, elapsed_seconds}. Recording is authoritative only after OBS confirms start. Idle kind='idle', recording='recording', start='starting', stop='saving', processing='processing', review='review', export='export', devices='devices'.
- `devices`: {mic: [{itemName,itemValue,itemEnabled}], window: [...], monitor: [...]} from actual OBS, initially empty. Never fabricate devices or meters.
- `model`: ModelManager.status() described below.
- `capabilities`: {cloud_key: bool, obsidian: bool, obs: bool, local_model: bool}.

Methods:
- `refresh_devices()` refreshes actual devices in a tracked job.
- `save_settings(payload)` saves a whitelist of config keys. Device values are itemValue, not display labels. Reject unsafe vault paths, invalid enums; save per-game preset. Switching game can use existing `config.games` client-side then save.
- `save_preset(payload,preset_id=null)` creates a new named preset or updates the specified ID. Payload contains `name` plus editable settings. Return fresh saved state; do not start capture. Name should be the game/project name.
- `select_preset(id)` applies all selected settings, switches vault/session list, and invalidates readiness until refreshed. Reject while recording or doing conflicting work.
- `choose_directory(kind)` returns {path} or {path:null}; kind vault/model/download. Only selects, does not write selected directory or import a model.
- `choose_obsidian()` returns {path} after native EXE picker; user saves it with save_settings.
- `import_hotwords(current_text=null)` returns {text,count} after native multi-file .txt/.scel picker; merges with the unsaved draft when supplied. Does not save until settings/preset is saved.
- `choose_hotword_files()` returns `{files:[{id,name,words}]}` from a native multi-file TXT/SCEL picker. Cancel returns an empty list. All selected files must parse before any are returned. Names are basenames, never absolute paths; IDs identify normalized word content. The wizard appends unique files to its unsaved draft.
- `open_dictionary_site()` opens only `https://pinyin.sogou.com/dict/` in the system browser. It does not send preset names, words or local filenames.
- Preset/config fields `hotword_files` and `hotword_manual` retain dictionary snapshots and optional manual terms. Save recomputes and validates the flattened `hotwords` transcription input. Legacy flat vocabulary becomes manual terms. Session exports contain flattened words only, never file metadata.
- `start_recording(payload)` frontend passes `{}` to start from the persisted active preset. Backend revalidates before starting. `later` never requires a cloud key or local model. Other modes require their respective capability. No test-only source reachable through this method.
- `stop_recording()` saves recording; `later` stays 待整理; other modes invoke existing process_isolated. Do not leave active ownership ambiguous on failure.
- `process_session(id)` reprocesses using current transcription settings; preserve old transcript via existing version mechanism. Reject `later` with a helpful instruction.
- `open_review(id, mode='obsidian')` mode obsidian/html; reports plugin acknowledgement or HTML fallback distinctly.
- `package_session(id)` exports session; `open_folder(id=null)` opens current vault or selected session. `open_raw(id)` opens existing raw video.
- `save_cloud_key(key)` calls existing DPAPI store (never return key); `verify_cloud_key()` uses current stored key and existing Qwen validator.
- `recover_cloud_task(id, task_id)` uses existing Qwen recovery procedure; no repeated submission for uncertain results.
- `model_action(action, path=null)` actions download/pause/import; forwards to ModelManager. No model deletion API.
- `open_official_obsidian()` opens https://obsidian.md/download, no installation.
- `close_allowed()` internal app close handler: active recording or job prevents shutdown and minimizes with status explanation. Model transfer pauses safely before idle close.

ModelManager(root) API (separate owned module):
- `status()` -> {state: missing/downloading/paused/verifying/ready/error, model:'large-v3', path, downloaded_bytes, total_bytes, error, source, revision}. This method is cheap and non-blocking.
- `start_download(directory=None)` -> starts async pinned download to a default root/models/large-v3 or selected directory. No overwrite of mismatching existing completed files. Preserve partial files.
- `pause_download()` -> cooperative cancellation retaining partial data.
- `use_existing(path)` -> asynchronously validate and register external model directory, no copy.
- `resolve_model()` -> ready model path or None; registry reload supports another worker process. Only validated files with unchanged stats accepted; hash validation establishes the registry.
- `wait(timeout=None)` for tests / safe shutdown. Thread-safe state.

Frontend: native-looking local UI based on the approved prototype, but all mocked timers, samples, model downloads, and success transitions are removed. No public preview or mock mode in the shipped app. Local HTML error fallback is real, not a fabricated success. Format actual bytes with units. When a meter is unavailable say '未开始电平检测', never animate fabricated activity. Focus, keyboard access, loading states, and errors must remain clear.
