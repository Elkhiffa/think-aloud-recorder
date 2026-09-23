# Portable update validation — 2026-09-23

Scope: manual release checks, package validation, idle-only installation,
application/review window closure, same-directory software replacement, recovery,
and preservation of private files. No CI changes or public release was performed.

## Accepted candidate

- Version: `0.6.0-preview.4` (local candidate, not a public release).
- Software ZIP: `ExperienceRecorder-0.6.0-preview.4-windows-x64-candidate.zip`.
- Size: 309,281,219 bytes.
- SHA256: `d43bfa722c1316e407b46108086fe6504be8186560c4689857b71c93c93525ca`.
- All 7,042 manifest entries and 53 current application/source assets matched.
- No models, runtime configuration, credentials, recordings or user vocabulary
  files were included. The bundled UIUX vocabulary remains an explicit asset.
- The extracted native launcher passed its private-runtime environment check.

## Automated and desktop checks

- Python suite: 312 total, 311 passed, 1 explicitly opt-in native input-capture
  test skipped. Summary: `Ran 312 tests in 40.696s; OK (skipped=1)`.
- UI state tests: 38 passed. Browser suite: 43 passed; after the final recovery
  field alignment, all 12 update-specific browser scenarios passed again.
- Real packaged WebView2 windows: 8 checks passed, including recording-preset
  focus, early review, session rename synchronization, playback preservation,
  input timeline display and the manual update bridge action.
- A real GitHub request reported no published Release. Opening the dialog did
  not initiate a network check; the explicit button did.

The UI browser scenarios use a synthetic bridge, including download progress,
failure and recovery states. The desktop scenario uses the real updater for the
manual GitHub check; recording/session data remain synthetic. These are not
claims of physical microphone/controller or cloud-transcription acceptance.

## External helper and preservation

The actual packaged Windows Python and installer were exercised against a full
extracted `0.6.0-preview.3` candidate in a disposable directory with synthetic
private files. Six checks passed:

1. The old native launcher initialized the disposable installation.
2. After the helper acknowledged readiness, the live parent still blocked all
   file replacement; the parent then exited naturally.
3. The independent helper installed `0.6.0-preview.4` and its environment check
   passed. New managed files matched the package inventory.
4. Config bytes, synthetic encrypted-secret bytes, a partial model, user-edited
   built-in vocabulary, custom vocabulary and unknown personal files survived.
5. The actual external `--recover` command restored the previous software.
6. An injected post-install environment-check failure restored all previous
   managed software and preserved the same private files.

These helper checks used `--no-launch`. New-window readiness acknowledgement and
the coordinated close flow are covered separately by the lifecycle tests; the
real desktop checks above exercise packaged windows. A public network download
followed by automatic restart has not been tested against a published Release,
because the repository has no Release yet.

Independent adversarial checks also covered a new personal file appearing just
before replacement, cancellation during interrupted recovery, repeated helper
launch attempts, process interruption at replacement boundaries, and unconfirmed
cancel after review-window closure failed. All demonstrated defects were fixed
and the counterexamples rechecked. The main window stays available for retrying
cancellation rather than allowing an unrevoked helper to install after exit.

## Remaining publication boundary

The existing dependency corresponding-source gate remains in force. Online
updates reject candidate packages and incomplete public-source metadata. Resolve
the documented source gaps in `build.md` before publishing runnable assets; do
not rename this candidate or toggle redistribution flags to bypass that gate.

## Authorized existing-install bootstrap

An existing `0.6.0-preview.1` directory, which had no updater, was upgraded in
place to this candidate after a complete verified backup. The one-time maintenance
plan replaced 31 application, UI, vocabulary, documentation and metadata files;
it replaced no executable, runtime, OBS or controller-library files. One old OBS
process could not be confirmed terminated and was left untouched. This does not
relax the production updater's requirement for all installation processes to exit.

After installation, all new managed files matched the candidate manifest, the
native environment check passed, and 7,341 existing non-replaced files retained
their hashes, including the configured preset, encrypted credential and personal
vocabularies. External library paths were not moved. Python-generated caches,
lock files and updater-owned result records are excluded from that private-file
preservation count.

The first maintenance attempt classified an interpreter-generated cache refresh
as a private-file change and successfully rolled back. Its evidence and backup
were retained; the corrected cache classification was used for the successful
retry. This was a maintenance-harness correction, not a product-code change.
No live recording or forced OBS shutdown was performed during this upgrade.
