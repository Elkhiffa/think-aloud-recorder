# Adjustable review panes validation — 2026-09-21

This extends the standalone review checks in `validation-0.3.0.md` with a draggable divider and independent saved preferences for side-by-side and stacked layouts.

## Automated checks

- Private Python runtime: `python.exe -m unittest discover -s tests` — 141 tests, 140 passed, 1 skipped (Windows symlink permission).
- `node --test tests/test_review_ui.js tests/test_ui_state.js` — 14 passed. Divider assertions include cramped dimensions, both bounds and restoring the preferred ratio when space becomes available.
- Preference tests verify reopening, merging the two layout axes across viewers, invalid input, corrupt preference files and unchanged session contents.
- JavaScript syntax and Git whitespace checks passed.

## Actual Windows UI checks

Used the same explicitly labelled synthetic 120-second H.264/AAC video and transcript fixtures. No live recording or cloud transcription was performed. The test harness holds device readiness at “checking” and does not query OBS.

- In a side-by-side review, dragging changed the video share from 59% to approximately 44%. A focused-divider Right key increased it by 2 percentage points without seeking the video.
- Reopening restored the saved horizontal preference. Double-clicking restored the default 59% share. Player controls remained usable with a narrow video pane.
- The final 0.3.1 archive was extracted to a new directory with Chinese characters and spaces. Its actual `ExperienceRecorder.exe --self-check` passed.
- In that extracted private WebView2 runtime, a 700×960 review window displayed stacked panes. Dragging the horizontal divider upward changed the share from 54% to approximately 42%; the preference file stored `rows: 0.41531528403484863`.
- The transcript scrolled independently, leaving the video and divider in place. Reopening restored the 42% share.
- Maximizing switched to the default side-by-side share. Restoring the window recovered the saved stacked share without moving playback from 00:00.
- Closing the main window through its X left the viewer open. Closing the final viewer ended the test Python process.

## Delivery

The 0.3.1 allowlist build excludes runtime settings, credentials, recordings and test fixtures. The archive and a separate clean delivery extraction were checked against the package manifest.

Application archive SHA256: `20b92029f473344f380cacdd5717531a107a8308c8398f884f48996a1eae91ae`.

This remains a private evaluation candidate under the existing dependency-source release gate. No company-computer test or live capture/transcription result is claimed.
