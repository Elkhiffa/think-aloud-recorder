# Think Aloud interface direction — 2026-09-22

Apply the globally installed Anthropic `frontend-design` skill to an existing Windows tool for recording observations while playing a game. The user's approved direction is a warm, focused notebook tool. Recording must take little attention; the library and the speaker's original words deserve most of the workspace.

## First pass

Core colors: canvas `#EEF0EA`, paper `#FAFBF7`, ink `#293A32`, quiet text `#596A5E`, fern `#2D6C58`, selected paper `#DDE8DD`. Dark mode maps these roles to graphite/green paper with readable pale text. Red is reserved for recording/stop and failures.

Type: Bahnschrift for the Think Aloud wordmark and elapsed timer, chosen for the compact, sturdy lettering of a recording instrument. Microsoft YaHei UI for Chinese controls and text, keeping Chinese legible offline on Windows. Body/actions use 15–16 px, contextual text 13–14 px, headings 20–28 px. Timestamps use the body family with tabular digits. No extra downloaded fonts or runtime network requests.

Two possible layouts:

```text
A. A vertical notebook
  wordmark                         help/theme
  large capture sheet
  experience list

B. A recording station beside the notes
  wordmark                         help/theme
  capture controls   | experience list
  preset / start     | search / filter
  actual status      | title, time, review
  library location   | more experiences...
```

The first implementation used B. After native inspection, the user preferred A: the side panel squeezed preset names and the library path. The final design uses a compact, full-width recording strip above the experience list at every width. Arrange the preset and capture action across the strip, and give the saved path its own wrapping line. All statuses and counts remain actual backend values.

## Brief review before implementation

- Keep A compact by aligning the recording controls across the upper strip; avoid the old tall, vertically stacked capture card. Give remaining height to the always-visible list.
- Remove the decorative eyebrow on the capture panel and avoid repeated outlined cards. The main action carries the visual weight; row separators encode separate sessions.
- Keep the experience-list title static and its contents always visible. Only individual session rows expand to reveal secondary actions; Review remains directly available.
- The four prompts in the method guide are alternative ways to speak, not numbered steps. Present them as labelled excerpts; reserve numbering for the actual setup sequence.
- In review, each timestamp forms a gutter next to its original words. This expresses the product's distinguishing relationship—speech tied to a moment—while exposing more text.
- Compact the review header and the file toolbar. Keep the requested split-copy interaction and its fixed-size two-second feedback. Preserve draggable panes, independent review windows, player controls and last-window exit.
- Use motion only to answer an action: expanded details, focus, pressed controls and copy confirmation. Respect reduced-motion preferences. Avoid decorative waveforms that could be mistaken for a live audio meter.
- Existing-preset editing has three settings steps and never enters the recording-method guide. New presets keep the guide; the recording-area help includes an info icon. Arrange the four device fields in two rows so the initial window exposes the microphone, refresh action and navigation without scrolling.

## Implementation and critique

Use native screenshots of synthetic fixtures to inspect the everyday screen, setup, review, narrow dimensions and dark theme. Keep original data and settings out of test builds. Record the final checks in a separate validation note.

After user review, New preset moved above the selector, aligned with the selector's right edge. Edit became a 48 px gear button beside the 48 px selector. The recording-method help moved inside the capture strip at the capture card's upper-right corner, with its right edge aligned to Start. The readiness label and primary button share a centerline; the selector and primary button share a baseline and height. This keeps controls belonging to each task together instead of distributing them across a single crowded row.

The new-preset device page defines a preset as saved recording settings and explains that the same game and devices normally need setup only once. Returning users can select that preset directly; the adjacent gear makes later changes discoverable. Existing-preset editing uses a shorter introduction and omits this first-use explanation.
