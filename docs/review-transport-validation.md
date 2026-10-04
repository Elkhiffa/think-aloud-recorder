# Review transport and companion layout — 0.7.3

Playback controls now occupy their own permanent row below the picture. Play/pause and time stay left; volume, a direct speed menu, settings and fullscreen stay right. Keyboard seeking is retained without visible rewind/forward buttons. Settings contain only a persistent double-click fullscreen preference; when disabled, double-click toggles playback once.

The current transcript appears below the video alongside a compact input panel, with a stacked layout in narrow panes. During pauses between utterances the previous quote is explicitly labeled. Timeline quote hover/pinning remains available. Header activity details use the available title width, routine saved messages are removed, and review spacing uses 4/8/16/24/32/40 px (or zero for no spacing).

Verification uses synthetic media and isolated preferences; no user recordings are captured or changed:

- Full Python suite: 742 tests, 739 passed and 3 environment skips.
- Review transport browser acceptance: permanent controls, actual speed changes, double-click behaviors, persisted settings, transcript synchronization, responsive geometry, light/dark rendering and computed spacing.
- Source-aspect browser acceptance: 14 checks, including ultrawide and portrait media.
- Existing input timeline browser acceptance: 35 checks; experience-event browser acceptance: 13 checks; quote popover and pure review logic checks also pass.
- A separate real WebView2 smoke check is required on the staged delivery before installation; its machine-specific receipt stays outside the repository.

The native preference is stored in `state/review-playback.json`, independently of layout and session material. Standalone browser reviews use local storage. The existing Plyr playback engine, progress, volume and fullscreen controls remain in use.
