# Vocabulary snapshot refresh validation — 0.7.5

All acceptance data is synthetic. No private dictionary, source note, recording, transcript or runtime configuration is included in this change.

- Python regression: 756 tests, 753 passed and 3 environment skips.
- Front-end state/bridge regression: 42 passed, including retaining an open draft's original vocabulary revision across live refreshes.
- 13 focused tests cover exact preservation of manual terms, other presets/settings, dictionary files and historical session settings; append-only union; Qwen length and combined-count limits; changed sources/configuration; ambiguous filenames, path escape and altered plans; inactive presets; nonblocking busy admission; failed writes; idempotent retries; authentication, CLI interprocess calls and endpoint cleanup.
- Real WebView2 acceptance starts `app.run_window` with an isolated, unconfigured synthetic preset. A separate CLI process previews/applies a refresh, the ordinary UI poll receives the live snapshot, and the real desktop bridge rejects an already-open editor's stale vocabulary. Closing the last window removes the agent endpoint. This check does not assert recording/OBS readiness or call cloud transcription.

Packaged acceptance repeats that native test using staged package modules and Python, alongside the existing portable self-check. Machine-specific receipts and synthetic scratch configuration remain in the ignored local build directory.

The interface updates only explicit presets. The TXT append/provenance step remains owned by the external preprocessing workflow. Source-file changes after a refresh require another preview/apply; this is not a watcher or an automatic agent.
