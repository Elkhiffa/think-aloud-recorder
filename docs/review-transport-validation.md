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

## 0.7.4 refinements

- The recorder selector is a quiet, unfilled control beside transcript search. A second, softly filled chip sits beside the current/previous quote heading. Both open the same dialog, which shows the selected speaker's measured speech share and explains that an actual recorder change requires agent preprocessing again.
- Saving an unchanged selection preserves the automatic/manual mode and does not rewrite metadata or republish material readiness. Transcript identity is still validated before a no-op can succeed. A real selection change still marks old analysis stale without deleting it.
- Companion panels reserve 112 px side by side or 168 px total when stacked. Speaker information no longer consumes a separate caption line.
- The playback line is 2 px high on its own composited layer, aligned to physical screen pixels. Real press duration uses a 4 px two-tone rail above label fills; label padding does not extend the physical interval.

Validation: 743 Python tests (740 passed, 3 environment skips); 10 speaker UI, 6 transport UI, 35 input UI, 14 source-aspect and 13 agent UI checks passed. The low-zoom check samples 90 playback frames at 0.2× and 150% display scaling. Real WebView2/bridge acceptance with synthetic preprocessed material confirms both dialog entry points, unchanged-save preservation, and actual-change invalidation. No personal recordings were modified during tests.
