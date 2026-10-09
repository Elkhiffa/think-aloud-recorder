# Saved preset device discovery

Source-review checkpoint on 2026-10-09: correction validated within the scope
below on `fix/preset-device-discovery`, based on `5275ff2` (0.7.7), for delivery
as 0.7.8. At this checkpoint the correction was not installed or published. The
private recorder was recording during diagnosis and was not restarted,
reconfigured or used for test capture. Installation and source push were
subsequently authorized; their acceptance results must be recorded separately.

## Observed problem and cause

The saved game window and default microphone were available to native Windows
identity enumeration. The current game window had a different transient window
class from the saved selection; the existing executable/title matcher already
resolved this uniquely. No new fuzzy-matching rule was needed.

Opening the old preset dialog did not request devices. Its initial empty cache
was rendered as missing devices, while the service's normal discovery first
required an available, idle OBS connection and the recorder's dedicated profile.
The explicit “设置 OBS” action connected/launched the engine and then populated
the list. That action is not a Windows authorization API. Empty-cache setup also
unconditionally initialized the main monitor/default microphone, including when
editing a saved preset.

These are confirmed dependency and presentation defects. The exact reason the
original automatic OBS startup did not complete is not established by the
available evidence. An absent Windows prompt is not evidence that a new
authorization occurred or was required. This change does not alter firewall
rules, automatic launch policy, or capture authorization.

## Corrected behavior

- Opening settings automatically queries native device identities independently
  of OBS. Explicit refresh uses the same identity-only API.
- Reading, failed, cached, missing, ambiguous and uniquely matched results are
  distinguished. Unknown evidence does not become a missing-device claim.
- Existing saved and draft choices survive reads, engine recovery, cancellation
  and late responses. Defaults apply only to an explicit successful first
  refresh of a new, empty, untouched draft.
- OBS connection/configuration, uncertain recording ownership and failed/stale
  readiness have a separate full-check action. Identity reads cannot recover
  recording ownership or bypass the readiness check before Start.
- Active recording, unknown ownership, conflicting foreground operations and
  closing retain their service guards. No identity query samples audio, opens a
  capture source, writes configuration, starts OBS or starts recording.

## Verification and evidence limits

The full Python suite completed with 773 tests: 772 passed, one skipped, in
296.729 seconds. After the recovery-guidance wording update, the targeted desktop
service and bridge-export suites passed all 143 tests in 21.781 seconds. The
skipped native-input smoke requires explicit opt-in. It was not enabled while
the user's recording was active.

The production HTML/CSS/JavaScript was exercised in headless Edge with synthetic
bridge snapshots. Tests cover saved-selection preservation, errors, empty lists,
ambiguous matches, late requests, cancel/reopen, new-draft defaults and compact
dark layout. Independent engineering and UX review found an uncertain-recording
recovery dead end in the first revision; the recovery action and its regression
coverage were added before delivery. UX also requested success-consistent
feedback and prevention of repeated refresh while a read is running; both were
implemented and rechecked. Final independent engineering and UX verdicts are
`pass_with_notes`, with all three UX findings resolved and no remaining
blocking/high engineering finding in the reviewed scope.

Final frontend checks passed: 46 state tests; 14 dedicated Edge inventory and
recovery scenarios; existing recorder 19, first-use 3, vocabulary 4, device 4 and
window 6 checks. The first final first-use attempt was blocked before page load
because its temporary server received port 6666, which Edge rejects. That
failure is retained; the unchanged test passed using a newly allocated port.

A separate local acceptance used the production UI and `DesktopService` with
real Windows identity enumeration, isolated configuration and a synthetic engine
failure. Opening and refreshing the saved preset uniquely matched the running
game and found the default microphone. Saved and draft IDs stayed unchanged.
The harness rejected all OBS transport calls; none occurred. Both isolated and
private configuration hashes remained unchanged. This proves live identity
discovery through the service/UI boundary; it does not prove actual installed
WebView2, packaged application, OBS recovery or recording acceptance.

Local evidence is retained under ignored `work/` directories:

- `preset-device-validation/full-python-run1.log`
- `preset-device-validation/targeted-python-run2.log`
- `preset-device-validation/browser-evidence/`
- `preset-inventory-native-smoke/run-3/` (first successful cross-boundary identity check)
- `preset-inventory-native-smoke/run-4/` (final frozen UI, including success feedback)
- `ux-independent/` (independent rendered-state observations)
- `preset-device-investigation/installed-before.json` and `installed-after.json`

The first two native harness attempts are preserved: one lacked a public model
manifest fixture; one used a fetch transport rejected by the production CSP.
The successful harness used the native-style exposed bridge without weakening
CSP. These failures are test-harness results, not hidden product successes.

## Remaining delivery gate

At the source-review checkpoint, the private 0.7.7 installation was unchanged.
Real native WebView2 and packaged-app checks, engine recovery and synthetic
recording acceptance were still pending. Do
not infer that the installed issue is resolved from source or browser tests.
The new `tests/test_preset_inventory_browser.cjs` and this validation note are
part of the source delivery. Apply the separately versioned update only after
the active recording is finished and installation is authorized; preserve
settings and recordings, and verify installed behavior without overwriting
historical releases. A GitHub source push does not publish release assets.
