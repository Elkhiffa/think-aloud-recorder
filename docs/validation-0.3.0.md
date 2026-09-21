# Standalone review validation — 2026-09-21

Implemented on `feat/standalone-review`, based on `208bee6489fd5ebb783e9f46745eb4a50b0ac447`.

## Automated checks

- Prepared private Python 3.12.10: `python.exe -m unittest discover -s tests` — 139 tests, 138 passed, 1 skipped (Windows symlink permission).
- `node --test tests/test_ui_state.js tests/test_review_ui.js` — 14 passed.
- JavaScript syntax and Git whitespace checks passed.
- Session tests cover immutable old notes/transcripts, renewed exported HTML, bounded file commands, invalid timestamps, and escaped transcript/title content.
- Shutdown tests cover idle polling, concurrent old-session review during recording, queued work, saving before close, cancelled confirmation, and failed stop retaining ownership.

## Actual Windows UI checks

Used two explicitly labelled synthetic sessions, each with a real 120-second H.264/AAC test-pattern MP4 and 40 synthetic transcript segments. No screen/microphone recording or cloud transcription was performed. The UI harness disables OBS enumeration and marks readiness as still checking; this is a deliberate regression fixture, not evidence of live device readiness.

- Two native WebView2 review windows loaded their videos simultaneously, retaining independent playback positions.
- Clicking the 00:00:03 transcript row sought to the corresponding video frame and started playback.
- Space paused playback after a transcript click; it no longer reactivates the focused transcript button.
- While paused at approximately 8.917 seconds, Right moved to 23.917 and Left returned to 8.917 seconds.
- Clicking the middle of the progress bar sought to approximately 59.750 seconds.
- Scrolling the transcript left the video in place and suspended automatic following.
- Copy-video-path completed through the native clipboard bridge. Open-folder created an Explorer window for the bound synthetic session.
- Closing the main window while readiness remained “checking” left both viewers open. Closing one viewer preserved the other. Closing the last viewer ended the Python application process; no test app window or process remained.
- Native windows were resized; narrow layouts were also checked at explicit 700×780 and minimum 560×540 outer window sizes. The final compact layout retains the player controls, file actions and scrollable transcript.

## Portable package

The allowlist build retains the local Plyr assets/license, native window manager and original recording/transcription dependencies. It omits configuration, keys, recordings, model weights, test harnesses and Obsidian plugins.

A full archive was extracted to a new path containing Chinese characters and spaces. Its real `ExperienceRecorder.exe --self-check` passed, including isolated imports and private DLL paths; the native launcher opened the first-use wizard and closed normally. The packaged Python/WebView2 runtime also rendered and sought the synthetic videos from a separate data directory. Final small-window CSS was checked in that extracted runtime before the final archive was rebuilt.

This is a private evaluation candidate under the existing build policy; dependency-source archives and SHA256 inventories accompany it. No real OBS capture, Qwen service call, or company-computer test was claimed by this validation.
