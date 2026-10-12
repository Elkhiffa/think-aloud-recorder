# 外部体验预处理接口

Think Aloud 负责保存原始资料并提供回看。外部 agent 可以把资料整理成可追溯的体验事件、探索想法和可选问题；记录器不附带 agent，也不运行后台 AI 任务。

没有 agent 时，完成的场次照常显示“可回看”。领取、预处理失败、过期或损坏均不会改变录制/转写状态。只有当前素材版本的有效结果才显示“体验事件”页签；事件及证据可定位原始录像。问题无需回答即可完成预处理。

## 手动发起一次预处理

默认由用户控制发起时机：结束一段录制，并等转写和文件整理完成后，把该场次文件夹路径交给外部会话。单次任务完成即结束，不需要定时检查资料库。录制中的场次或仅视频先就绪的场次不应进入预处理。

将源码中的整个 `skills/think-aloud-preprocess` 目录安装到所用 agent 的技能目录后，可使用下面的提示词。软件更新不会同步这个独立副本，更新方法见下方“Skill 安装与更新”。回看顶部复制按钮的下拉菜单提供「复制场次文件夹路径」。这里的路径应指向包含 `session.json`、录像和逐字稿的具体场次文件夹，而不是整个资料库；接口会检查真实整理状态和当前素材版本。

```text
使用 $think-aloud-preprocess，对这个 Think Aloud 场次做一次预处理：

场次文件夹：【粘贴当前场次文件夹路径】

这是手动发起的单次任务，取代此前的持续监听安排。只处理指定场次，不创建定时任务，不持续扫描或等待。

先确认录制、转写和文件整理已经完成。若尚未完成，说明情况并结束；若素材已整理完成，只缺就绪信号，可通过本地接口为这个场次补发。

按照 skill 读取原话，结合相关画面、操作和必要的原声，整理可追溯的体验事件、值得探索的想法，以及少量可选问题。区分明确表达、实际观察和推测，如实说明资料缺口与检查范围；不要只挑问题，也保留顺畅体验和反例。无需等我回答问题才完成。

通过 skill 的接口校验并提交结果，确认记录器能读取处理状态。保留原始素材和逐字稿；相同版本已有完整结果时复用，不重复处理。像给聊天会话起名一样概括本场具体做了什么，提交后通过 name-activities 为未命名场次生成简短标题（例如“清河探索与初次止戈”）；完整任务/区域、玩法专名与目标另存 activities 详情，不套固定粗分类词表。手动标题完整保留，自动整理只更新下方内容详情；无手动标题时采用简短的会话式内容标题。项目名和预处理事件数显示在副标题行，活动内容另行换行呈现。接口见 [场次命名](../skills/think-aloud-preprocess/references/activity-naming.md)。

完成后简要告诉我整理出了什么、有哪些资料限制，以及值得我补充的信息。
```

## Skill 安装与更新

应用、仓库中的方法文档和 agent 已安装的 Skill 是三个独立对象。安装包升级成功，不表示 Skill 副本已更新；仓库文档可能在应用版本不变时继续澄清方法。不要仅用相同的软件版本号判断它们是否一致。

1. 确定源码提交，取得该提交的整个 `skills/think-aloud-preprocess` 目录；使用 Skill 安装器时指定固定的 `ref`。已安装的目录先复制备份到技能目录之外，避免把备份也作为第二份 Skill 加载。先比较原副本与来源：存在本地定制时保留并审阅，不直接覆盖。
2. 一并同步 `SKILL.md`、`references/protocol.md` 和 `agents/openai.yaml`，以及未来由该 Skill 引用的其他资源。只更新主文档可能继续引用旧协议。不要替换无关 Skill、修改 agent 配置或删除用户添加的文件。
3. 保存来源提交、旧副本备份位置和安装前后逐文件 SHA256；与实际取得的来源文件核对。用目标应用的 `app/agent_cli.py --help` 确认文档所需入口，必要时再检查子命令。比如 `quote_words` 需要应用 0.6.10，追加预算及高清请求需要 0.6.9；缺少入口时先升级应用，不修改原始素材来绕过兼容限制。
4. 新副本在后续轮次中可用；正在进行的会话若要采用新方法，应明确读取更新后的主文档及引用资源，并记下实际采用的来源提交。磁盘文件一致、会话读过文档、按规则执行和分析效果达标分别验收，不能互相替代。不因安装 Skill 而重做已有结果。

两台电脑可用不同的本地路径，但应从同一已确认来源同步。若报告与已安装副本不一致，先指出报告实际使用的提交和应用版本，再完成同步；不要把新文件的存在写成旧任务已经使用它的证据。

## 文件与状态

每个场次在录像、转写和独立回看文件完成后，最后原子发布 `agent-ready.json`。信号包含协议版本、场次 ID、素材 revision、相对源文件名及大小/修改时间、录像时长。没有安装路径、配置或密钥。

`agent_cli.py` 是外部会话的本地接口，使用自带 Python。`scan` 读取就绪场次；`publish` 为指定旧场次补发或更新信号；`claim` 领取，`reprocess` 备份后重新领取已有结果，`renew` 续期，`evidence` 读概览/区间，`frame` 提取图片，`validate` 校验候选，`submit` 提交，`fail` 记录原因，`status` 回读状态。完整参数见 `--help`。

0.6.10 增加 `quote-words SESSION --ref t000040 [--offset 0 --limit 80]`，按需读取一条原话的原始词时间，最多每页 200 词。当同一转写片段中的话相隔很久，可在结果中用 `{"kind":"quote_words","ref":"t000040","word_range":[3,9]}` 引用原数组索引 3–8。程序生成节选文字、时间和说话人，回看点击定位到节选起点；不修改原转写、素材 revision 或已有机械索引。没有有效词时间时明确拒绝节选，普通整段引用仍可使用。词间空档不等于已确认的静音。

含原话节选的结果需 0.6.10 及以上读取、提交和重新导出；旧版会拒绝新证据类型，不能显示该整份事件结果，但原视频／逐字稿不受影响。新版兼容旧整段引用。原话与画面默认输出不增加字词明细，只有按需查询才展开。

画面候选试验另提供 `visual-nodes`、`visual-overview`、`visual-read`、`visual-review`：先在本地逐帧压缩画面变化，先读全程紧凑概览，再按需展开带时间戳的图片与原话/操作引用。它不领取分析任务、不提交体验事件，也不自动运行，详见 [画面变化候选](visual-nodes.md)。概览不能替代实际看图或完整原话；不要将机械候选直接视为玩家目标或问题。分阶段机器统计与返回字符量可用于控制取材开销，不能换算为真实模型额度消耗。

新增 `visual-plan INDEX --output NEW_DIR`、`visual-packet PLAN --request-id ID --phase initial|inspect|review --question TEXT` 和 `visual-budget PLAN`，将首轮、定向补图与复核纳入同一个发放预算。默认总额 24、首轮最多 12、复核预留 4，属于试验配置。补图用 `--at` 指定时间，或 `--start/--end/--limit` 请求短区间。每个调用者共享同场计划，不能以新计划或直接打开原图绕过额度；完整机械索引不是必须全部读完的任务清单。预算只计算入口发放次数，不能代替实际看图记录或模型计费统计。详见上述文档的“共用预算的取材计划”。

0.6.5 增加 `visual-candidates INDEX --start SEC --end SEC [--limit 24]`：将短区间内主要及弱候选平铺成有上限的导航表，不携带整段运动树与原话。新的选图计划采用分散首轮和局部稳定程度排序，缓解近邻动画挤占名额；旧计划保留旧算法与原预算，新计划格式需 0.6.5。完整 `visual-read` 接口保持兼容。

0.6.12 增加 `visual-compare PLAN --request-id ID --question TEXT --start SEC --end SEC [--region X Y WIDTH HEIGHT] [--mode candidates|scan] [--limit 8]`。针对一个具体疑问，比较已有候选或显式短窗内的局部像素变化，保留出现顺序与 A→B→A 返回过程。它只返回原始 PTS、机械分组和覆盖限制，不发图、不理解交互语义；实际看图仍走原计划的 `visual-packet` 与同场累计账本。候选模式最多 120 秒，逐帧模式最多 30 秒；动画、关注区域不准和原始素材缺口仍可能影响结果。详见 [Skill 的局部状态比较规约](../skills/think-aloud-preprocess/references/protocol.md#局部状态比较)。旧索引、旧预算及正式结果格式不需迁移，不因升级重做已完成场次。

同版回看在操作时间轴上标出“游戏在后台”区间，并只弱化相交的输入部分。跨前后台的长按仍是一个输入事实；未知或矛盾的窗口状态单独标记，不视为后台，也不计作采集缺口。后台输入不代表游戏必然未接收；展示不改变源时间和校准。

```powershell
& 'F:\ThinkAloud\app\runtime\python.exe' 'F:\ThinkAloud\app\agent_cli.py' scan 'F:\think-aloud-database'
```

此处路径只是本机示例。公司电脑应使用实际安装位置与资料库。

完成信号不等于已预处理。未领取时不显示“待处理”。外部会话领取后显示“预处理中”；结果有效后显示“已预处理 · N 个事件”；领取过期/失败显示“预处理未完成”。转写、原始操作等素材文件变化会使旧结果过期。开发版中，手动同步和记录者选择不再改变 revision；已有结果按整理时快照解释，设置变化时在事件页签顶部提示可能的操作时间偏差。用户命名、笔记与处理状态不属于 revision，避免回写触发自身重跑。

revision 是本地源文件大小/修改时间和相关语义设置的指纹，不是内容校验签名。手工替换素材后需正常更新文件修改时间并重新发布。目录移动而保持文件属性时不会无故重新处理。

## 逐字稿优先的开发版接口

以下为当前源码中的开发版功能，不表示现有安装包已包含。就绪信号和领取协议保持 v1，结果文件允许 v1 或 v2。v1 的读取、校验、回看和导出继续可用；本轮不改独立 Skill 方法文档。

### 结果格式 v2

v2 保留 v1 的 session_id、revision、summary、coverage、events、questions、ideas，在顶层增加 `instances`（每场最多 300 条）。下面是单条实例；引用必须来自该场的实际证据与资料库目录：

```json
{
  "id": "i01", "event_id": "e02",
  "said": [{"kind":"quote","ref":"t000012"}, {"kind":"quote_words","ref":"t000016","word_range":[0,5]}],
  "refers_to": {"start":182.0,"end":247.0,"basis":"retrospective","note":"回顾刚才的界面"},
  "screen": "bag.items", "elements": ["bag.items.auto_use"],
  "kind": "confusion", "statement": "记录者对刚才的状态变化不确定。",
  "issue_tags": ["TA-03"],
  "evidence": [{"kind":"video","start":226.0,"end":226.0,"observation":"所指按钮仍显示原状态。"}],
  "confidence": "medium"
}
```

`said` 必须有原话引用；其文字、时间和说话人由程序从原始逐字稿展开。`refers_to` 使用录像秒数，范围不能越界；`basis` 为 `same_time|retrospective|unknown|earlier_session`，回顾实例的结束不得晚于最早 `said.start`，可选 note 最多 200 字；`earlier_session` 表示所指在本场之前的游玩，不填 start/end，note 必填。可选 `compare_to:{start,end,note?}` 记录比较判断的第二个时刻。`event_id` 必须存在；statement 最多 300 字，不添加原话未表达的判断。kind 为 `confusion|obstacle|positive|negative|expectation|suggestion|self_correction|observation`，其中 negative 是对设计价值或动机的否定评价，obstacle 是操作受阻；confidence 为 `high|medium|low`。补充 evidence 最多 12 条：画面事实（observation 最多 300 字且位于 coverage 已检查范围），或操作引用 `{kind:"input",ref}`（需 coverage.inputs 不为 none）。`inputs-summary SESSION --start S --end E` 把同一按键或摇杆的连续操作合并成区段，首尾编号可直接作为操作引用，每次最多 10 分钟。

`issue_tags` 必须已登记。screen 是界面的完整导航路径（入口名即使不显示也写上），可为 null；存在游戏目录时，非空 screen 必须在目录中，目录里还没有的新界面标 `screen_proposed: true`，留待用户确认后收入目录。界面之间可以交叉跳转，跳转经过的界面按顺序写在可选的 `route` 列表，screen 只放最终所在界面。screen 为 null 时可用 `screen_context` 说明原因：`hud`（HUD、战斗、大世界）、`multi_screen`（跨多个界面的总体评价）、`outside_game`（游戏外窗口）、`unknown`。elements 记录画面上的文字，不要求在目录中登记。`validate`、`submit`、`status` 均支持 v2，提交和状态返回实例数量。回看在所属事件下显示中文类型、陈述、标签，以及分别定位原话起点和所指起点的“说”“指”按钮；指向本场之前的只显示说明，有对照时刻的另有“对照”按钮。人工校准仍仅作用于事件。

### 分析快照与旧结果

新提交由程序写入 `analysis_context: {alignment, recorder_speaker}`。校验与投影按该快照解释操作证据；当前设置变化只生成 notice。旧公式的 ready、result 和人工校准 source_revision 继续兼容。旧结果没有快照时，回看设置入口在修改前确认旧 revision 与当前上下文一致，然后写 `analysis-context.json: {result_sha256, alignment, recorder_speaker}`；结果原文件不改写，校准摘要绑定保持不变。读取顺序为结果内快照、SHA 匹配的旁车、当前设置。真实素材变化仍使结果过期。

旧 `visual-*` 工具保留原实现；本轮 revision 公式变化会使升级前的视觉索引与计划过期，需要时重建。重建后的索引不再因偏移或记录者变化而过期；这些工具不属于新方法主路径。

### 议题标签与跨场次查询

资料库根目录的 `issues.json` 保存 `{version:1, issues:[{id,title,description,status,parent?}]}`。用户编号以 `TA-` 开头；新提候选自动使用 `N-001` 等三位编号且只能以 candidate 创建。确认既有候选使用 `issues-update --status confirmed`。子议题只有一级，编号为父议题加 `.n`（如 `TA-04.5`），行内 `parent` 必须等于编号前缀；`issues-add --parent ID` 自动编号，`description` 写成立的理由。`BUG` 是固定议题，读取时总会出现，不能改名、改状态或合并；单场次整理只在记录者原话明说是 bug 或把问题归到程序、引擎本身时直接写 `issue_tags:["BUG"]`，其余议题标签仍只在跨场次分析时通过对应表挂。有子议题的议题须先合并或移走子议题才能合并。

```text
issues-list VAULT
issues-add VAULT --title TITLE [--id ID] [--status candidate|confirmed] [--parent ID]
issues-update VAULT ID [--title TITLE] [--description TEXT] [--status candidate|confirmed]
issues-merge VAULT FROM_ID INTO_ID
issues-dismiss VAULT ID
issues-link VAULT --file LINKS.json | --issue ID --session SESSION --instance INSTANCE [--reason TEXT] [--role support|counter]
issues-unlink VAULT ID --session SESSION --instance INSTANCE
instances-query VAULT [--issue ID]... [--screen ID] [--element ID] [--kind KIND] [--session ID]
bug-hits VAULT
insight-validate VAULT REPORT
catalog-confirm VAULT GAME --proposed NAME (--new ID [--name NAME] | --into ID)
```

以上均为 `agent_cli.py` 子命令。合并前备份原结果至 `agent-history`；追加绑定新摘要的校准记录，保留原条目，并保留分析快照。完成引用替换后再移除旧标签。资料库写入复用文件锁与原子替换。资料库根目录的 `issue-links.json` 是“议题 → 实例”对应表 `{version:1, links:[{issue,session_id,instance_id,result_sha256,reason,role}]}`，`role` 为 support（支持证据，缺省值）或 counter（反例），供跨场次分析在不改写各场结果的情况下归类；`issues-link` 整批校验后才写入，议题和实例都必须存在且场次已完成整理。每条对应绑定写入时的结果摘要，该场重新整理后旧对应不再生效，`issues-list` 为每个议题给出 links_active / links_stale。合并议题时对应表里的引用一起改写；被改写结果的场次，其余对应同时换绑到新摘要。查询只读取 complete 场次，不建立查询缓存；议题条件同时匹配实例自带的标签和有效对应，查父议题时一并匹配其子议题；多个 issue 取任一匹配，其余条件叠加。`--screen` 按目录编号或别名匹配，二者等价。返回 session_id、instance_id、said_start、refers_start/refers_end、screen、catalog_screen（screen 是目录编号或别名时为正式编号，否则为 null）、frame_at（第一条画面证据的时刻，没有则为 null）、elements、kind、statement、issue_tags（两种来源合并）、issue_links（议题、理由和角色）、event_id 和 event_title，按场次时间、所指起点排序。

`issues-dismiss` 只用于候选议题（没有子议题、没有场次结果直接带这个标签）：移除该议题及其全部对应，场次结果不变。`bug-hits` 列出记录者本人原话中含 “bug”、“Cocos”、“引擎”、“报错”、“闪退”、“重叠”、“裁切”、“适配”、“歪了”、“偏了”（不分大小写）的转写段落；有说话人标注时只认记录者，没有标注时整段视为记录者。每条按原话引用对上实例，state 为 linked（实例已挂 BUG 或其子议题）、instance（成了实例但未挂）或 raw（没有成为实例）。

洞察报告由跨场次分析 agent 写入资料库根目录的 `洞察/*.md`（单个不超过 1 MB）；工具不撰写报告，只在洞察窗口展示并核对引用。实例引用写作 `[0924 i72](i:SESSION_ID/i72#TA-04.5)`，`#` 后可选写明证据所属议题；议题引用写作 `[TA-04.5](issue:TA-04.5)`。`insight-validate` 返回引用总数和找不到的引用（实例不存在、场次未完成整理或议题不存在）。

### 本地情景轨道与界面目录

开发 runtime 需单独安装 `rapidocr_onnxruntime`；缺失时命令明确返回“OCR 依赖未安装”。本轮未加入安装包或自动后台队列。

```text
context-build SESSION [--interval 5] [--title-interval 2] [--full-interval 10] [--start SEC] [--end SEC] [--output DIR]
context-read SESSION [--start SEC] [--end SEC] [--compact] [--output DIR]
context-build SESSION --rematch [--output DIR]
catalog-validate VAULT GAME
catalog-suggest SESSION [--top 30]
catalog-hotwords VAULT GAME --output FILE
```

轨道保存在 `context-track.json`，含 source_video（视频大小、mtime_ns）、interval、start/end、frames 和 screens。每隔 2–10 秒取区间中点附近的真实视频帧，缩放宽 960；items 为 `[中心x,中心y,原文]`，丢弃置信度低于 0.6 的文本。UID、角色名等原文均保留。OCR 文字仅供定位，误识别仍需看原画面确认。

目录有 `title_regions` 时改为两层模式，轨道 version 为 2：每 `--title-interval` 秒（默认 2，可选 1–10）只识别各标题区裁图，每 `--full-interval` 秒（默认 10，不小于标题间隔、不超过 60）在同一格点上做一次整屏识别。每帧带 `titles:[{region,text,x}]`（x 为裁图左边界的归一化坐标），只有整屏帧带 items；顶层另有 title_interval、full_interval 和所用 title_regions，interval 等于标题间隔。没有目录或目录没有 `title_regions` 时保持单层 version 1，只用 `--interval`；两种版本的轨道都可读取。

同视频及同采样参数复用（两层模式还要求标题区坐标相同）；转写或记录者变化不会重跑 OCR。`--compact` 按标题前 10 字合并相邻帧，两层轨道优先按标题区文字合并，只有标题区且无字的帧略过；每段文字最多 120 字。`--output` 将生成和读取定位到外置工作目录，真实素材冒烟须使用该参数。`--rematch` 只重算 screens，保留帧。

目录位于 `game-assets/GAME/catalog.json`，结构为 `{version:1, game, screens:[{id,name,source,match,elements}]}`。match 包含 all_of、any_of、none_of 字符串数组；全部 all_of、至少一个 any_of（空数组不限）、没有 none_of 时命中。多命中按 all_of+any_of 命中词数排序，并列按目录先后。element 含 id、name、aliases、notes；screen/element 可附 `engine_id`，source 可为 manual、ocr_cluster、engine。目录顶层可选 `title_regions:[{id,rect:[x,y,w,h],detect?}]`，rect 为 0–1 归一化坐标；`detect:{type:"vertical_edge",x_range:[a,b]}` 在该横向范围内找同方向亮度跳变覆盖行数最多的一列作为面板左边界（至少覆盖 60% 的行），以该列为左边裁出 w×h，找不到时用 rect 原位置。match 可选 `title_any_of`：帧有标题文字时先按标题命中词数选界面，并列按目录先后；未命中再用整屏规则。只识别了标题区的帧若标题未命中，不作判断，既不延长也不打断分段。相邻同界面观测合并为 start/end/screen，source 恒为 ocr，有对应 engine_id 时保留；区间端点是实际观测帧时间，未命中记为 null。目录由用户维护，程序不自动命名界面。用户在洞察窗口或用 `catalog-confirm` 确认 agent 提议的界面时：收为新界面写入只有名称、匹配词留空的最小条目（不会认领画面），编号与提议名不同时提议名记为别名；并入已有界面则把提议名加为该界面的别名。确认只改目录，不改写场次结果；提议名一旦成为目录编号或别名，即不再列为待确认。

`catalog-suggest` 只统计 y<70 的标题文字及出现时间，两层轨道改为统计标题区文字；`catalog-hotwords` 导出名称与别名去重 TXT，用户通过现有词库功能手动加入预设。

引擎预留文件 `engine-track.json` 的约定为 `{"version":1,"clock":"client|video","offset_seconds":0,"events":[{"t":12.3,"type":"screen_open|screen_close|widget_focus|widget_activate","engine_id":"...","payload":{}}]}`。本轮不解析此文件；判断实例继续引用目录 id，由目录映射 engine_id。

## 一致性与独立性

用户明确要求重做时，用 `reprocess SESSION --worker 会话标识 --reason 重做理由`，不用删除结果或修改素材 revision。接口先把旧结果原始字节保存到 `agent-history`，校验后才发放领取令牌；旧结果在新提交成功前继续可回看。备份失败不会建立领取，活跃任务不能抢占。重做失败或过期保留旧结果；`status.reanalysis` 提供重做状态。已有结果仍有效时顶层 `state=complete` 代表该结果可用，不代表这轮已完成。报告等非接口文件由执行会话在重做前另行备份。

事件分析应先还原整场的主要目标与过程，允许目标未明，然后从事件中推导问题。机械画面节点辅助取材，不直接生成语义事件。前后对比应记录相同场次／revision、基线与新结果，新增场次和素材变化另列。

- 领取采用短暂的跨进程场次锁和到期令牌；新领取后，旧 worker 不能提交。正在有效领取的场次不能被其他 worker 抢占。
- 原始资料在录制时就已保存。预处理结果是附加层，没有“等待 agent 后才能正式存文件”的步骤。
- `experience-events.json` 是单文件原子完成回执。结果内引用绑定素材 revision，经校验后再对外展示。之后重做保留旧结果于 `agent-history`；不移动场次目录或覆盖原话、视频、用户笔记。用户授权后可另用 `name-activities` 保存有事件依据的具体内容项并给未命名场次命名；手动标题完整保留，自动整理只更新下方内容详情；无手动标题时采用简短的会话式内容标题。项目名和预处理事件数显示在副标题行，活动内容另行换行呈现。接口见 [场次命名](../skills/think-aloud-preprocess/references/activity-naming.md)。
- 录制完成时发布接口失败不影响原功能；外部会话可用 `publish` 为指定场次补发。只有用户明确授权一批历史场次时才使用 `scan --publish`，不能因为单场次缺少标记就把整个资料库加入处理范围。若另行配置监听，监听器启动时应重扫，而非仅依赖单次文件通知。
- 操作证据通过与回看相同的撤销/缺口逻辑读取，应用同步偏移并保留原时间、后台状态。异常/缺失输入不构成“没有操作”的证据。
- UI 只读取本地校验结果，不执行生成的 HTML、脚本或链接。导出保留验证后的事件和静态回看，不携带任务领取令牌、就绪文件或本机处理历史。

可维护的预处理 skill 位于源码 `skills/think-aloud-preprocess`，包括方法和具体结果格式。它可单独复制到另一台电脑的 Codex skills 目录；软件包不携带用户技能配置。持续监控由用户明确授权的外部会话承担，本接口不会自行创建会话、定时任务或云端上传。

0.7.1 支持在回看中校准体验事件的起止时间、名称、概述、问题与感受、备注。原 agent 结果保持不变，手动修正独立保存在 `experience-event-edits.json`。下次整理读取 `evidence.manual_corrections` 的字段差异和 diff，并提交当前 `corrections_review` 采纳说明；漏读或并发新修改会阻止覆盖。事件阅读顺序为概述、具体问题、弱化备注、默认收起的证据。
## 词库衔接

0.7.5 起，已授权补词的外部 agent 可通过运行中应用的 `vocabulary-status`、`vocabulary-preview`、`vocabulary-apply` 刷新指定预设快照。源 TXT 更新不等于预设已生效；完整步骤及冲突处理见 [本机词库接口](vocabulary-agent.md)。该操作不重转写、不改历史场次，也不启动监听任务。
