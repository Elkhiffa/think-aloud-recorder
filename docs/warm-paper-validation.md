# Warm paper UI validation — 2026-09-22

Implements the approved A1 structure with the A3 selected-transcript treatment.
The product contains only the real window UI: no concept-board annotation,
component specimen or example-error panels. The recorder, preset wizard and
independent reviewer share the quote/bookmark identity, paper/ink/brick palette,
light/dark modes and compact typography described in `recorder-experience.md`.

## Scope

- Main: equal section headings, deeper recording band, aligned recording controls,
  one mutually exclusive status/error slot above Start, independently scrolling
  session list. Backend readiness continues to control recording eligibility.
- Setup: fixed step rail/header/footer, scrolling body, grouped device fields,
  file-first vocabulary, provider-specific options and fixed Bailian console link.
  Saved keys are never read into the password field or sent through the link.
- Review: fixed video and separately scrolling transcript, pale selected row,
  red timestamp and separator between the time and original words. Existing
  split-pane resizing, seeking, copy menu and offline player remain available.
- Historical operation failures produce a one-time notice after readiness has
  recovered; they cannot replace the current ready status above an enabled Start.

No capture/audio-routing, transcription pipeline, library migration or existing
user configuration changes are part of this iteration.

## Checks

- Python unit suite: 142 passed, including the bridge export and fixed-console URL.
- Node UI/state suite: 20 passed, including ready/error replacement, requests in
  progress, device checks and historical-error recovery.
- Real Edge browser: 20 acceptance checks passed with 20 screenshots. Tests load
  the actual source UI, use an explicitly synthetic native bridge and generated
  test-pattern video; unexpected external requests are blocked. Covers light/dark,
  1240×900 and compact windows, long paths, wizard navigation/cancel, vocabulary
  multi-selection, fixed wizard footer, review scroll/seek/split/copy behavior.
- Native pywebview/WebView2: 8 checks passed for recorder readiness, blocked state, setup and minimum
  window scrolling verified with synthetic bridge data. The new ICO loaded through
  WinForms. CapturePreview screenshots cover the application content only; the
  test windows automatically close.
- Independent read-only review's historical-error finding was corrected and
  specifically rechecked. No further finding in that follow-up.
- Portable `0.5.1-preview.1` candidate: 308,577,384-byte software ZIP; 7,028
  allowlisted extracted files matched their SHA256 inventory. Models, state,
  recordings, OBS configuration and encrypted keys were absent. The relocated
  native launcher ran `--self-check` successfully from an unrelated working
  directory; Python/modules/DLLs/FFmpeg resolved inside the extracted package,
  and the missing model was correctly reported as optional. This was a runtime
  self-check, not an OBS recording run.

Native video playback is not established by the native smoke: its hidden-canvas
test-video generator failed to produce playable frames. Review playback evidence
comes from the real browser test. This iteration does not claim a new microphone,
OBS capture, cloud-provider or GPU acceptance run.

## Repeating the checks

Run the supplied runtime's `python.exe -m unittest discover -s tests` and
`node --test tests/test_ui_state.js tests/test_review_ui.js` from a prepared checkout.
For browser acceptance, set `PLAYWRIGHT_MODULE` to an already installed Playwright
module if it is not resolvable by Node, then run `node tests/test_ui_browser.cjs`.
It uses installed Edge; it does not install packages or download a browser.
The report and screenshots are written under ignored `work/visual-acceptance`.

`scripts/render_brand_icon.cjs` regenerates the native ICO from `ui/brand.svg`
using the same existing Edge/Playwright setup. It emits seven PNG-backed sizes
from 16 to 256 pixels without adding an imaging dependency.

Local native evidence is under ignored `work/native-smoke*.json` and
`work/native-*.png`. These are synthetic validation artifacts, not user recordings.
Portable candidates continue to use the existing allowlist and redistribution
gate described in `build.md`; they are not a public binary release.
