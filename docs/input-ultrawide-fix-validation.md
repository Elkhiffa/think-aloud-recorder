# Local input and ultrawide repair — 2026-09-25

## Findings and changes

The reported recent recordings had input capture enabled and a completed sidecar,
but every saved interval was an Xbox trigger. No button or stick intervals existed
in the canonical input files. Playback cannot reconstruct those missing events.

The SDL 2.32.10 Windows Raw Input controller backend uses HID reports for normal
buttons/sticks and separately correlates XInput trigger data. Missing HID reports
therefore fit the observed trigger-only symptom. This is a compatibility diagnosis,
not a hardware reproduction: no physical controller was connected during validation.
On Windows the recorder now disables **SDL's controller Raw Input backend** before
initialization and enables its XInput path. The keyboard/mouse Raw Input listener,
DualSense HIDAPI support, foreground ownership gates and timestamp handling remain.

References: [SDL controller hints](https://github.com/libsdl-org/SDL/blob/release-2.32.10/include/SDL_hints.h),
[Windows Raw Input controller driver](https://github.com/libsdl-org/SDL/blob/release-2.32.10/src/joystick/windows/SDL_rawinputjoystick.c).

The reported 3440×1440 source had been fitted into a fixed 1920×1080 recording.
OBS now waits for actual source dimensions and fits the encoding size within the
selected preset's limits, using even pixels. A 3440×1440 source with the balanced
preset produces 1920×804. Geometry is retained in session metadata. Missing source
dimensions fail before recording rather than guessing a canvas.

The player slot now fits both available width and height at the visible source
aspect ratio. It can be narrower than the manually chosen left column when height
is limiting. Divider behavior and the operation panel's column width are preserved.

An optional, bounded `video-display.json` describes a verified crop of baked-in
letterboxing in an old clip. It changes only presentation; MP4/MKV and timing are
unchanged. Wrong-source dimensions invalidate the crop. The path menu can show the
original frame again. Fullscreen placement also preserves the visible aspect.
This is not automatic scene-based cropping or recovery of missing image content.

## Validation

- Python discovery: 500 tests, 497 passed, 3 expected opt-in skips.
- Node UI/state checks: 40 passed.
- Real Edge layout: 13 checks passed, with browser-encoded 3440×1440, 16:9,
  portrait and letterboxed fixtures. Covers window sizes, divider adjustments,
  transcript scrolling, restored original frame and fullscreen crop geometry.
- Native hidden-target input lifecycle: passed. No unrelated input persisted;
  registrations, observer and threads were released. Hardware buttons not tested.
- Independent installed-runtime self-check: passed.
- Isolated OBS recording of generated 3440×1440 video: actual output 1920×804,
  two audio tracks, successful remux and owned OBS cleanup. No microphone/window
  capture or cloud transcription. A first harness run recorded successfully but
  its screenshot export required unavailable Pillow; the corrected FFmpeg-based
  harness completed successfully. This was a harness dependency issue.
- Native WebView2 from the independent package: opened its synthetic session,
  displayed the full-width colored frame without player bars and played it using
  the actual control. Synthetic sessions remained outside the user's library.

Local evidence is ignored under `state/input-diagnosis-20260925`,
`work/review-aspect` and `F:/CodexHome/ThinkAloud-repair-20260925`.
Physical button/axis acceptance still requires a short recording with the user's
controller connected and the selected game in the foreground.

## Local deployment

Installed `0.6.0-preview.6+local.20260925` through the existing verified updater,
with eight managed-file replacements, a retained rollback transaction and a
passing installed-launcher self-check. The six changed runtime/assets match the
tested source bytes. Runtime configuration, protected credentials and vocabulary
hashes are unchanged. Original session media size/timestamps and non-media hashes
are unchanged across the eight real sessions.

The three recent, individually sampled letterboxed recordings now have bounded
display sidecars for their 1920×804 visible region within 1920×1080 files. Their
standalone review pages were regenerated with the original pages backed up.
No original video, input history, transcript or notes were changed.

The actual updated installation opened the latest real session and sought to
approximately 04:57. Native WebView2 displayed the full visible game region,
restored the original letterboxed frame on request, and returned to the cropped
view. The library listed all eight existing sessions. This validates playback and
deployment, not physical controller input.
