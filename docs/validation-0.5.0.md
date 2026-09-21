# Field-notes interface validation — 2026-09-22

Development remains in `F:/CodexHome/think-aloud-review` on `feat/visual-notebook`. The installed `frontend-design` skill informed the direction and critique in `docs/design-fieldnotes.md`. The previous private D-drive installation was not modified.

## Changes

- The recording card sits above the full-width experience list. The list heading is static; individual sessions retain expandable secondary actions and a direct Review button.
- New preset is above the selector and aligned with its right edge. A 48 px gear button beside the selector has the same height. The recording-method help includes an info icon and sits inside the recording card, right-aligned with Start.
- The saved library path has its own wrapping row. The main window starts at 1240×960; setup groups device fields into two columns with fixed navigation and footer controls.
- New presets explain what a preset saves and that the same game/devices usually need configuration only once. Editing an existing preset starts at devices and exposes only three settings steps; the method guide remains available separately.
- Warm paper/green colors, readable Windows system type, shared light/dark themes and quiet timestamp gutters extend the notebook identity to review. The draggable panes, mature player, independent review windows and split-copy actions remain available.

## Automated checks

- Full private Python suite during this iteration: 141 tests, 140 passed, 1 skipped because Windows symlink permission was unavailable.
- After the final window/setup-flow changes, 5 targeted desktop/window-lifecycle Python tests passed.
- After the final preset layout/copy changes, 16 Node UI-state and review tests passed. The setup behavior check covers edit-mode step boundaries and retention of the new-preset introduction.
- JavaScript syntax and staged/unstaged Git whitespace checks passed.

## Native WebView2 checks

Used explicitly labelled synthetic fixtures, including a 120-second H.264 test-pattern video and 40 timestamped transcript segments. The preview harness prevents actual device recording and does not call cloud transcription.

- Inspected the vertical home layout in light/dark themes, the static list heading, expanded session actions and the long path row.
- On the final layout, confirmed New preset aligns to the selector, the gear matches the selector height, and the info/help control aligns to Start.
- At the initial window size, inspected the complete first-use introduction and the new-preset definition/device page. Device controls, Refresh, Cancel and Next were visible without scrolling.
- Opened the final gear control: editing begins on devices, with only three steps and no method-guide step or Back button on the first page. Cancel returned to the unchanged main screen.
- Inspected review in light/dark themes, the timestamp/text gutter and the visible synthetic-test label. At the 560×540 minimum, the player, folder/copy controls and scrollable transcript remained available; the copy menu stayed inside the viewport.
- In the final packaged preview, clicked the default session-folder copy action and observed the check mark and `copied!` text, then the restored icon/text with unchanged button dimensions. Path correctness and other menu selections were checked in the preceding 0.4.0 validation; this iteration preserves that implementation.
- Verified last-window shutdown during native testing; closed the owned synthetic preview windows again after the final checks.
- Both the final delivery launcher and a package extraction under a path containing spaces/Chinese characters passed `--self-check` with exit code 0 and `ok: true`. The delivery reported `F:/think-aloud-record` as its library.

## Delivery

The archive manifest contains 7,025 files. All hashes matched both the native-preview extraction and `F:/CodexHome/ThinkAloud-0.5.0` after the final update; their existing local configurations were preserved byte-for-byte. Runtime settings, credentials, recordings, transcripts, test fixtures and local models are not included in the allowlist archive.

Application archive: `dist/delivery-0.5.0/ExperienceRecorder-0.5.0-windows-x64-candidate.zip` (328,156,365 bytes).

SHA256: `5492e22d69d21f8aa2ed467373f54b54f441017cf99916b23d60f5435800b504`.

Dependency-source archive: `dist/delivery-0.5.0/ExperienceRecorder-0.5.0-windows-x64-candidate-dependency-sources.zip`.

SHA256: `b9bf1e03db19f4a11eed97757d670b5c17f5e2938dd5d57d0be1a81a3a2dd57e`.

This remains a private evaluation candidate under the existing dependency-source release gate. No live microphone/screen capture, Qwen transcription or company-computer run is claimed for this visual iteration.
