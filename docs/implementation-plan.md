# Desktop implementation scope

The recording engine and isolated transcription worker are preserved. The desktop
shell uses local HTML/CSS/JavaScript in WebView2, with an explicit method allowlist
between the frontend and Python. Obsidian remains the primary review application.

The current UI contract is [recorder-experience.md](recorder-experience.md):
setup wizard, complete named recording presets, a minimal daily recording screen,
and backend-verified start eligibility with specific errors.

Local Whisper weights are separate from the portable software. A pinned manifest,
full integrity verification, restartable downloads and import-by-reference keep
model ownership independent of software updates.

Public source excludes credentials, configurations, user libraries, recordings,
logs, models and custom vocabularies. Binary artifacts use the build allowlist and
include license/source materials for their actual dependencies. Dependency source
status is recorded in the build manifest, not inferred from application tests.

Validation combines focused unit/regression tests with synthetic OBS capture,
track isolation, local transcription, version/note preservation, session export,
Obsidian plugin acknowledgements and a real extracted portable desktop launch.
Synthetic evidence does not establish live microphone hardware quality or cloud
service availability. No cloud audio upload is part of agent validation.
