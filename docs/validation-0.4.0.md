# Notebook interface validation — 2026-09-21–22

Development continues in `F:/CodexHome/think-aloud-review` on `feat/visual-notebook`, preserving the previous standalone review and adjustable-pane changes. The old D-drive installation was not modified.

## Changes

- Warm paper colors, restrained green, larger text, shared light/dark themes and an original speech/voice mark, including native-window icons.
- A compact recording panel and expanded recent experiences; dialogs keep their navigation visible while content scrolls.
- A recording-method introduction before device setup: observation, interpretation, intended action and feelings after trying. The home header can reopen this guide without creating a settings draft.
- A split Copy button beside Open folder. The default copies the current session folder; its disclosure offers transcript JSON/video paths and document actions. Successful copy shows a check and `copied!` for two seconds without moving the video. Playback shortcuts remain functional without an on-page hint row.

## Automated checks

- Full private Python suite during this iteration: 141 tests, 140 passed, 1 skipped because Windows symlink permission was unavailable.
- Latest targeted Python checks after the review changes: 8 passed (`tests.test_review`, `tests.test_desktop_shell`).
- Latest Node UI/state and review suite: 15 passed. The added guide behavior check verifies initial introduction, draft retention on Back, device validation, cancellation without persistence and independent help access.
- JavaScript syntax and Git whitespace checks passed.

## Native WebView2 checks

Used explicitly labelled synthetic fixtures: a 120-second H.264/AAC test-pattern video and 40 timestamped transcript segments. The harness prevents actual device recording and does not call cloud transcription.

- Inspected the first-use guide, its scrollable examples and fixed footer; advanced to device setup and cancelled without saving.
- Inspected the compact home screen, shared branding and independent recording-method help in light/dark themes.
- Opened a synthetic session through the application's session list using the packaged private runtime.
- Default copy wrote the exact current session directory to the Windows clipboard. Video and transcript JSON selections wrote their respective paths. All three paths contain Chinese characters and spaces.
- Observed the check/`copied!` state and its later restoration. The button and video dimensions stayed fixed; the keyboard-hint row was absent.
- Used keyboard arrows and Enter to select and copy a transcript path. Copy controls did not start playback or seek the video.
- At the native minimum 560×540 window size, found and corrected a clipped menu. The final disclosure stays inside the window, with scrollable overflow; keyboard navigation brought the last document action into view.
- The extracted application launcher passed `--self-check` in a directory containing spaces and Chinese characters. All checked imports and native runtime DLLs came from the package; the optional local model was absent without blocking startup.
- The final delivery launcher also passed `--self-check`, reporting `F:/think-aloud-record` as its initial library.
- Closed the packaged main window through X while a viewer stayed open, then closed the final viewer through X. The test Python process exited; no source-preview process remained.

## Delivery

The final allowlist archive was verified and its manifest matched both a separate test extraction and `F:/CodexHome/ThinkAloud-0.4.0`. The latter has a local, ignored configuration initially pointing to `F:/think-aloud-record`. Configuration and recorded material are not included in the archive.

Final application archive: `dist/ready-0.4.0/ExperienceRecorder-0.4.0-windows-x64-candidate.zip`.

SHA256: `ea4d58b6d952e88992e611988d396914f662bf039f045fae9908a6c1120bce15`.

This remains a private evaluation candidate under the existing dependency-source release gate. No live microphone/screen capture, Qwen transcription, or company-computer run is claimed for this visual iteration.
