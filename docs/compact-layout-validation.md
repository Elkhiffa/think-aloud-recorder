# Compact portable layout validation

Date: 2026-09-24. Branch: `feat/compact-portable-layout`.

## Scope

Installation root contains the branded EXE, `app/`, and `vocabularies/`.
Source checkouts remain flat. User libraries stay external or retain their existing
installation-relative meaning. This change does not alter recording formats,
transcription providers, input capture or review presentation.

## Evidence

- Full Python suite: 427 tests executed, one existing platform/privilege skip;
  no failures. Subsequent recovery and compact release preflight additions were
  validated separately (9 compact migration/path tests and the compact release
  commit/runtime binding case passed).
- Native branded launcher passed under a Chinese path containing spaces, from
  an unrelated working directory. Normal self-check did not initialize settings.
- Fresh compact package: real OBS recorded synthetic color plus silent audio;
  two raw audio tracks were present. Playback media was ready before processing.
  The private background process completed the silent-microphone path without
  downloading models or uploading to a provider.
- Native WebView2 main window loaded, native review acknowledged readiness,
  video readyState reached 4 and seeking to one second succeeded.
- Closing the native main window ended its owned OBS; subsequent process
  inventory found no processes under the validation package. No OBS crash files.
  The installation root still contained exactly the three intended entries.
- Synthetic migration tests cover protected-data preservation, unknown files,
  rollback after partial moves and failed self-check, config/vocabulary changes
  after preparation, model path handling, invalid recovery journals and missing
  backups. Independent read-only review found no remaining reproducible blocker.
- Update tests cover flat and compact packages, same-layout updates, rollback,
  helper bootstrap/recovery paths, outer process ownership and inner state paths.

The native recording used synthetic sources only. This is not new acceptance of
physical microphones/controllers or cloud transcription accuracy. No Release or
GitHub push is part of this change. The migration backup does not copy the external
user library; the library is not a migration target.
