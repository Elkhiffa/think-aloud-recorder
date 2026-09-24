# 回看页源比例适配验证

2026-09-22，`feat/warm-paper-ui` 工作树。本次只调整回看页内部布局，不修改桌面窗口尺寸。

## 已实现行为

- 首次取得视频真实 `videoWidth` / `videoHeight` 后，按源比例自动计算左右栏。计算扣除布局边距、分隔线、资料工具栏的实际高度以及栏内间距。自动适配为逐字稿保留至少 320 px；手动分隔线仍允许缩到原有 220 px 下限。
- 视频槽本身保持源比例。宽度不足时降低视频槽高度并保持顶部对齐；画面仍使用 `object-fit: contain`，不裁切、不拉伸。高度受限的竖屏槽可比其所在栏更窄。
- 上个视频保存的分栏值只作为未取得源尺寸时的回退，不覆盖新视频的自动适配。用户拖动或按方向键后，源尺寸更新和窗口尺寸变化均保留手动比例；双击或 Enter 恢复自动适配。
- 工具栏高度随宽度现场测量；适配从最宽候选逐步缩窄，避免工具栏换行造成宽窄往返。
- 窄屏上下分栏及逐字稿独立滚动保留。很窄的竖屏播放器解除 Plyr 的 200 px 最小宽度，显示进度、播放、静音和全屏操作；较宽播放器保留完整操作。

## 验证及证据边界

`node tests/test_review_ui.js` 通过：时间线、分栏边界、16:9 / 超宽 / 竖屏适配、工具栏换行占高、窄宽度约束和无效元数据回退。

`node tests/test_review_aspect_browser.cjs` 10 组检查全部通过。使用已安装 Edge 和现有 Playwright；视频由浏览器的 canvas / MediaRecorder 生成，实际解码产生源尺寸，没有替换 `videoWidth` / `videoHeight`。使用真实模板、样式、脚本和 Plyr，桌面桥接为合成响应。

固定 1240 × 900 浏览器视口下的实测结果（CSS px，四舍五入到两位）：

| 实际视频源 | 视频栏宽 | 视频槽尺寸 | 逐字稿栏宽 |
| --- | ---: | ---: | ---: |
| 960 × 540（16:9） | 847.98 | 847.98 × 476.98 | 320.00 |
| 1280 × 540（超宽） | 847.98 | 847.98 × 357.73 | 320.00 |
| 540 × 960（竖屏） | 405.05 | 405.05 × 720.08 | 762.95 |

浏览器检查另覆盖：

- 桌面桥接延迟返回旧分栏、独立导出页保存旧分栏，均不会覆盖源适配。
- 实际拖动后替换为另一比例的合成视频，再调整到 1440 × 840、1050 × 700、1240 × 900，保留手动分栏且视频槽继续保持新源比例。
- 元数据到达前的手动调整、双击复位、Enter 复位和复位后的继续自动适配。
- 1000 px 宽窗口在 650–880 px 高之间逐 10 px 检查，覆盖工具栏由 90 px 换行为 40 px 的实际边界；每档连续 10 个渲染帧没有分栏振荡。
- 横屏和竖屏视频在 560 × 540 上下布局中保持比例；播放、静音和全屏控件仍在视频槽内，逐字稿保留至少 32 px 内容高度。
- 逐字稿真实滚轮滚动不改变视频槽位置或尺寸，不滚动整个页面；无脚本异常、无非本地测试请求。

机器可读几何证据与截图保存在忽略的 `work/review-aspect/acceptance.json` 及同目录 PNG。重新运行会刷新这些合成证据；可以通过 `TAR_ASPECT_OUTPUT` 指定其他输出目录，通过 `PLAYWRIGHT_MODULE` 指向现有 Playwright。

以上证明浏览器内实际布局与交互，不等同于原生 WebView2 窗口、打包应用、OBS 或用户安装验收。测试视频和逐字稿均为合成数据。

## 2026-09-23 replacement resize contract

The earlier ratio-preserving column behavior above is historical. Current review opens with a video-width target of at least 900 px when the monitor allows it, then holds the CURRENT left width while window resizing changes the right pane. Only a right-pane minimum (measured header plus at least the ruler and two lanes, floor 280 px) can force the left side narrower. A later enlargement retains that narrowed width rather than restoring 900; manually moving the divider becomes the new current width. Double-click/Enter explicitly reinitializes the fit.

The player and recent-operation card have identical widths. Source pixels retain their ratio with `object-fit: contain`; the player container may use black bars when height-constrained or displaying unusual aspect ratios. Native review starts at 1440 × 900 within the selected monitor's available area.

Current `tests/test_review_aspect_browser.cjs` verifies this behavior with wide, ultrawide and portrait synthetic media, current-width preservation after manual dragging and repeated resizing, compact breakpoints, and unchanged playback geometry during transcript scrolling. All 10 checks passed; current evidence is `work/review-aspect/acceptance.json`. This browser report does not independently validate native monitor DPI conversion.
