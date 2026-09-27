# Idle OBS source-lifetime crash — 2026-09-26

OBS 32.2.2 crashed during idle device polling, after the most recent recording
had already stopped normally. Its crash report initially named `w32-pthreads.dll`.
The matching official release PDBs resolve the stack to:

`pthread_mutex_unlock → signal_handler_disconnect → OBSSourceLabel destructor → SourceTreeItem destructor`

The old readiness path created three disabled temporary inputs every five seconds
and removed them immediately after reading their property lists. OBS's log showed
source-tree additions still being handled after the inputs had been removed.
The stack and timing implicate asynchronous source-label cleanup during this
rapid source churn. They do not indicate damaged recording media or a Qwen fault.

## Change

Routine readiness now queries only OBS's existing status/profile/collection and
reads live Windows device identities. Explicit device refresh uses the same
native inventory. Neither path creates or removes an OBS input, starts capture,
or activates a microphone audio client.

- Microphones: active Core Audio capture endpoints, read-only friendly names and
  the communications default; all COM interfaces and allocated values released.
- Windows: visible eligible windows with the existing OBS title/class/executable
  escaping. Duplicate identities remain ambiguous and are never deduplicated.
- Displays: monitor interface IDs with the same display-name fallback as OBS.

The existing operation lock, foreground-generation cancellation and fresh
recording-status checks remain. Recording start still checks the selected input
against OBS's own property list and verifies actual source dimensions before
starting. Availability enumeration is not a guarantee that capture will succeed.

The new module is explicitly included in the portable build allowlist.

## Evidence

- Full Python discovery: 509 tests, 506 passed, 3 expected opt-in skips.
- A separate complete portable installation passed 205 real idle checks and two
  synthetic recording/stop cycles. Source lists were unchanged by every group
  of checks; no temporary readiness inputs or crash reports appeared.
- Idle checks retained the same process handle count, 290 before and after.
  The initial harness compared handles across recording initialization as well,
  which mixed unrelated allocations into its assertion. The corrected check
  measures inventory-only growth after warmup and garbage collection.
- Both synthetic recordings retained 1920×804 ultrawide output and two original
  audio tracks. The review MP4 decoded successfully. The owned test OBS closed.
- A complete packaged-launcher self-check passed. Tests used generated media;
  device inventory read identities only and did not record real devices.

The actual incident was not intentionally reproduced against the user's install.
Validation demonstrates removal of the triggering source mutations and successful
recording afterward; it is not an overnight stability guarantee.

Ignored local evidence is under `state/obs-crash-20260926` and
`F:/CodexHome/ThinkAloud-repair-20260926`. Runtime settings, credentials, logs,
device identities and recordings are excluded from the source change/package.

## Local deployment

The verified package was applied to `F:/ThinkAloud` as
`0.6.0-preview.6+local.20260926` through the existing transactional updater.
The previous files and rollback entry remain under
`F:/CodexHome/ThinkAloud-repair-20260926/transaction`. All six installed file
hashes matched the package; the four changed source files matched this worktree.
The installed launcher self-check passed.

After restart, the native main window exposed the new version, the original
`F:/think-aloud-database` location, and all 15 existing sessions. Configuration,
credential and vocabulary hashes, all original session file sizes/timestamps,
and non-media session file hashes remained unchanged after deployment and restart.
The most recent 62-minute recording stopped normally before the crash, and its
review MP4 decoded through the end.

Final foreground activation could not be completed: the desktop automation helper
returned `failed to activate captured window` on the initial attempt and one fresh
window-selection retry. No further UI input was sent. The actual installation
was left running without starting a real recording; foreground readiness remains
to be observed by the user. Recording/stop and repeated idle-check acceptance
above refer to the isolated complete package, not a claimed live game capture.

## References

- [Official OBS 32.2.2 release and matching symbols](https://github.com/obsproject/obs-studio/releases/tag/32.2.2)
- [OBS WASAPI device enumeration](https://github.com/obsproject/obs-studio/blob/32.2.2/plugins/win-wasapi/enum-wasapi.cpp)
- [OBS window identity encoding](https://github.com/obsproject/obs-studio/blob/32.2.2/libobs/util/windows/window-helpers.c)
- [OBS monitor property IDs](https://github.com/obsproject/obs-studio/blob/32.2.2/plugins/win-capture/duplicator-monitor-capture.c)
- [Windows endpoint enumeration](https://learn.microsoft.com/en-us/windows/win32/api/mmdeviceapi/nf-mmdeviceapi-immdeviceenumerator-enumaudioendpoints)
