# Foreground recovery and dense gap review — 2026-09-26

The latest 62-minute session had zero input intervals in both the final sidecar
and its journal. Its foreground ledger remained outside the target from about
7.6 seconds until capture ended. Meanwhile the live per-event foreground gate
admitted samples, which the stale timestamped ledger rejected: 466,727 identical
zero-duration coverage gaps were written inside one long focus gap. The raw
records contain no key/button identities that could be restored.

This is evidence of disagreement between the live HWND check and the WinEvent
history, not proof of a particular game/driver suppressing an OS notification.
Review rendered the rejected samples as individual elements, and incorporated a
full-history JSON string into each render key. Both made this history expensive
to zoom/render.

## Change

- The independent foreground observer checks the actual foreground HWND on each
  acknowledged marker. A disagreement must persist for 64 ms before it adds a
  prospective transition. It never backdates newly acquired authorization or
  recovers previously discarded input. Existing per-event HWND/process checks,
  marker watermarks, transition exclusion bands and late-event revocation remain.
  Resumed holds are sampled again after the recovered boundary.
- The writer records a count inside an existing focus gap instead of persisting
  one point for every rejected input. Other adjacent uncertain samples are
  grouped until a trusted input/transition/checkpoint separates them.
- Review compacts historical redundant points into their covering global gap,
  keeps the rejected-sample count, and labels the inconsistent foreground range
  as missing reliable input. Controller-only disconnects cannot cover missing
  keyboard input. Different reasons and successful ranges stay separate. Startup
  preparation markers remain distinct for conservative initial seek handling.
- Visible gap marks are clipped and combined at pixel resolution. Exact logical
  gaps remain separate from their visual bands. Render keys use a small revision
  counter, and wheel-driven rebuilds run at most once per animation frame.

## Verification

- Python discovery: 516 tests, 513 passed, 3 expected opt-in skips.
- Production Edge input/review regression: 31 checks passed. The first run found
  an old width-only geometry expectation, superseded by the earlier source-aspect
  fit change. It now verifies the source ratio, containment and unchanged geometry
  across modes; no production geometry code changed in this fix.
- Synthetic 466,727-sample legacy history: compaction 75.9 ms, page load 1.67 s,
  160 wheel events across 20 frame batches 318 ms, at most one gap element, no
  browser errors or zoom long tasks. These are measurements on this machine,
  not universal latency guarantees. Dense uncovered points also collapse at
  pixel resolution without modifying logical intervals.
- An owned native test window registered the actual Raw Input/WinEvent/SDL paths.
  One deliberately stale foreground transition recovered automatically. Desktop
  test actions W, A, Escape, mouse click and movement produced 10 intervals and
  5 gaps. 11,945 markers were acknowledged, both threads exited and the hook was
  removed. No game video/audio was captured. This is desktop-generated input
  acceptance, not physical-controller or long gameplay timing acceptance.
- Read-only conversion of the actual affected history took 2.60 s. Its derived
  review payload contained 5 gaps (including preparation), zero invented inputs,
  and the count of 466,727 discarded samples. Standalone HTML shrank from
  64,723,789 bytes to 295,431 bytes without changing the source sidecar/journal.

Ignored detailed receipts, synthetic test recordings and local previews are in
`work/input-gap-recovery`. The initial native harness could not find SDL in the
development checkout; the completed run explicitly used the already installed
private SDL runtime. No dependency was downloaded or globally installed.

## References

- [SetWinEventHook and queued out-of-context delivery](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwineventhook)
- [GetForegroundWindow and transient null handles](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getforegroundwindow)

The local stale-ledger evidence and recovery behavior above are our diagnosis and
implementation; the references do not establish the cause of the missing event.

## Confirmed scope change later in this task

The user then explicitly chose complete keyboard/mouse/controller capture during
recording, with independent target-window state and display-time filtering.
Production now selects `recording_scope: all`. Physical intervals remain intact
across foreground changes, including held controls and background controller
events. The journal stores window-context records separately; final sidecars
publish `window_states` independently of `gaps`. Missing/late window observations
make the context unknown and do not revoke physical input. Video-clock cutoffs,
device disconnects and actual collector errors still have their own semantics.

The viewer defaults to all inputs and offers a foreground-only display filter.
It clips displayed holds to known foreground spans without editing saved facts,
shows the window state at the playhead, and does not hatch background operation
as a capture gap. Preset help describes the new session-wide scope. Old recordings
retain their historical meaning and cannot gain inputs that were never saved.

The final scope suite passes 522 tests (519 passed, 3 opt-in skips), and all 32
production Edge review checks pass, including filter toggling without moving the
video or deleting background inputs. New tests cover checkpoint recovery, held
inputs across focus changes, observer failures, video cutoffs, and context export.
The earlier native key/mouse receipt belongs to the first repair. A subsequent
native all-input window test was stopped with the user's physical Escape key
before capture was started; no further desktop control was attempted. Consequently
the new all-input mode has automated/backend/browser validation, but no completed
physical-background-input acceptance from that stopped test.

## Installed acceptance — 2026-09-27

The local transactional installer completed version
`0.6.0-preview.6+local.20260926.3` at `F:/ThinkAloud`. Its packaged self-check
passed, and before/after inventories confirmed that configuration, credentials,
vocabulary and original session files were preserved. The update kept its previous
version backup. Only the affected session's derived standalone review was then
rebuilt separately: 298,882 bytes, 5 compacted gaps, zero invented input intervals.
The earlier standalone review was backed up as well.

After the user resumed the work, Computer Use operated an owned test window
loading the installed capture modules. During a 39.95-second capture, a second
window put the selected target in the background. Background ArrowLeft, mouse
clicks and mouse motion were retained, alongside the earlier foreground F8.
Seven intervals were saved; the only two capture gaps were startup and final
watermark boundaries, with no focus gaps. Separate window context correctly
reported the foreground/background transition. All capture threads exited and
the WinEvent hook was removed. A desktop-generated F9 attempt was not observed
in the receipt and is not counted as passing input acceptance. This verifies
background keyboard/mouse persistence; it is not a physical-controller or
long-gameplay acceptance run.

The full 522-test run and 32 browser checks above passed before installation;
two subsequently added targeted cases also passed, covering production scope
selection and raw keyboard/mouse decoding while the target is in the background.
The final synthetic gap stress receipt measured compaction at 62.7 ms, loading
at 1.23 s, and 160 wheel events across 20 frame batches at 301 ms, with at most
one visible gap element and no recorded zoom long task.

Computer Use also opened the installed main window and the actual affected
62-minute session in its native WebView2 review. The main window showed the
installed `.3` version and all 15 library sessions. Review loaded the video,
explicitly reported that this old clip has no saved valid inputs, and changed
the timeline from 1.0x to 0.5x and 0.3x in two wheel actions without reproducing
the prior long freeze or mass of repeated gap elements. Playback remained paused
at the same position. The actual review was left open for inspection.
