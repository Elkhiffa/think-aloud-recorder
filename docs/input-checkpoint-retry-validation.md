# Windows input checkpoint contention — 0.7.7

## Diagnosis

A reported 0.7.6 capture ended with `journal_write / PermissionError / WinError 5` at the atomic replacement of `input-events.json.tmp` onto `input-events.json`. The existing writer treated the first failed replacement as permanent, stopped the input source and retained a visible failure and data gap. The diagnostic does not identify which process denied replacement; it does not establish disk exhaustion or a specific reader.

A Windows reader opened without `FILE_SHARE_DELETE` can reproduce this failure on an otherwise writable directory. Live review uses short ordinary file reads, but there is no evidence attributing this historical failure to review, preprocessing, antivirus or another process.

## Change and boundaries

Only the replacement of a fully written, flushed temporary checkpoint/journal is retried. Windows access denied, sharing violation and lock violation (5/32/33) receive at most seven attempts with 0.63 seconds of total backoff. The existing checkpoint is never deleted to force progress. The journal append and checkpoint serialization are not repeated, so a retry cannot duplicate input intervals. Routine checkpoint retries hold the writer's serialization lock while input callbacks remain available.

Other storage errors fail immediately. Exhausted conflicts follow the existing failed capture/visible warning/gap path; diagnostics include the number of replacement attempts. Permanent permission problems cannot be made writable by this change.

No historical recording, interval, gap or alignment metadata is edited. Separate overlapping gap explanations remain evidence and must be unioned when calculating missing duration.

## Alignment finding

`Session.finish_inputs(error=...)` invalidates live clock continuity and closes the OBS stop-event listener. Final measured alignment also explicitly requires a complete input capture. This explains why an input write failure yields `uncalibrated` even though `input_clock` remains in session metadata. The initial OBS duration is a coordinate anchor for input samples, not the encoder's presentation-offset calibration. The live monotonic anchor and trustworthy final stop boundary were not persisted for the failed recording, so they cannot be reconstructed from `initial_seconds` or final video duration alone. The conservative alignment behavior is retained; transient retries that succeed no longer trigger it.

## Validation

- Focused collector and session tests include transient conflicts, non-sharing errors, finite exhaustion, preservation of the old checkpoint, crash recovery that excludes an uncommitted journal tail, orderly finalization of genuinely observed inputs, and no inferred alignment after a journal failure.
- A real Windows `CreateFileW` reader denies delete sharing on an owned temporary checkpoint. The writer encounters an actual Windows conflict, synthetic input continues during the lock, releasing the reader lets the checkpoint commit, and finalization produces exactly the two expected intervals with no duplicate journal entries.
- Native hidden-target lifecycle smoke confirms registration, source/observer/writer shutdown and cleanup. The owned target is never foreground, no real user input is persisted, and this test makes no hardware-button or video-sync accuracy claim. Source checkout lacks SDL2; the smoke uses the explicitly selected, existing verified portable runtime DLL.
- Python discovery: 762 tests, 759 passed and 3 expected environment skips.
- Complete regression and packaged-app checks are recorded in ignored local delivery receipts. No OBS recording or cloud transcription is started for these checks.
