# Compact main window — 0.7.6

The supplied interaction sketches guide hierarchy and control placement; the existing warm-paper visual identity remains. Main-screen spacing uses the 4/8/16/24/32/40 px scale.

- Header owns recording-method help, version/update access and theme.
- Preset selection, accessible plus and gear buttons, and recording action align at 48 px. Recording time stays above the action and the microphone meter below. Quiet states remain free of microphone prose; the existing two-minute warning remains visible above the action.
- Project, local date and duration share a metadata row. Activity details use the entire row width and wrap. Completed preprocessing counts and storage paths remain available in expanded details/settings; active jobs and exceptional statuses stay visible.
- Native startup size changes from 1240 × 960 to 920 × 1040, bounded by monitor work area. Minimum size is 720 × 600, also bounded on smaller displays. Existing review-window sizing is unchanged.

## Acceptance

- Python regression: 757 tests, 754 passed and 3 environment skips.
- Front-end state/bridge tests: 42 passed.
- Edge browser acceptance: 50 checks passed, covering primary actions, background processing, session expansion/rename, long paths, preset editor, vocabulary revision safeguards and existing review/update behavior. Main-screen screenshots cover light/dark 920 × 1040 and compact 720 × 620; 390 px reflow remains operable without horizontal overflow.
- Microphone browser checks pass for signal/quiet/error conditions, two-minute warnings, stable ordinary recording geometry, clock/button/meter order, bridge timeout and session isolation.
- Real `app.run_window` with an isolated synthetic configuration confirms WebView2 load and no horizontal overflow under this computer's display/text scaling. The desktop screenshot confirms the new arrangement. Manual click verification stopped when the user's screenshot overlay covered the window; browser interaction coverage and the native bridge check remain separate evidence.
- The native smoke also verifies the preceding vocabulary API change with a separate CLI process, the live UI snapshot and stale-editor rejection. Only synthetic configuration and vocabulary are used; no recording or cloud transcription is initiated.

Packaging and any installation receipts are machine-local under the ignored delivery directory. User configuration, vocabulary, recordings and transcripts are excluded from the software payload and preserved by the transaction updater.
