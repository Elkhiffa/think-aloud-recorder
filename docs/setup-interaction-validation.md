# Setup and recording interaction follow-up — 2026-09-22

Refines the approved warm-paper UI from `78f5a72` in response to actual use.

## Delivered behavior

- Completed-step checkmarks are centered inside the circular markers.
- The method page leads with “开始录制 → 体验 + 说出想法 → 回看 + 分析问题”.
- Entering the device step focuses the preset-name input; polling does not steal
  focus or overwrite typed text.
- Empty device lists show “设置 OBS”. This explicit operation waits for its own
  successful refresh acknowledgement before filling the current draft with the
  actual Windows primary display and the enabled OBS `default` microphone item.
  Neither list order nor localized labels are used to identify the primary display.
  Unknown defaults remain empty with an explanation. Ordinary refresh, cancelled
  drafts, reopened drafts and manually changed device choices are protected.
- Transcription uses two parallel keyboard-accessible tabs, local and Qwen. New
  drafts select local; existing record-only presets require an explicit choice
  when edited. Selecting a tab does not download, upload or save configuration.
- Home has no duplicate recheck/edit links. The folder button has a subtle fill
  and ends at the gear's right edge. A fixed status region keeps all controls and
  the session list stationary across ready/checking/single/multiple-error states.
  Overflowing reasons remain available by pointer or keyboard scrolling.

## Verification

- 152 Python tests passed, including 10 new default-device/refresh tests.
- 27 Node UI/state tests passed, including late results, cancellation, manual
  overrides, failed refresh, legacy presets, keyboard tabs and focus behavior.
- 29 real Edge browser checks passed; 27 screenshots and no browser exceptions.
  The checks use the actual HTML/CSS/JS with synthetic devices and a generated
  test video. Both themes and 1240×900 / 820×620 recorder windows were checked.
  CTA, preset, gear, folder and session-list bounds remained identical across all
  tested error transitions. Review playback/scroll/split/copy regression checks
  also passed, including a 560×540 review window.
- The Windows primary-monitor reader returned two identity candidates on this
  machine in a read-only native check. Matching against OBS entries was tested
  with synthetic lists, including a primary monitor that was not the first item.
- Six native WebView2 interaction checks passed: ready state, blocker replacement,
  edit wizard, name focus, tab switching and compact scrolling with fixed footer.
  Hidden-window CapturePreview had partial timeouts; those failed attempts were
  retained. Compact native screenshots rendered, and the full browser screenshots
  provide the visual evidence. The native capture harness is not reported as an
  all-green suite. No actual OBS capture or cloud transcription was performed.

The browser's earlier canvas fixture produced an empty 110-byte WebM container.
The fixture now mounts the canvas and requests every frame explicitly; it rejects
empty media before acceptance. The successful run decoded a 102,251-byte video.
Playback assertions were retained. Earlier failed reports remain in
`work/interaction-acceptance`; final evidence is `acceptance.json` there.

## Local packages

`0.5.1-preview.2` is a private portable candidate, with the existing dependency
source/redistribution gate unchanged. The software ZIP is 308,580,371 bytes.
The 416,331-byte `ThinkAloud-preview.1-to-preview.2-update.zip` contains only nine
changed program/manifest files. It does not contain configuration, secrets,
runtime, OBS settings, recordings or models. Applying it to the exact previous
software produces all 7,028 target manifest hashes.
An isolated application of this delta retained byte-identical synthetic config,
state, model and recording markers. The updated native launcher then passed
`--self-check` from an unrelated working directory, resolving modules and DLLs
inside that installation. This does not imply that a user's installation has
already been updated.

To update the previous trial: close the recorder and its review windows, extract
the update ZIP contents into the existing `0.5.1-preview.1` application directory
(beside `ExperienceRecorder.exe`, preserving the `ui` subfolder), and allow the
program files to be replaced. Then use the original launcher. Personal settings
and the selected library remain in place. This delta targets that trial version;
for other versions, use the full portable candidate.
