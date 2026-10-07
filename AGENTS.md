# Experience Recorder

Windows desktop recording and transcription app. Preserve original recordings and user notes; only the independent microphone track is transcribed. Native WebView2 windows are the review destination. The application exits after the last window closes.

## Working rules
- Develop on a dedicated branch in a separate Git worktree. Do not edit the existing private portable installation.
- Never commit or package runtime configuration, credentials, recordings, transcripts, logs, model weights, or unapproved user vocabulary files. The two shared plain-text dictionaries documented in `vocabularies/README.md` are explicitly approved for Git; local vocabulary maintenance records and backups remain excluded. Build releases from explicit allowlists.
- Preserve two-track semantics: track 1 = desktop + microphone playback mix; track 2 = microphone only and sole transcription input.
- Do not treat process launch as recording/review success. Use OBS status and player readiness acknowledgements.
- Preserve session locks, recovery, old transcript versions, user notes, and uncertain cloud submission guards.
- Model absence affects transcription only. Local model files are optional and never part of the software archive.
- No silent cloud uploads, global dependency installs, proxy changes.
- UI must display actual state; fixtures and synthetic tests must be clearly identified. Never replace live checks with mocked success claims.
- Validate with `runtime/python.exe -m unittest discover -s tests`, plus targeted real desktop and packaged-app smoke checks. Test recording with synthetic sources only unless the user requests actual capture.
- All collaborating agents must respect assigned file ownership and preserve other agents' changes.

## Versioning
- `portable.json.version` is the single default delivery version, starting with `0.6.1` for this sequence. Use plain `X.Y.Z` for new packages and `vX.Y.Z` for new release tags; do not add preview, local, date, or machine suffixes.
- The same deliverable uses the same version on both development computers, in local installations, and on GitHub. Increment the patch number for the next delivered revision; use a minor increment for a feature milestone. Do not bump for every commit or test build.
- Keep build dates and source commit identities in separate metadata. Never replace the contents of an already released version or rewrite historical tags/packages. Preserve updater support for historical versions.
- The builder defaults to the version in its own checkout, not the runtime seed. Release preflight requires the target commit, tag, and package versions to match. An explicit numeric build override is only for controlled fixtures/reconstruction and cannot bypass this release check.
- A version bump or source push does not publish a Release, install an update, or establish runtime acceptance. Publication and local installation remain separate actions.

## Local development location
- Continue iterations and build artifacts under `F:/CodexHome`; the current worktree is `F:/CodexHome/think-aloud-review`.
- The user requested `F:/think-aloud-record` as this computer's initial library. Keep that machine-local choice in ignored runtime configuration, not portable archives.
