# Think Aloud notebook direction

The subsequent layout refinement is documented in [design-fieldnotes.md](design-fieldnotes.md).

The application records the user's thinking alongside the experience. Its identity is a speech bubble with three voice strokes, warm paper surfaces and a restrained green accent. The mark appears in the home header, review header and native application windows.

## Visual rules

- Use 15–16 px for regular content and actions, 13–14 px for supporting text, and a small set of 18–26 px headings. Smaller windows reduce spacing rather than type size.
- Separate canvas, paper and tinted surfaces. Body copy and supporting text use distinct ink colors; the primary recording action and current step receive the strongest accent.
- Keep the everyday capture panel compact so recent experiences are visible. The experience-list heading stays fixed; individual rows expand to show additional actions.
- Keep dialog headers and navigation fixed while the content scrolls. Show clear keyboard focus without adding outlines to programmatically focused headings.
- Main and review windows share light/dark colors and a locally saved theme choice. Exported review pages carry their own styles.
- Keep the player and transcript splitter. Below the player, Open folder sits beside a split Copy button. Its main action copies this session's folder (not the library root); the arrow opens individual transcript JSON/video paths and document actions. After a successful copy, a check replaces the copy icon and the label reads `copied!` for two seconds without changing the player layout. Failures retain a visible error. Playback shortcuts remain available without a permanent hint row.

## Recording-method introduction

First use and new presets begin with a short introduction before the device/recording/storage steps. Existing-preset editing contains only those three settings steps. The recording area opens the guide independently through an info icon and the recording-method label.

Four concrete prompts explain the method: what I notice, what I think it means, what I plan to try, and how it feels afterward. The examples are invitations, not a script. Pauses, uncertainty, changed interpretations and feelings are welcome. The final setup step includes a short reminder to start with an observation. Saving a preset never starts capture.

## Local workspace

Development and delivery artifacts are under `F:/CodexHome`. This computer's initial library is `F:/think-aloud-record`, set in ignored runtime configuration. Portable archives remain free of machine-specific settings, secrets and recorded material.
