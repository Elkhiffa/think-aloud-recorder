# 开发计划：逐字稿优先的判断实例 MVP（2026-10-09）

> 执行者：Codex。审核者：Claude（经由用户转达）。用户保留目标与取舍的决定权。
> 本计划替代此前“按预算抽图 → 按活动整理”的增量补丁路线。遇到与本计划冲突的旧文档、旧 Skill 条款，以本计划为准，并在里程碑报告中列出冲突点。

## 0. 为什么做

工具的价值是：专业 UX 边玩边说出判断 → 判断能追溯到具体时刻和界面元素 → 能按设计议题跨场次筛选和回看。现在的结果以“活动事件”为单位，问题只是事件里的一段文字，无法按议题跨场次筛选，也无法区分“说出口的时间”与“所指的时刻”。

本轮只做最小可验证的一刀：
1. 修三个会让已有数据出错或被隐藏的问题；
2. 本地 OCR 情景轨道（命令行，不打包）；
3. 结果格式 v2：在现有事件下增加“判断实例”，加上资料库级议题标签；
4. 单游戏界面目录 v1（格式 + 匹配器，不做自动聚类命名）。

Skill 方法文档由 Claude 另行重写，**本轮 Codex 不修改 `skills/` 下的内容**，除非审核意见明确要求。

## 1. 全局规则（必须遵守）

### 1.1 范围纪律
- 只改本计划列出的文件和行为。不顺手重构，不改名，不调整与本轮无关的 UI、样式、文案。
- 不修改 `portable.json` 版本号，不做打包、发布、安装；不碰 `updater.py`、`update_installer.py`、`scripts/build_portable.py`、`scripts/prepare_release.py`。
- 不修改已安装应用 `D:\Think Aloud`，不写入真实资料库 `D:\think-aloud-database`（只读允许）。真实场次的冒烟检查一律用 `--output` 写到工作目录。
- 不 push、不 merge、不 rebase、不 reset --hard。只在本地分支提交。
- 不新增 `docs/*-validation.md` 一类验证文档。每个里程碑的验证结果写进里程碑报告（回复消息），不落成新文件。只有 M3 结束时更新 `docs/agent-integration.md` 与 README 中受影响的段落。
- 不为“可能的边界情况”预先添加防御代码或说明文字。只处理本计划点名的情况；新发现的情况写进报告的“待定问题”，由审核决定。

### 1.2 测试纪律（重点）
- 每个里程碑只写本计划“测试”栏列出的测试，可以拆成多个 test 方法，但不要扩成新的测试矩阵。
- 迭代过程中只跑本里程碑相关的测试模块（如 `python -m unittest tests.test_agent_protocol`）。
- 完整单元测试 `python -m unittest discover -s tests` **每个里程碑只在结束时跑一次**。当前基线：773 个测试全部通过（1 个 skip）。
- 浏览器 `.cjs` 测试：只有改了 `ui/` 或 `player.html` 的里程碑（M3）才跑，并且只跑 `tests/test_agent_review_browser.cjs` 一个；不跑原生 WebView2 冒烟、OBS、真实录音、打包检查。
- 无关的既有测试失败：最多尝试 1 次判断是否由本次改动引起；不是就原样报告，不去修。
- 同一个失败修了 2 次仍未通过：停止，写进报告，等审核。

### 1.2a 触发路径先行（测试与防御代码都适用）
- 写每个测试函数之前，先在它的 docstring 第一行写出触发路径，格式固定为一行：
  `触发路径：<角色> → <入口> → <步骤> → <触发条件> → <不修会怎样>`
- **角色和入口必须是下面之一**，否则不写这个测试，也不写对应的实现：
  1. 用户在界面上的操作（主窗口、向导、回看窗口）；
  2. 命令行命令（`agent_cli.py` 子命令）；
  3. 外部 agent 提交的数据（`validate`/`submit` 的输入）；
  4. 旧版本留下的数据（已有资料库、旧格式结果、升级后首次打开）；
  5. 操作系统层面的状况（文件被杀软/同步盘/索引器占用、磁盘写失败、进程被结束）。
- “理论上可能”“为了健壮性”不是路径。写不出路径的情况，放进里程碑报告的“未写的测试”一栏，由审核决定。
- 同样适用于新增的 `try/except`、参数校验和兜底分支：每个新增分支在代码注释或报告里能对应到一条路径；对应不上就不加。
- 本计划为每个点名测试预先给出了路径（见各里程碑“测试”栏）。直接使用；若发现预给路径在代码里走不通，停下来报告，不要改写路径去迁就实现。
- 里程碑报告的“测试”一栏，每个新测试一行：`测试名 — 路径编号（1–5）— 一句话路径`。

### 1.3 节奏与停止条件
- 每个里程碑结束：**停止并报告**，等审核意见后再开始下一个里程碑。不要自行连续推进。
- 每个里程碑有时间盒（见下）。实际耗时超过时间盒 2 倍时停止，报告卡点。
- 涉及数据格式、字段语义、兼容策略的歧义：不要猜，停下来在报告里提问（列出选项和你的推荐）。

### 1.4 里程碑报告格式（回复消息，不超过约 40 行）
```
里程碑：Mx 名称
分支 / 提交：<branch> <short-sha...>
改动文件：路径列表（每个一句话说明）
测试：执行的命令 → 结果（通过数 / 失败数）
与计划的偏离：无 / 列出
待定问题：无 / 列出（附选项与推荐）
```

## 2. 准备（M0，时间盒 0.5 小时）

- 基于 `fix/preset-device-discovery`（PR #12，0.7.8，尚未合并；若届时已合并则基于 `main`）新建 worktree 与分支 `feat/judgment-instances`。按仓库惯例放在 `D:\Think Aloud Development\source\` 下。
- 把本计划复制到分支的 `docs/plans/2026-10-09-transcript-first-mvp.md` 并提交。
- 准备开发运行环境：使用你惯用的开发 runtime（忽略目录 `runtime/`），不要改动已安装应用的 runtime，不做全局安装。M2 需要的 `rapidocr_onnxruntime` 只装进这个开发 runtime。
- 跑一次完整单元测试记录基线。
- 报告后停止。

## 3. M1：数据层修复（时间盒 1–1.5 天）

参考复现用例：`D:\Think Aloud Development\analysis\review-20261009\repro_findings.py`（两个用例当前“通过”代表 bug 存在；修复后应把断言改为期望行为并移入 `tests/`）。

### M1.1 整理成功后，回看页生成失败不得把场次标为失败
- 位置：`recorder.Session.process()`，`self.update(state='可回看', ...)` 之后的 `make_player(...)` 与 `try_publish_ready(...)`。
- 要求：
  - `make_player` 内的 `os.replace` 使用与 `recorder.write` 相同的 PermissionError 重试。
  - 在 `可回看` 状态写入之后，`make_player` 若仍失败：保持 `state='可回看'`、`transcription_state='ready'`，在 meta 写入 `review_page_warning`（简短中文原因），不进入外层 `except`。下次打开回看或导出时会重新生成（确认现有逻辑已会重建；若不会，在报告中说明，不要新增机制）。
  - `try_publish_ready` 维持“失败不影响原功能”的语义，同样不得进入外层 `except`。
  - 外层 `except` 生成的错误前缀使用实际失败步骤：在调用 `make_player` 前设置 `step='生成回看页'`（只影响前置失败场景的标签）。
- 测试：`F1` 复现用例改为期望 `state=='可回看'` 且存在 `review_page_warning`；原转写文件不被改写。
  - 路径（5）：用户录完一场 → 后台整理写完逐字稿并标为可回看 → 杀软/OneDrive/索引器正占用 `独立回看.html` → 替换抛 PermissionError → 已完成的转写被标“失败”，用户点重试又多存一份旧稿并重复转写。（已在 Windows 实机复现）

### M1.2 `recorder.write` 落盘
- `recorder.write`：写临时文件后 `flush()` + `os.fsync()`，再替换；替换最终失败时删除临时文件后再抛出。
- 不改其他写入函数。
- 测试：替换失败时不残留 `.tmp`（用 patch 让 `os.replace` 一直抛 PermissionError）。
  - 路径（5）：资料库放在同步盘或被杀软长时间锁住 → 40 次重试后仍替换失败 → 每次失败在场次目录留下一个 `.tmp`，越积越多且可能被误当成数据。
  - fsync 本身不写测试（无法在单元测试中模拟断电），只在报告里说明改动位置。

### M1.3 同步偏移、记录者选择不再使整理结果和人工校准失效
现状：`agent_protocol._identity()` 的 revision 原料包含 `alignment=input_alignment(meta)` 与 `recorder_speaker`，用户在回看中改同步偏移或记录者后，`_status` 判为 stale，体验事件页签与人工校准全部隐藏，且无提示。

要求（兼容策略已定，不要改成别的方案）：
- 新 revision 公式：从原料中移除 `alignment` 与 `recorder_speaker`，其余不变。
- 同时保留旧公式函数 `_legacy_revision(...)`（用当前 meta 计算）。以下三处比较时，**等于新公式或等于旧公式即视为一致**：
  1. `agent-ready.json` 的 `revision`；
  2. `experience-events.json` 的 `revision`；
  3. `experience-event-edits.json` 中各条的 `source_revision`。
- `publish_ready` 之后写入的信号一律使用新公式。`claim`/`submit` 的新结果一律使用新公式。
- `submit` 时把提交时刻的 `input_alignment(meta)` 和 `recorder_speaker` 快照写入结果文件的附加字段 `analysis_context`（校验时允许该字段；旧结果没有该字段）。
- `_status` 返回 complete 时，若结果有 `analysis_context` 且与当前值不同，附加 `notice`：“整理后同步偏移／记录者已改动，事件中的操作时间可能有偏差”。回看页在事件页签顶部显示该提示（只加一行文字，沿用现有 notice 样式）。
- `set_input_offset` / `set_recorder_speaker` 中现有的 `try_publish_ready` 调用保留。
- 测试：
  - 改同步偏移后：状态仍为 complete，人工校准仍投影生效，出现 notice（即 F3 复现用例的反向断言）。
    - 路径（1）：用户在回看中把操作同步偏移从 1.0 调到 1.2 → 体验事件页签和全部人工校准消失，没有任何提示。（已在 Windows 实机复现）
  - 用旧公式生成的既有结果（不含 `analysis_context`）在偏移未改动时仍为 complete。
    - 路径（4）：用户升级到新版本 → 打开升级前已整理的场次（真实资料库现有 21 场，全部是旧公式）→ 若只认新公式，全部变成“需重新预处理”。
  - 真实素材文件变化（如 `录像.whisper.json` 改动）仍判为 stale。
    - 路径（1）：用户在场次详情点重新转写 → 逐字稿改变 → 旧整理结果引用的原话已不对应，必须提示需重新预处理。

M1 结束：全量单元测试一次 → 报告 → 停止。

## 4. M2：本地 OCR 情景轨道（时间盒 1.5–2 天）

目的：给 AI 和人一条“每隔几秒画面上有什么文字”的时间轴，用于把原话所指定位到具体界面。只读文字，不做语义判断。

### 4.1 模块与输出
- 新模块 `context_track.py`：
  - 抽帧：用已有的 PyAV（`av`）从 `录像.mp4` 每 `interval` 秒取一帧（默认 5 秒，可选 2–10），缩放到宽 960。支持 `start`/`end`。
  - OCR：`rapidocr_onnxruntime`；若不可导入，抛出明确错误“OCR 依赖未安装”，命令返回 `{ok:false}`，不影响其他功能。
  - **不做任何遮蔽**：UID、角色名、客户端时间水印原样保留（数据不公开，且 QA/程序 debug 需要带 UID 的记录）。只丢弃置信度低于 0.6 的文本。
  - 额外提取水印元数据：识别画面角落形如 `ID:<数字>` 的 UID 水印及其后的客户端日期时间（如 `0929 15:16`），写入顶层 `watermark`：首次出现的 `uid`、以及若干 `{t, client_time}` 样本（每分钟至多 1 个），供将来与客户端日志对时。识别不到时为 null，不报错。
  - 输出 `context-track.json`：
    ```json
    {"version":1,"source_video":{"bytes":123,"mtime_ns":456},"interval":5,
     "watermark":{"uid":"0156936254","client_time":[{"t":2.5,"text":"0929 15:16"}]},
     "frames":[{"t":2.5,"items":[[x,y,"文本"],...]}],
     "screens":[]}
    ```
    `screens` 在 M4 由界面目录匹配填充；M2 留空数组。坐标为 960 宽画面中的文本框中心。
  - 该文件是派生数据：**不进入 revision 原料**，不触发 stale。
  - 有效性只绑定 `录像.mp4` 的大小与 mtime（`source_video`），不绑定场次 revision：重新转写、改记录者都不应使情景轨道失效，否则会无谓地重跑数分钟的 OCR。
- 不接入自动后台队列（MVP 手动运行）。

### 4.2 命令行（`agent_cli.py`）
- `context-build SESSION [--interval 5] [--start S] [--end E] [--output DIR]`：默认写入场次目录；给了 `--output` 就写到该目录（冒烟检查必须用它）。已有同 revision、同 interval 的结果时直接返回，不重算。
- `context-read SESSION [--start S] [--end E] [--compact]`：返回指定区间的帧文本；`--compact` 时合并相邻且文本几乎相同的帧（相同的前 10 个字符的标题行视为相同即可，不要做复杂相似度），每帧最多 120 字。
- 两个命令都在 `--help` 中给一句话说明，遵循现有 `{ok,data|error}` 输出约定。

### 4.3 测试
- 单元测试中 **mock OCR 引擎与抽帧**（不依赖模型文件和真实视频），覆盖以下五项：
  - UID 与客户端时间水印提取，且原文保留在 frames 中。路径（2）：用户要把某段问题连同 UID 和客户端时间发给 QA/程序 → `context-read` 必须能直接给出。
  - 低置信度丢弃。路径（2）：3D 场景、粒子特效被 OCR 成大量乱码 → 情景文字被噪声淹没，agent 读到错误界面。
  - `--compact` 合并。路径（2）：在同一界面停留十几分钟 → 上百帧重复文本塞满 agent 上下文。
  - 已有结果复用。路径（2）：agent 或用户对同一场次再次运行 `context-build` → 不应重新 OCR 数分钟。
  - 重新转写后不失效。路径（1）：用户重新转写 → `录像.mp4` 未变 → 情景轨道仍然有效。
- 冒烟（不写测试文件，写进报告）：对 `D:\think-aloud-database\场次\20260929-151037-2a4c0e*` 的 0–600 秒运行 `context-build --output <工作目录>`，报告帧数、耗时、输出大小，并贴出 `context-read --compact` 的前 15 行。参照物：`D:\Think Aloud Development\analysis\review-20261009\proto-2a4c0e\context_track.txt`。

M2 结束：全量单元测试一次 → 报告 → 停止。

## 5. M3：结果格式 v2 —— 判断实例 + 议题标签（时间盒 2–3 天）

### 5.1 议题标签（资料库级）
- 文件：资料库根目录 `issues.json`：
  ```json
  {"version":1,"issues":[
    {"id":"TA-01","title":"理解养成规则之后，为什么还要自己当物料管理员","description":"","status":"confirmed"},
    {"id":"N-001","title":"……","description":"","status":"candidate"}]}
  ```
  - `id`：`TA-` 开头的由用户定义；agent 新提的一律 `N-` 加三位序号，`status` 只能是 `candidate`。
- 命令行：`issues-list VAULT`、`issues-add VAULT --title T [--id ID] [--status candidate|confirmed]`、`issues-update VAULT ID [--title] [--description] [--status]`、`issues-merge VAULT FROM_ID INTO_ID`（合并时把所有场次结果中引用 FROM 的实例改指 INTO，原结果文件按现有 `agent-history` 方式备份）。
- 写入使用原子替换，加资料库级文件锁（复用现有锁工具，不新造）。
- 报告不由工具维护；工具只负责标签的存取与引用。

### 5.2 结果格式 v2
- `experience-events.json` 的 `version` 允许为 2。v2 = v1 全部字段 + 新增顶层 `instances`：
  ```json
  {"id":"i01","event_id":"e02",
   "said":[{"kind":"quote","ref":"t000012"},{"kind":"quote_words","ref":"t000016","word_range":[0,5]}],
   "refers_to":{"start":182.0,"end":247.0,"basis":"same_time|retrospective|unknown","note":"可选，≤200字"},
   "screen":"catalog 中的 screen id 或 null",
   "elements":["element id", "..."],
   "kind":"confusion|obstacle|positive|expectation|suggestion|self_correction|observation",
   "statement":"≤300字，用记录者的意思概括，不加推测",
   "issue_tags":["TA-03"],
   "evidence":[{"kind":"video","start":226.0,"end":226.0,"observation":"≤300字"}],
   "confidence":"high|medium|low"}
  ```
  - `said` 复用现有 quote / quote_words 的校验与展开逻辑（程序生成文字和时间）。
  - `refers_to` 必须落在场次时长内；`basis=retrospective` 时 `refers_to.end` 不得晚于 `said` 的最早开始时间。
  - `event_id` 必须指向本结果中存在的事件；`issue_tags` 必须存在于 `issues.json`（candidate 也可）；`screen`/`elements` 若非空必须存在于界面目录（M4 之前可为空或 null，校验在目录缺失时跳过）。
  - 上限：每场最多 300 条实例；每条最多 12 条 evidence。
- v1 结果保持完全兼容（读取、校验、显示、导出不变）。
- `submit`、`validate`、`status` 支持 v2；`status` 增加 `instances` 计数。
- 人工校准（`event_edits`）本轮仍只作用于事件，不扩展到实例。

### 5.3 跨场次筛选（只做后端 + 命令行）
- `instances-query VAULT [--issue ID]... [--screen ID] [--element ID] [--kind K] [--session ID]`：遍历资料库中**状态为 complete 的**场次结果，返回扁平列表：`session_id, instance_id, said_start, refers_start, refers_end, screen, elements, kind, statement, issue_tags`，按场次时间和 refers_start 排序。
- 只读，不缓存（MVP）。

### 5.4 最小 UI（只改回看页事件页签）
- 每个事件卡片下列出其实例：两个时间（“说”“指”，点击分别定位）、kind 中文名、statement、标签 id 列表。
- 不做新时间轴、不做实例编辑、不改主界面。
- 样式沿用现有事件卡片的 class，新增 class 不超过 5 个。

### 5.5 测试
- 协议（每项都是路径 3/4/2/1 中的一种，预给路径如下）：
  - v2 合法样例通过。路径（3）：外部 agent 按新格式提交一场整理。
  - `refers_to` 越界被拒。路径（3）：agent 给出超出录像时长的时间（LLM 写错时间是已发生过的问题）→ 回看点击后定位到不存在的位置。
  - retrospective 的所指晚于说出口时被拒。路径（3）：agent 把“刚才……”标成回顾，却把所指时间写在说话之后 → 追溯方向错误。
  - 未知 issue tag 被拒。路径（3）：agent 自造一个不在 `issues.json` 里的标签 → 按议题筛选时这条实例永远查不到。
  - 未知 event_id 被拒。路径（3）：agent 把实例挂到不存在的事件下 → 回看页无处显示。
  - v1 结果不受影响。路径（4）：升级后打开已有 21 场旧格式结果。
  - `instances-query` 按议题跨场次筛选。路径（2）：用户要处理“目标丢失”议题 → 需要列出所有场次中挂了该标签的实例，按时间排序依次回看。
  - `issues-merge` 改写引用并备份。路径（2）：用户发现两个标签说的是同一个问题 → 合并后旧标签的实例全部归到新标签，原结果可追溯。
- 浏览器：只跑 `tests/test_agent_review_browser.cjs`，在其合成数据中加入一个 v2 结果，断言实例渲染和两个时间的定位。
- 文档：更新 `docs/agent-integration.md` 中结果格式与新命令的说明（中文，精简），README“可选体验预处理”一段加一句指向 v2。不新建验证文档。

M3 结束：全量单元测试一次 + 上述一个浏览器测试 → 报告 → 停止。

## 6. M4：单游戏界面目录 v1（时间盒 1.5–2 天）

### 6.1 格式
- 文件：资料库根目录 `game-assets/<游戏名>/catalog.json`（游戏名取场次 meta 的 `game`）：
  ```json
  {"version":1,"game":"燕云十六声",
   "screens":[
     {"id":"bag.items","name":"背包·道具","source":"manual|ocr_cluster|engine",
      "match":{"all_of":["道具"],"any_of":["普通道具","养成材料","活动道具"],"none_of":[]},
      "elements":[{"id":"bag.items.auto_use","name":"自动使用道具","aliases":[],"notes":""}]}]}
  ```
  - `match` 只做文本包含判断：某帧 OCR 文本拼接后满足 all_of 全部出现、any_of 至少一个出现（any_of 为空则不要求）、none_of 都不出现。多个界面同时命中时取 all_of+any_of 命中词数最多者；并列取目录中靠前者。
  - **引擎数据预留（用户有引擎与客户端访问权限，后续会跑测自家待上线功能）**：
    - screen 与 element 均允许可选字段 `engine_id`（字符串，引擎/客户端中的界面或控件标识）；`source` 取值 `manual|ocr_cluster|engine`。
    - `context-track.json` 的 `screens` 条目带 `source`（本轮恒为 `"ocr"`）与可选 `engine_id`，为将来由客户端日志直接给出界面时间轴留位。
    - 预留但本轮不实现的导入文件 `engine-track.json`（场次目录，可选）：`{"version":1,"clock":"client|video","offset_seconds":0,"events":[{"t":12.3,"type":"screen_open|screen_close|widget_focus|widget_activate","engine_id":"...","payload":{}}]}`。只在 `docs/agent-integration.md` 中写明字段约定，不写解析代码。
    - 判断实例的 `screen`/`elements` 仍引用目录 id，由目录负责与 `engine_id` 对应，实例格式不需要因引擎接入而改变。

### 6.2 功能
- `context_track.py` 增加界面匹配：对每帧给出 screen id 或 null，并把连续相同的帧合并成 `screens: [{"start","end","screen"}]` 写回 `context-track.json`（目录变更后可用 `context-build --rematch` 只重算 screens，不重新 OCR）。
- 命令行：
  - `catalog-validate VAULT GAME`：校验格式、id 唯一、元素 id 唯一。
  - `catalog-suggest SESSION [--top 30]`：只做确定性统计，列出出现频次最高的“标题区文本”（每帧 y<70 的文本拼接）及其出现时间样例，供人或 AI 命名；**不自动写入目录**。
  - `catalog-hotwords VAULT GAME --output FILE`：把所有 screen/element 的 name 与 aliases 导出为 TXT 词表，用户可通过现有词库功能手动加入预设；不自动修改预设。
- 目录内容本身（界面和元素条目）不由 Codex 编写；测试用合成目录。

### 6.3 测试
- 匹配规则：all_of/any_of/none_of 与并列取舍。路径（2）：目录里“背包·道具”和“背包·任务”都含“仓库”等共同字样 → 不加 none_of 和取舍规则就会互相误判。
- 相邻帧合并。路径（2）：agent 读界面时间轴时需要的是区间，不是逐帧列表。
- `--rematch` 不调用 OCR。路径（2）：用户录了 20 场后修订目录 → 只重算界面分段，不应重跑几小时 OCR。
- `catalog-validate` 报重复 id。路径（2）：手工编辑 JSON 时复制条目忘了改 id → 实例引用指向不明确。
- `catalog-hotwords` 去重。路径（2）：元素别名之间、别名与名称重复 → 导出的词表出现重复词条。

M4 结束：全量单元测试一次 → 报告 → 停止。

## 7. 不在本轮范围（不要做）

- 主界面的议题视图、跨场次连续回看、分层时间轴与“说→指”连线、实例级人工校准（下一轮 P2）。
- 视觉 token 与组件统一、编辑预设单页化、录制前 5 秒准备与就绪检测速度（P3）。
- 页面桥接门面化与 CSP、导出白名单（安全加固，另排）。
- OCR 模型进入安装包、第三方来源材料补全。
- 修改 `skills/think-aloud-preprocess`（由 Claude 重写）。
- 删除或改写旧的 `visual-*` 命令（保留兼容，本轮不碰）。
