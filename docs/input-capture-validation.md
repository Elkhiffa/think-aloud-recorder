# Input capture: integration contract and validation

2026-09-22. These notes distinguish implemented safeguards, synthetic tests, native lifecycle checks and still-unverified hardware behavior.

## Integration API

- `capture_readiness(settings, root=None)` returns `{enabled, ready, error}`. `record_inputs` must be true; source must be `游戏窗口`; exact OBS window identifier must resolve unambiguously. No listener starts during readiness.
- `prepare_capture(settings, session_path, *, root=None, clock=time.perf_counter)` returns None if disabled, otherwise an InputRecorder. Preparation does not capture input.
- `start(origin=None, video_offset=0.0)` starts only after OBS confirms recording and Session has a trustworthy video clock sample. `origin` is the perf_counter sample corresponding to `video_offset`.
- `stop(duration=None, interrupted=False, error=None, trim_to=None)` releases the native source and materializes final data. `trim_to` removes intervals at/after the authoritative video cutoff and clips crossing intervals. It also atomically rebuilds this run's journal; recovery/export cannot reintroduce that tail.
- `recover_capture(session_path, duration=None, *, error=None, trim_to=None)` reads the durable checkpoint/journal prefix, marks interrupted, and adds a capture gap through known video duration. It never resumes listeners.
- `snapshot()` materializes diagnostic current history outside the capture lock. Production recording persistence uses a small checkpoint, not this full-history path.

## Files and data

`input-events.json` is a small atomic checkpoint while recording: duration, clock, sanitized current holds, journal count and journal basename. `input-events.journal` receives sanitized completed interval/gap records with fsync. A partial or uncheckpointed tail is not treated as durable coverage. On stop, the final JSON is materialized in the public version-1 contract (`timebase: video_seconds`, state, intervals, gaps), so stopped-session review does not depend on the journal. Recovery must use `recover_capture`, not interpret the live checkpoint's empty intervals array as all history.

`input-events.revocation.json` is an independent atomic revocation fence containing only version and earliest `invalid_from` video time. It is persisted before invalidation cleanup or an explicit video cutoff changes the data files and retained for the session. Recovery applies it to both checkpoint-only active holds and journal records before using them. Thus a crash or failed checkpoint replacement after journal cleanup cannot revive stale holds. An unreadable existing fence fails closed to zero; normal sessions without a revocation have no extra file.

The startup capture gap covers video zero through listener readiness, including the OBS offset. Focus, disconnect and capture failure have separate gaps. Resumed holds are marked `resumed`, rather than inventing their onset. Auto-repeat is deduplicated. Holds stop at the final acknowledged capture watermark even if listener shutdown blocks or the observer fails; the remaining known video duration is a capture gap. Text, clipboard contents, foreground titles and unrelated source fields are not written.

A collector reserves a new journal exclusively. If a journal/sidecar already exists, start and subsequent cleanup do not overwrite those prior files.

## Backend and dependency

Keyboard/mouse use Windows Raw Input via ctypes. Every source event is checked against the bound target HWND/process before persistence; keyboard/mouse raw payload is not read while the current foreground is outside the target. Target lookup is exact title/class/executable, then bound to HWND and process creation; ambiguous/missing targets fail closed.

Xbox and DualSense use the SDL2 event/controller API. The portable runtime is official pinned SDL2 2.32.10 x64 at `tools/input/SDL2.dll`, prepared by `scripts/fetch_input_runtime.py`, with provenance and zlib license. No global plugin/runtime installation or runtime download occurs. Sensors/rumble are not enabled. A development-only explicit `THINK_ALOUD_SDL2_PATH` can select a DLL.

## Foreground timing and late notifications

A dedicated WinEvent observer records timestamped foreground changes independently of capture/disk work. A **single OUTOFCONTEXT hook** receives foreground events and a custom queue-confirmation event from our own message-only hidden window. The durable watermark advances only when that exact self-issued marker callback arrives; elapsed time alone never advances authorization. Pending events beyond the acknowledged watermark remain in memory. If marker acknowledgement stalls, capture fails closed. The native lifecycle test confirmed hundreds of marker callbacks and hook cleanup.

Custom event specification: OEM range event `0x01FF`, hwnd = this recorder's private message-only STATIC window, idObject = `0x5441`, idChild = per-observer increasing sequence. This signals only our internal queue fence, not focus, keyboard input or a visible/accessibility action. Unrelated callbacks in the hook range are ignored. Microsoft documents the OEM range as open for communication mechanisms and requires published definitions to avoid collisions; identity checks include our private hwnd and outstanding sequence.

Resumed keyboard/mouse samples recheck actual foreground on each sample and use the same event gate; a loss of focus terminates the resume loop. Resume samples wait for 64 ms of stable target focus. Raw Input and WinEvent timestamps share one calibrated system-tick-to-monotonic mapping, so callback delay does not change their relative timestamp mapping. Source timestamps use the actual system/SDL tick difference, not an age clamped to 60 seconds. Input older than two seconds is discarded with a gap when it reaches the event gate.

A notification unexpectedly crossing an already acknowledged watermark invalidates capture immediately. `invalid_from` propagates to the recorder, stops further input output, and atomically rebuilds this run's owned journal and final view from the trusted prefix. Discarded ranges remain capture gaps. The regression suite covers a key already checkpointed before a deliberately out-of-order away/back notification; it disappears from final JSON, journal, and later recovery.

**Remaining guarantee boundary:** same-hook sequential WinEvent delivery is the documented basis for the marker fence. The 32 ms subtraction used on acknowledged marker time accommodates common 10–16 ms system-tick resolution; it is not a latency timeout or authorization rule. Events within 32 ms of a foreground transition are also excluded conservatively, since SDL uses a separate clock. Tests do not establish absolute microsecond-boundary privacy or perfect correspondence between OS/SDL timestamps and physical activity. Unexpected late/out-of-order notifications are treated as capture failure with retained-tail cleanup; do not claim stronger privacy or real-hardware timing acceptance than this evidence supports.

## Verification

40 deterministic tests pass in `tests/test_input_capture.py`: 2 ms taps; queued taps after snapshots; repeats; long holds; focus resume and pre-read exclusion; missed away/back transitions; late notification rollback of checkpointed records; journal recovery/partial tails; cutoff and journal consistency; controller mapping/deadzones; keyboard/mouse Win32 struct decoding; lifecycle failure cleanup; preserved existing journals; historical snapshot lock separation; fixed-watermark shutdown waits and observer failures; shared tick mapping; conservative transition bands; failed checkpoint replacement with stale active holds; persistent earliest-revocation authority.

The opt-in `tests/test_input_capture_native.py` also passes with `THINK_ALOUD_NATIVE_INPUT_SMOKE=1` and is skipped by normal discovery. It creates its own hidden target and never foregrounds it, registers actual Raw Input listeners and WinEvent hook, initializes SDL, checks for approximately 1.5–1.7 seconds, then cleans up. Input intervals written: 0. Raw Input registrations restored, capture/observer threads stopped, WinEvent unhook confirmed, hundreds of ordered marker acknowledgements received, SDL subsystems released. Read-only SDL type enumeration saw Xbox. No user key/button values were printed/persisted and no SendInput was used. Exact latest counts are in ignored `work/input-native-smoke.json`.

A synthetic 100,000-interval write-cost run yielded a 320-byte live checkpoint, 13,156,895-byte journal, and next idle checkpoint cost of 5.09 ms on this machine. History read/sort occurs outside the capture lock. This is a synthetic throughput/locking result, not a real input-latency result. Evidence: `work/input-journal-performance.json`; script: `work/bench_input_journal.py`.

## Isolated OBS integration attempt

The first real isolated OBS run used only ffmpeg synthetic video, a synthetic 880 Hz tone on track 1, and synthetic silence on tracks 1/2. Native capture started with the target resolver injected solely to bind an owned hidden HWND excluded by the normal visible-window picker. No microphone, desktop sound or user window source was selected.

The run failed the production OBS clock continuity check on its first follow-up sample, before completing Session.stop/prepare_video. Initial OBS output duration was zero. OBS log shows encoder startup work reaching approximately 347 ms; this may explain a wall-clock/video-start mismatch but is an inference, not a confirmed diagnosis. The test's own recording was stopped and OBS PID 8612 normally closed after exact executable/root/recording-directory validation. No preexisting OBS existed. Failed evidence remains under `work/obs-input-smoke/run-20260922-170624/report.json` and `cleanup-after-failure.json`. This is **not** a successful end-to-end acceptance.

## Still unverified

- Actual Xbox button events, DualSense USB/Bluetooth behavior, unplug/reconnect, and Steam Input/remapped-device behavior. An OS-exposed virtual Xbox controller is labeled Xbox; the underlying physical hardware cannot be inferred from icon styling.
- Full actual recording/video timing and long-session drift. Session's OBS query uncertainty does not replace a physical timing test.
- UWP/hosted/protected targets that cannot resolve exact OBS window identity remain unavailable rather than broadening scope to any process window.

## Primary references

- https://learn.microsoft.com/en-us/windows/win32/inputdev/using-raw-input
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwineventhook
- https://github.com/libsdl-org/SDL/blob/SDL2/include/SDL_events.h
- https://github.com/libsdl-org/SDL/blob/SDL2/include/SDL_gamecontroller.h
- https://github.com/obsproject/obs-studio/blob/master/libobs/util/windows/window-helpers.c

- https://learn.microsoft.com/en-us/windows/win32/winauto/allocation-of-winevent-ids


### Second isolated OBS attempt after marker-fence fix

`work/obs-input-smoke/run-20260922-172203/report.json` confirms real Session.start/native listeners/Session.stop/prepare_video and pre-transcript review generation, while still failing startup-clock continuity. First follow-up sample: video 0.000 s vs wall since anchor 0.614880 s. Next: video 0.199 s vs wall 1.317538 s. Later samples keep approximately 1.1 s offset (e.g. video 2.633 s vs wall 3.725813 s). This supports waiting for an advancing/stable OBS video clock before establishing the initial anchor; simply relaxing drift tolerance would conceal the discrepancy.

Actual output: raw MKV 4.366 s, one H.264 video and two AAC audio tracks; prepared MP4 4.288 s, one video/one mixed audio track. Mixed audio peak approximately 0.12917, independent synthetic microphone track peak exactly 0. No transcript was produced; pending-transcript desktop review payload and offline review HTML were generated successfully. Input state correctly failed due to clock protection, 0 intervals, explicit capture gap. Listener and observer threads stopped, WinEvent hook unregistered, OBS capture sources removed and recording stopped.

Normal owned-OBS shutdown returned close_unconfirmed before the process completed exit. A read-only follow-up (`post-exit.json`) then confirmed PID 50080 absent and no remaining OBS processes, without any additional kill/close. The original report remains failed; this is partial integration evidence, not an all-green acceptance.

### Third isolated OBS attempt after startup-clock calibration

`work/obs-input-smoke/run-20260922-172742/report.json` used recorder SHA-256 `c476c5d51d1eca20a47a626a287fc75fecb5b23971ad710e3de9ade35086a575`. All eight subsequent OBS clock observations passed without changing the drift tolerance. Initial video anchor was 0.233 s; follow-up samples spanned 0.799–3.699 s. This validates the short synthetic recording's clock-continuity check, not physical input-to-frame latency or long-session drift.

Actual output: raw MKV 5.733 s, one H.264 video/two AAC audio tracks; prepared MP4 5.754 s, one video/one mixed audio track. Mixed audio peak approximately 0.13402, independent synthetic microphone peak exactly 0. Sidecar state complete, video_seconds timebase, zero outside-target intervals and explicit focus/capture gaps. No transcript was generated; the pending-transcript review payload and offline HTML were produced. Listener/observer threads stopped, hook unregistered, OBS recording idle and synthetic capture sources released.

The attempt remains failed because normal OBS shutdown exceeded both the production 8-second wait and the additional test 12-second child-process wait. OBS log records shutdown beginning at 17:28:09.106, an older WebSocket client's closing handshake timing out at 17:28:14.457, and the server thread exiting at 17:28:31.192. A later read-only `post-exit.json` confirms PID 53228 absent and no remaining OBS processes; no additional close/kill occurred. The open client was established immediately before Session.start's operations, so missing explicit Session request-client cleanup is a likely contributor for the integration owner to inspect. No production recorder lifecycle code was modified by this worker.

### Fourth isolated OBS attempt: passed after explicit client cleanup

`work/obs-input-smoke/run-20260922-174132/report.json` passed all 19 recorded checks with recorder SHA-256 `400d34aabb72173b747ecaa446cccdff85b7a2f22fe059e3ce53a726c5acd647` and collector SHA-256 `e6543daa9d1f1a600d5f6a2608b9871ac3083b6e1b41c01dc9a651ca80985890`. This run used the integrated request-client cleanup, shared foreground-clock mapping, marker fence and persistent revocation code. No production sources were modified for this rerun. The same resolver-only injection bound the test's own hidden HWND; it was never foregrounded. All video/audio sources were synthetic and no user input was recorded.

All eight clock-continuity observations passed, spanning video 0.799–3.766 s from initial offset 0.266 s; the last verified OBS video time was 4.166 s. Actual raw MKV: 5.766 s, one H.264 video/two AAC audio tracks. Prepared MP4: 5.754 s, one H.264 video/one AAC mixed audio track. Mixed audio peak approximately 0.13209; independent synthetic microphone peak exactly 0. Sidecar state complete, duration 5.766 s, zero intervals, explicit focus/capture gaps. Pending-transcript review payload and offline HTML were produced without starting transcription.

Listener and observer threads stopped, the WinEvent hook unregistered, OBS recording stopped and synthetic capture sources were released. `shutdown_owned_obs` returned `closed` within its existing production deadline; original child exit was confirmed. Log timestamps show normal shutdown beginning at 17:41:59.641 and WebSocket server shutdown complete at 17:42:00.134, without the earlier closing-handshake timeout. No force termination was used. There were no preexisting OBS processes and no OBS processes remained afterward; a separate read-only enumeration also confirmed absence. The first three failed reports remain unchanged.

This passes the bounded synthetic Session.start/native-listener/Session.stop/prepare_video/early-review/normal-exit integration scope. It does not claim real Xbox/DualSense button acceptance, target-focus switching latency, physical input-to-frame alignment or long-session drift results.

## Readability and scrubbing follow-up: preview.2 / preview.3

The final preview.3 frontend groups contiguous analog samples into display bands while retaining raw intervals, uses readable short-press boxes with collision-free columns, and supports timeline clicks and vertical pointer dragging. Manual scrubbing preserves playback state and speed and suspends automatic viewport following. Quote clicks still pin text; quote drags seek. The library-copy control now belongs to header metadata, above the video. The bundled UI/UX vocabulary contains 440 terms; existing preset vocabulary snapshots remain unchanged until reimported.

Final validation on 2026-09-22:

- Python suite: 265 tests, 264 passed and one optional native-input test skipped. Frontend state, pure-function and syntax checks passed.
- Production browser input/review suite: 27 checks passed, including real browser pointer dragging, snapshot changes during a gesture, tail-click suppression, frozen time mapping, paused/playing state, zoom and horizontal browsing. Cancellation/blur checks inject lifecycle events during a real browser drag. Video aspect suite: 10 checks passed. General UI suite: 32 checks passed.
- Independent Edge reproduction confirms that pressing a quote, inserting an earlier transcript segment through a snapshot, and releasing still pins the originally pressed text.
- The final preview.3 archive was extracted into a path containing spaces and Chinese characters. All 7,039 manifest files and 50 current application source files matched. The packaged EXE self-check passed from outside the installation directory.
- Final packaged WebView2 smoke: seven checks passed and both windows closed automatically. Fixtures use synthetic media/inputs and a simulated main bridge; review API and clip-name persistence are real. The native timeline tap dispatches synthetic pointer events, while actual mouse gesture coverage belongs to the browser suite.

Local reports are retained under ignored `work/input-review-scrubbing`, `work/review-aspect-scrubbing`, `work/visual-acceptance-scrubbing`, and `work/native-input-preview3`. The preview.3 software ZIP is 309,254,729 bytes with SHA256 `5be6bbe04bb7bed5f71afad5e34c3a2bca8fed47d2407f5ccfea52f96529ccf0`. It contains no model weights or personal runtime data and remains a private test candidate pending the existing dependency-source redistribution requirements. These checks add no real Xbox/DualSense hardware or long-session timing claim.

## 2026-09-23: input alignment and readable review tracks

The old OBS output-duration clock counts encoded output, not the acquisition time of the current video frame. A stable encoder buffer therefore passed continuity checks while leaving a constant input/video offset. New complete, continuous recordings retain raw input timestamps and store a separate `input_alignment` measured from the final video-track endpoint and the bounded StopRecord/STOPPING interval. Missing events, pauses, clock discontinuities, recovery and excessive uncertainty do not receive an automatic correction. Existing clips can set or clear an explicit per-clip offset through the review file menu; positive values move input later. This never rewrites video, original events or speech timestamps.

Two isolated 720p30 OBS/x264 synthetic recordings measured offsets +1.246719 and +1.274064 seconds. Eight timed color markers had maximum residual 0.014323 seconds after correction. Evidence: ignored `work/native-clock-20260923-174318/report.json`. This validates the video-clock mapping against synthetic events, not physical keyboard/controller latency or long-session drift. The same test's cleanup CRASHED in GetOutputList after recording had completed; its recordings must not be represented as a full lifecycle pass. The crash and original logs remain preserved.

Review behavior:

- Direction, pointing and D-pad use fixed narrow lanes. Overlapping WASD directions are combined at the playhead; no independent W/A/S/D lanes. Raw input remains available for precise state and inspection.
- Motion samples separated by at most 120 ms form one display band; D-pad presses separated by at most 650 ms form a navigation burst. Capture gaps and resumed boundaries split bands. These grouping thresholds affect presentation only.
- Dashed borders and weak fill indicate grouped activity. Horizontal ticks mark real press onsets or motion restarts; dense analog sampling does not create a stripe per sample. Solid single holds remain distinct. Only the playhead's current direction is labelled. Inside a D-pad burst, the latest preceding press is shown even between taps; its tooltip says when it has been released.
- Grid lines are below input bars. Sticky ruler labels occupy a separate layer; the playhead remains above bars.
- Recent operations remain for two video seconds after release. Each button press expires independently. Analog sampling is consolidated per control; active inputs and released-but-recent inputs have different fills. Seeking reconstructs this from the destination timestamp.
- The video and recent-operation panel share their width. Initial video width targets at least 900 CSS pixels when room allows. Later window resizing preserves the current left width, changing the right pane first until its measured header/ruler minimum. 900 is not a resizing minimum or a width restored on enlargement. Source pixels use `object-fit: contain`, with player bars as needed.

Browser evidence: 29 synthetic interaction checks in `work/input-review-bands/acceptance.json`; 10 responsive/source-size checks in `work/review-aspect/acceptance.json`. They use production HTML/CSS/JS with synthetic media/bridge fixtures, and do not establish native device compatibility. Raw timestamp immutability, negative/positive offsets, media clipping, burst boundaries, independent expiry and 100k-event range lookup are also covered by `tests/test_review_ui.js`.

## 2026-09-24: browsing, true holds and movable quotes

- A real button/trigger interval strictly longer than 0.5 seconds has warm fill and a solid rail. A 0.5-second press retains the tap style. Display padding, motion sampling and accumulated tap-burst duration never qualify as a long press. A real hold inside a grouped navigation band has its own solid section, while the surrounding burst remains dashed.
- Content-wheel input browses the timeline without seeking, pausing or changing playback speed. It suspends automatic follow. Ruler-wheel input still zooms around the pointed time; clicks and vertical drags still seek. An offscreen playhead produces an upper/lower return button inside the visible pane, including during horizontal browsing. Clicking it restores follow without seeking. View bounds clamp at the start/end.
- Hover previews remain temporary. Clicking a quote pins it until its explicit close button is used. The header can be dragged within the window or moved using its focused time label and arrow keys; the body remains selectable and scrollable. Outside clicks, Escape, seeking, scrolling, tab changes and new transcript snapshots do not dismiss it. A newly clicked quote replaces its content while retaining a manually chosen position. Resizing clamps it back inside the window and keeps close accessible. A pinned quote retains its original text if that transcript snapshot is subsequently replaced.

Evidence in the isolated timeline worktree: 31 production-browser checks in `work/input-review-bands/acceptance.json`, 10 popup checks in `work/quote-popover/acceptance.json`, 10 layout checks in `work/review-aspect/acceptance.json`, and the pure helper suite in `tests/test_review_ui.js`. Python regression: 429 tests, one environment skip. Browser fixtures are synthetic and do not establish physical device accuracy or OBS lifecycle behavior.
