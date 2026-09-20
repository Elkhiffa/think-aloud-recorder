# Experience Recorder

Windows desktop recording and transcription app. Preserve original recordings and user notes; only the independent microphone track is transcribed. Obsidian remains the primary review destination.

## Working rules
- Develop on a dedicated branch in a separate Git worktree. Do not edit the existing private portable installation.
- Never commit or package runtime configuration, credentials, recordings, transcripts, logs, model weights, or user vocabulary files. Build releases from explicit allowlists.
- Preserve two-track semantics: track 1 = desktop + microphone playback mix; track 2 = microphone only and sole transcription input.
- Do not treat process launch as recording/review success. Use OBS status and plugin acknowledgements.
- Preserve session locks, recovery, old transcript versions, user notes, and uncertain cloud submission guards.
- Model absence affects transcription only. Local model files are optional and never part of the software archive.
- No silent cloud uploads, global dependency installs, proxy changes, or Obsidian binary redistribution.
- UI must display actual state; fixtures and synthetic tests must be clearly identified. Never replace live checks with mocked success claims.
- Validate with `runtime/python.exe -m unittest discover -s tests`, plus targeted real desktop and packaged-app smoke checks. Test recording with synthetic sources only unless the user requests actual capture.
- All collaborating agents must respect assigned file ownership and preserve other agents' changes.
