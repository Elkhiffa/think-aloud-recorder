# 研究 B：职业游戏用户研究（GUR）团队如何分析 playtest / think-aloud，又如何把发现交给设计师

- 检索日期：2026-10-20；工具：WebSearch + WebFetch（不少 PDF、ACM、OUP 正文在付费墙后，或抓取时返回二进制，没能读到）
- 用途：评估「think-aloud 自玩录像 → 跨 session 洞察报告」agent 流程。用户的抱怨是：agent 组织问题太自下而上，职业做法更自上而下。
- 引用规则：英文原文直接引用每处不超过 15 个词，其余都是转述。原始来源的标题保留原文。

## 来源可信度标记（每条论断后都会标一个）

| 标记 | 含义 |
|---|---|
| 【一手·已读】 | 作者本人撰写的页面，已抓取并读过正文 |
| 【一手·摘要/目录】 | 只读到摘要、关键词或章节目录（多为 OUP 2018 书的章节、GDC Vault 场次页），**正文主张不能归给它们** |
| 【二手·已读】 | 访谈、新闻或第三方综述，已读过正文 |
| 【仅搜索摘要】 | 只看过搜索引擎给的摘要，原页面没抓到或抓取失败，**证据最弱** |

---

## 0. 先说结论

1. **职业 GUR 的框定是自上而下的。** 研究开始前，先和设计、制作一起定研究目标（research objectives），再把每个目标对应的设计意图问清楚：玩家在这里应该理解什么、能做到什么、有什么感受。分析的时候，先把发现**按目标、关卡或机制分组**，再在组内提炼出各自独立的问题。每条问题写成「意图和实际体验的偏差」，加上「游戏里的原因」和「对玩家的影响」（Bromley 2021/2022【一手·已读】）。
2. **合并的判据是「修复是否相同」，不看描述像不像。** 两条观察如果原因相同、一个修复能同时解决，就并成一个问题，即使发生在不同地方。如果需要不同的修复，就算描述的是同一个对象，也要拆开（Bromley 的 jetpack 例子【一手·已读】）。这一条最直接地对治「自下而上、碎片化」。
3. **报告不能从第一条细碎问题开始写。** 开头放一句论点级的洞察（thesis statement），接着是一页摘要：哪里最需要关注、游戏整体状态如何。然后依次是分组问题、问题详情、下一步（Bromley 2022【一手·已读】）。发现太多会稀释影响力。
4. **严重度靠固定的几个问题来判定，不靠出现次数。** 三个问题是：是否阻断推进、是否需要外部帮助、是否反复踩坑。主观意见单独走一条通道，同样拿设计意图来衡量（Bromley 2023【一手·已读】）。
5. **交付方式是现场 debrief 加行动工作坊。** 默认由团队出方案，研究员把问题写成「我们如何才能……」（how might we, HMW）式的挑战，而不是直接给答案（Bromley 2021【一手·已读】；Hodent 2015【一手·已读】）。
6. **针对本项目的关键提醒：** 语料来自设计师本人自玩，N=1。这更接近专家评审或启发式评估，而不是外部玩家测试。Hodent 所说的「知识的诅咒」（curse of knowledge，指熟悉设计的人很难客观看待它）是直接的局限。职业界对应的做法是**用启发式清单做演绎式（自上而下）编码**（Desurvire & Wixon 2018【一手·摘要/目录】；Laitinen 2006【一手·已读（摘要页）】）。

---

## 1. RQ1：职业团队如何自上而下地框定研究，又如何组织发现

### 1.1 研究目标来自团队，而不是来自数据

- **研究目标由设计、制作提出，在启动会上和各条线负责人一起收敛。** 先选目标，后选方法，否则方法会限制能回答的问题。没有其他成员参与的目标设定是危险信号，因为这会降低发现被采纳的概率。启动会之后要把议定的目标写下来分发，**本次答不了的目标也要记下来**，留给后续研究。——Steve Bromley, "Defining research objectives", gamesuserresearch.com, 2021-01-01【一手·已读】 https://gamesuserresearch.com/defining-research-objectives/
- **研究目标分三类，每类对应一种方法**（Bromley, "Designing a games user research study", 2021-01-01【一手·已读】 https://gamesuserresearch.com/designing-a-games-user-research-study/）：
  - 理解或能力类（玩家是否理解喷气背包、Boss 打法、下一步去哪）：观察行为，并追问行为背后的原因
  - 平衡类（难度、多人地图）：记录游戏内事件，再和设计师的意图对比
  - 体验类（跳跃手感、追逐戏是否好玩）：了解玩家怎么想、为什么这么想、有多大比例的玩家同意
- **测量结果只有和设计意图对照才有意义。** 同一个「死了 3 次」，可能说明太简单、太难，也可能刚刚好，取决于设计师想要什么。因此要在研究前确认意图，预先定义什么算好、什么算坏的结果。（同上【一手·已读】）
- **可用性问题的定义本身就是自上而下的：** 玩家做不到团队预期他们做的事，就是可用性问题。设计意图就是团队预期玩家理解和做到的东西，要向设计师、UI 美术、关卡设计逐一问清，然后拿它来识别「意外行为」。——Bromley, "Find usability issues in games with playtests", 2022-05-24【一手·已读】 https://gamesuserresearch.com/find-usability-issues-in-games-with-playtests/
- **观察之前先把记录框架搭好。** Sangin 那一章的目录依次是：先澄清研究目标和业务需求，再理解玩家体验、准备数据采集策略、编排笔记指南（note-taking guide），然后才进入观察。——Mirweis Sangin, "Observing the player experience", in *Games User Research* (Drachen, Mirza-Babaei, Nacke eds., OUP 2018), ch.11【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195456889

### 1.2 「意图对照」是业界共识，而不是某一个人的方法

- **Hodent（前 Epic UX 负责人）把 UX 的目的定义为交付设计师想要的体验，而不是把游戏做简单。** 原话是："We are here to help the developers convey their vision." 她举的例子是《生化危机》：如果目的是制造恐惧，堵死一条逃生路线可能正是设计意图。是否要修，由 UX 和设计共同决定。——Celia Hodent, "5 Misconceptions about UX in Video Games", 2015-04-02（2022 更新）【一手·已读】 https://celiahodent.com/five-misconceptions-ux/
- **意图与实际偏离的实例（Fortnite 采集系统）。** 设计师核对过采集数值，玩家却仍觉得「肝」。测试发现，玩家根本没用数值平衡所依赖的「弱点」机制。于是先迭代 UI，最后把该功能并入技能树。——Hodent, "Understanding the Success of Fortnite: A UX & Psychology Perspective", 2019-07-22（2020 更新）【一手·已读】 https://celiahodent.com/understanding-the-success-of-fortnite-ux/
- **知识的诅咒：** 设计者熟悉自己的设计，所以很难客观判断，必须找目标受众来确认他们感知到的就是想要的体验。——DigiPen 新闻稿转述 Hodent, 2018-10-17【二手·已读】 https://www.digipen.edu/showcase/news/dr-celia-hodent-brings-ux-insight-from-fortnite-to-digipen/
- **前 Epic UX 研究总监 Ben Taels 的说法：** UXR 的核心是确保设计师想要的体验（包括**有意设计的摩擦和难度**）真正到达玩家；同时要找出阻碍设计的意外摩擦，以及计划外但正面的涌现体验。数据用来辅助设计判断（inform），而不是由数据决定设计（drive）。——Luke Plunkett 访谈, Aftermath, 2025-07-30【二手·已读（一手口述）】 https://aftermath.site/video-games-user-experience-ux-research.md
- **PlaytestCloud（Kulik）：** 成功标准要按预期体验来定义，而不是笼统地问「好不好玩」，例如恐怖游戏就不应该让人觉得舒适。玩家的反馈只能当作体验的证据，不能当作诊断：玩家说「太难」，真正的原因可能是说明不清、反馈太弱或引导太差。——Jozef Kulik, "The 4 Ingredients of Effective Games User Research", PlaytestCloud blog, 2026-04-15【一手·已读】 https://start.playtestcloud.com/blog/the-4-ingredients-of-effective-games-user-research
- **学术上把「意图对照」做成了工具（GURB）。** GURB 把设计师预期的玩家体验和测试实测结果并排放置，让问题带着上下文一起汇报。案例和开发者访谈都显示，它改善了跨职能沟通。——Naeem Moosajee, *GURB: the game user research blueprint*, MSc thesis, UOIT, 2016（导师 Mirza-Babaei & Nacke）【一手·已读（摘要页）】 https://ontariotechu.scholaris.ca/items/8d57f0d0-8c00-4bde-9d33-67bb215cf0eb/full
- **Bungie《命运》：** 这场演讲的简介提到，团队做过研究，检验新 IP 的角色美术是否符合美术的意图。——John Hopson, "User Research on Destiny", GDC 2015【一手·摘要/目录】 https://gdcvault.com/play/1022354/User-Research-on

### 1.3 分层评估模型：先按层级，后按问题

- **Player Research 的分层模型。** McAllister & Long 那一章的目录里有「五层模型（F2P）」和「四层模型（买断制）」。摘要说明，每种方法都按它在吸引力（appeal）、理解、可用性、体验、变现这几层上的作用来评估。——Graham McAllister & Sebastian Long, "A framework for player research", OUP 2018, ch.8【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195455905
- **同一模型在 2013 年访谈里的表述：** 变现建立在理解、可用性、体验这三层之上。玩家不理解游戏，也就不会理解怎么付费。——PocketGamer.biz 访谈 McAllister, 2013【仅搜索摘要】 https://www.pocketgamer.biz/the-key-to-f2p-success-know-your-player-says-player-research/

### 1.4 发现的组织轴：业界实际用过的几种

| 组织轴 | 来源 | 适用场景 | 风险 |
|---|---|---|---|
| **按研究目标 / 关卡 / 机制先分组**，组内再提炼独立问题 | Bromley "Analysing a games user research study" 2021【一手·已读】 https://gamesuserresearch.com/analysing-a-games-user-research-study/ | 默认做法，分析的第 2 步 | 目标定得太散时，分组也会散 |
| **按机制（如合成）、问题类型（如 UI）或「洞察类别」分组**；研究目标可以提示怎么分组 | Bromley "How to write a games user research report" 2022-02-15【一手·已读】 https://gamesuserresearch.com/how-to-write-a-games-user-research-report/ | 报告层面的分组 | 只按 UI 类型分组时，容易丢掉体验层的论点 |
| **组与组之间按玩家遭遇顺序（线性游戏）或严重度排序**，组内也按严重度或时间顺序排 | 同上 | 线性内容、新手引导（FTUE） | 开放世界不适合纯时间顺序 |
| **按研究问题建立层级**，每条洞察带一个严重度 | Laure Duchamp 的做法，见 Bromley "Sharing Games User Research Findings" 2021【一手·已读】 https://gamesuserresearch.com/sharing-games-user-research-findings | debrief 时控制讨论范围 | — |
| **每个目标一节，节内每个主题一页**，并解释玩家为什么这么说 | PlaytestCloud "player interviews part 3"【仅搜索摘要】 https://start.playtestcloud.com/blog/player-interviews-part3 | 访谈类数据 | — |
| **按项目的关键挑战**组织（规模、战斗、职业与玩家自主性、玩法风格多样性），再列研究贡献（合成界面、导航、移动、头像与状态条） | James Berg, "Dissecting the Dragon: GUR for Dragon Age: Inquisition", OUP 2018 ch.23【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195461114 | 大型 RPG / 开放世界的复盘 | 只有目录，看不到正文怎么写 |
| **按 onboarding 阶段**：核心信息与障碍 → 主要机制 → 目标与成长路径 → 沉浸。四个阶段可以重叠 | Hodent, "The Gamer's Brain, Part 2: UX of Onboarding" GDC16, 2016-03-22【一手·已读】 https://celiahodent.com/gamers-brain-ux-onboarding/ | 新手引导、养成系统的学习曲线 | 「按阶段组织发现」是从她的框架推出来的做法，不是她原文里的报告指令 |
| **按启发式类别**：PLAY 的四类是玩法；沉浸与投入；可用性与机制；新玩家体验 | Desurvire & Wixon, "Heuristics uncovered…", OUP 2018 ch.14【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195457780 | 专家评审、自玩 | — |
| **按主题自动归类**：可用性、游戏设计、乐趣、变现、挫败 | PlaytestCloud AI "First Findings" 产品页【仅搜索摘要】 https://start.playtestcloud.com/product-updates/meet-first-findings-a-completely-revamped-ai-analysis-experience-across-your-entire-playtest | 一款 AI 产品的做法，可以作为对标 | 这是商业产品，不代表研究员的实践 |

**观察：** 以上组织轴没有一个是「把问题平铺后按出现频次聚类」。它们的第一层永远是研究目标、系统或机制、旅程阶段、项目挑战或启发式类别这类**预先定义的骨架**，问题只挂在骨架下面。

---

## 2. RQ2：问题的格式、严重度、建议、数量

### 2.1 Bromley 的分析流水线（2021，最完整的一手描述）【一手·已读】
来源：https://gamesuserresearch.com/analysing-a-games-user-research-study/

1. 从原始笔记、访谈、问卷里找「玩家体验偏离设计意图」的迹象，再追问原因。**同时记录哪些地方按意图工作了**，避免团队改坏它们。
2. 删掉不表示问题、也不提供有用数据的笔记，剩下的**按研究目标分组**（例如同一关卡、同一机制）。
3. **在组内提炼独立的问题。** 判据是团队是否需要分别给出修复。jetpack 例子：教程里和第 3 关里漏看了同一个视觉提示，原因相同，算一个问题；忘记操作是「回忆」层面的问题，单独算一个。
4. **原因要写成游戏的某个属性**（物件、关卡设计、之前的段落）。如果原因写成「玩家不理解」，说明还要继续深挖。一个问题可以有多个原因。**不要把方案写成原因**，例如「缺少教程」就直接指向了某一个修复。
5. **影响要写玩家这一侧：** 和预期体验差在哪里、卡了多久、几个人需要主持人帮忙、是否阻断推进。
6. **固定格式：** 问题陈述，加一条或多条原因，加一条或多条影响。
   - 例子（转述）：问题是「洞穴附近的谜题不清楚怎么完成」。原因是谜题灰色，混在混凝土墙面里。影响 1 是玩家没把它看成正确的前进路线，继续在洞里乱转。影响 2 是玩家回头走了最多 30 分钟，部分人需要主持人帮助。
7. 定严重度（见 2.2）。
8. **分析完成之前不要分享初步结果**，否则可能让团队去修错问题。在很多工作室里，正常规模的研究 24 小时内就能分析完。

### 2.2 严重度：固定问题，而不是频次

- **四档：Critical / High / Medium / Low。** 每条问题从 Low 起步，下面每个「是」上调一档：
  1. 玩家是否必须完成它才能推进？
  2. 主持人是否需要介入？
  3. 是否持续？（原文措辞是「克服后玩家是否知道下次怎么避免」，方向和「持续」相反。按 2023 年那篇文章的解释，这里应理解为「同一玩家是否反复踩坑」。）
  - 有的工作室把第 3 问换成「出现得有多频繁」。Bromley 认为两种都不完美，选定一种后要一致执行。**这套问题只适用于可用性问题。**
  - 出处：Bromley "Analysing…" 2021 / "Find usability issues…" 2022【一手·已读】
- **2023 年版本的三问：** 是不是核心体验？是不是难以克服？（「卡多久可以接受」要事先和团队约好。）是不是持续？「持续」指同一玩家反复遇到，**不是**有多少玩家遇到。作者明确提醒，在定性研究里按受影响人数排优先级有风险。——Bromley, "How to prioritise playtest issues and player feedback", 2023-04-06【一手·已读】 https://gamesuserresearch.com/how-to-prioritise-playtest-issues-and-player-feedback/
- **主观意见单独走一条通道。** 先确认样本有代表性（线上社区声音更大、更极端）。部分负面反馈本来就是设计意图。要和设计师一起把预期体验定义得尽可能具体（例如推进前玩家必须理解或做到什么），再拿反馈去对照。衡量维度是：偏离意图多远、是否造成显著挫败、有多少人持同样看法（要量化以后才能下判断）。（同上【一手·已读】）
- **关于「占多少比例的参与者」，各家有分歧：**
  - Bromley 反对在小样本定性研究里按人数排序（同上）。
  - Desurvire 的报告会写清出了什么问题、多少玩家遇到、原因是什么，建议则视团队需要而定（PlaytestCloud 访谈 Heather Desurvire Part 2, 2017-08-06【二手·已读】 https://start.playtestcloud.com/blog/deep-dive-into-games-user-research-with-heather-desurvire-part-two-of-two）。
  - 结论：「人数」可以作为证据写进去，但**不能单独决定严重度**。

### 2.3 原因的分类框架：Hodent 的认知机制

- **知觉（perception）：** 玩家按自己的经验和语境来解读符号。图标对某些玩家毫无意义。错误的可供性（false affordance）会把玩家引向错误操作，而且很难纠正。
- **注意（attention）：** 注意力有限。战斗中会漏看重要消息（无意视盲）。多路输入重叠时（比如驾驶教学中 NPC 在说话），学习会受损。
- **记忆（memory）：** 有三种失败：编码不足（处理太浅）、存储不足（随时间遗忘）、提取不足（信息还在但调不出来，对策是提供提醒，比如把目标钉在 HUD 上）。
- **评估方法：** 不要问玩家「清不清楚」，要问「为什么」。玩家常说目标很清楚，却解释不出来。过 20 分钟再检查一次，看他们是否还记得。——Hodent, Gamer's Brain Part 2, 2016【一手·已读】 https://celiahodent.com/gamers-brain-ux-onboarding/
- **和本项目「通知」主题直接相关的实例：** Epic 曾把红色大量用在次要通知上，削弱了玩家对真实伤害的注意。装饰用的电火花被误认为发电机（错误的可供性）。——Hodent, "Developing UX Practices at Epic Games", 2015-03-16【一手·已读】 https://celiahodent.com/ux-practices-epic-games/
- **找根因的实例：** 玩家抱怨敌人体型，测试发现真正的原因是寻路导致敌人急转弯（Hodent 2015 Misconceptions【一手·已读】）。这是「玩家说的原因不等于真实原因」的典型例子。

### 2.4 报告结构

- **Bromley 2022【一手·已读】**（https://gamesuserresearch.com/how-to-write-a-games-user-research-report/）的结构：
  - 一页摘要：最重要的发现、最需要关注的区域、游戏整体状态。检验标准是「能不能在一次简短对话里讲清楚」。
  - 背景：说明这项研究为什么重要、为什么现在做，而不是只写日期和流程。
  - 分组问题 → 详细问题 → 下一步 → 附录数据。
  - **最重要的洞察排在最前面，它可以是一句论点，而不是某条细碎的 UX 问题。**
  - 每条问题都要对照预期体验和实际体验，并写出原因（方便团队定位修复点）和影响（方便排优先级）。
  - 更丰富的发现（例如关于玩家的普遍规律）可能不适合「原因 / 影响」格式。
  - 受众分层：设计、美术、程序要看全部细节；制作人和高管只需要知道问题的规模和需要投入多少关注。
  - 一页只讲一个发现，用平实的语言。
  - 列出的失败模式：只罗列发现的平淡报告容易被忘掉；发现太多会稀释影响力；把报告本身当成目标，而不是把改进游戏当成目标。
- **Mirza-Babaei 那一章的目录**（OUP 2018 ch.18【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195460088）：
  - 常见章节：目的、研究设计与方法、执行摘要与严重度、发现描述、下一步。
  - 报告形态有六种：短笔记、完整报告、表格式报告、**体验曲线图报告（experience graph report）**、演示文稿式报告、可交互定制报告。
  - 摘要的核心主张是：沟通方式和发现本身同样重要，好研究可能因为讲不清而无法带来改变。
- **PlaytestCloud（Chris Hugelmann, "Writing A Playtest Report", 2020-08-05【一手·已读】 https://start.playtestcloud.com/blog/writing-a-playtest-report）：**
  - 同样是五节：目的、方法、执行摘要、发现、下一步。
  - 每条发现要给出推理过程，可以用自己的话，也可以用玩家原话。
  - 引语要切题，不要堆砌。
  - 离群发现也要保留，因为它们代表不同类型的玩家。

### 2.5 建议，还是交给设计师

- **默认交给团队解决。** 研究员缺乏其他职能的领域知识，给出的方案可能显得幼稚，还会收窄团队的创意空间。更好的做法是把问题写成 HMW 式的挑战。只有在无法和团队直接沟通时，才附上建议。——Bromley, "Debriefing a study", 2021-01-06【一手·已读】 https://gamesuserresearch.com/debriefing-a-study/
- **原因描述里不能夹带方案**（Bromley Analysing 2021【一手·已读】）。有的团队会在报告里附建议或方案提示（Bromley Report 2022【一手·已读】）。
- **Desurvire：** 建议可选；报告里注明设计师才是自己游戏的专家（2017 访谈【二手·已读】）。
- **RITE 的另一种取向：** 方法来自 Medlock, Wixon, Terrano, Romero, Fulton (2002, UPA proceedings)，我**没有读到原文**。
  - 二手综述能确认的内容：每位参与者测完后，测试团队开会决定是否不改设计继续测；如果要改，就暂停测试，等修订版出来。《帝国时代 II》案例中，前 10 名参与者测试期间快速迭代，之后 6 名参与者都不再需要改动，这一段就是「验证步骤」。综述作者指出，很少有实践者真正完成验证步骤。——Lewis & Sauro, "Ten Things to Know about the RITE Method", MeasuringU, 2020-04-01【二手·已读】 https://measuringu.com/rite-method/
  - 「问题确认、方案也清楚就立刻改」这一表述只出现在搜索摘要和维基百科中【仅搜索摘要】 https://en.wikipedia.org/wiki/RITE_Method

### 2.6 一份报告通常有多少条问题

- **没有找到任何来源给出典型数量**（标记为缺口）。能找到的只有定性约束：
  - 一次研究可能发现「很多问题」，所以方法的重点是排序，而不是限量（Bromley 2023）。
  - 发现太多会稀释影响力，只挑团队现在需要的（Bromley 2022）。
  - 可以只发一封列出前 5 个问题的邮件（Bromley Sharing 2021）。
  - 研究范围太大时，团队学到的东西太多，反而全部变成噪音（Bromley "Scope your studies to increase research impact"【仅搜索摘要】 https://gamesuserresearch.com/scope-your-studies-to-increase-research-impact/）。

---

## 3. RQ3：游戏里的 think-aloud、专家自玩、启发式评估

### 3.1 Think-aloud 的方法学

- **Knoll 那一章**（OUP 2018 ch.12【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195457270）的目录涵盖：为什么在 GUR 里用 think-aloud、由谁主持、如何采集、局限、回溯式 think-aloud（RTA）、与其他方法结合。儿童一节里写到，自发的话语和行为与被提示的话语同样重要（这里只有标题，正文没读到）。
- **Bromley 的立场：** think-aloud 通常不自然。**合作游戏是例外**，玩家要互相解释机制，能比较真实地暴露他们的理解。——Bromley, "Games User Research Methods", 2020-12-20【一手·已读】 https://gamesuserresearch.com/?p=2664
- **Laitinen 2006：** 建议游戏测试把 think-aloud 环节和不打断的自由游玩混合使用，因为不能总去打断玩家。专家评估和用户测试给开发者带来的数据，开发者评价为新颖且有用。是不是玩家出身的专家，找到的问题在数量和相关性上没有明显差别。——Sauli Laitinen, "Do Usability Expert Evaluation and Testing Provide Novel and Useful Data for Game Development?", *Journal of Usability Studies* 1(2), 2006【一手·已读（摘要页）】 https://uxpajournal.org/wp-content/uploads/sites/7/pdf/JUS_Laitinen_Feb2006.pdf
- **视频提示的回溯评论：** 赛后用游戏录像加一份词表来提示玩家回顾，在一款 TPS 教程关做了先导研究。——Gow, Cairns, Colton, Miller, Baumgarten, "Capturing Player Experience with Post-Game Commentaries", 2010【仅搜索摘要（PDF 抓到的是二进制，没能读）】 https://www-users.york.ac.uk/~pc530/pubs/Gow_cgat2010.pdf
- **口述和生理数据之间存在错位：** 很多明显的生理反应没有出现在视频提示的 RTA 口述里，而一些口述中「有意思」的体验在生理数据里也看不到。——Tan, Leong, Shen, "Combining think-aloud and physiological data to understand video game experiences", CHI 2014, pp.381–390【一手·已读（摘要页）】 https://opus.lib.uts.edu.au/handle/10453/41566
  - **启示：** 单凭口述会漏掉玩家没说出口的体验，需要用行为、事件或画面来三角互证。
- **同步（CTA）还是回溯（RTA）：一般可用性研究的证据，不是游戏：**
  - van den Haak, de Jong, Schellens（在线图书馆目录）发现两者找出的问题集合相当，但浮现方式不同；同步口述会损害任务表现【仅搜索摘要】 https://www.semanticscholar.org/paper/Retrospective-vs.-concurrent-think-aloud-protocols:-Haak-Jong/bf7270b4c89944ab2e58c666d36a6e7815f131ea
  - Alhadreti & Mayhew 的比较研究认为同步法更好，并报告没有观察到反应性（reactivity，即口述本身改变了被测行为）【仅搜索摘要】 https://ueaeprints.uea.ac.uk/id/eprint/65771/
  - Hertzum 2024 年在 ACM TOCHI 31(3) 发表了一篇元分析，**结论未读到**（PDF 超过抓取上限）。
  - **游戏专项的反应性实证研究没有找到**，这是一个缺口。

### 3.2 专家自玩、设计者自评

- **Hodent 的知识的诅咒（见 1.2）。** 设计者没法客观评估自己的设计，首次体验尤其如此。一份实践指南也认为，开发者积累的隐性知识让他们无法评价首次体验和新手引导【仅搜索摘要】 https://bugnet.io/blog/what-is-playtesting 。
- **Taels：** 观察到的行为比自我陈述更可靠。「按 Tab」的例子说明，心智模型的错位只有在研究员追问「为什么不按」时才会暴露（Aftermath 2025【二手·已读】）。
- **对本项目的含义：** 自玩 think-aloud 的价值落在「专家评审」那一侧（Laitinen 2006 支持这类数据对开发者新颖有用），但不能声称代表目标玩家的首次体验。

### 3.3 启发式作为自上而下的编码框架

- **Hodent 的游戏 UX 框架**（Fortnite 2019 页面【一手·已读】，原文名称）：
  - 可用性有 7 条：**Signs and feedback / Clarity / Form follows function / Consistency / Minimum workload / Error prevention and recovery / Flexibility and accessibility**
  - 「可投入性」（engage-ability）有 3 根支柱：**Motivation**（内在 / 外在动机，自我决定理论 SDT 的胜任、自主、关联）；**Emotion**（游戏手感，即相机、操控、角色这「3C」，加上临场感等）；**Game flow**（挑战、节奏、onboarding）
- **Desurvire & Wixon（OUP 2018 ch.14）**【一手·摘要/目录】：
  - 介绍 PLAY（四类：玩法 / 沉浸与投入 / 可用性与机制 / 新玩家体验）和 GAP（入门友好性：演示与练习、带反馈的动作演示、自我效能、知识迁移）两套启发式。
  - 目录中有「归纳法」「演绎法」，以及「**符合项 / 违反项 / 增强项**（adherences, violations, enhancements）」，也就是说启发式评估同时记录正面发现和改进机会。
  - 摘要称，启发式比非正式评审有效得多，有助于发现问题、提出修复，并识别有效的设计元素。
- **Pinelle, Wong, Stach, "Heuristic Evaluation for Games", CHI 2008：** 分析了 108 款游戏（6 个类型各 18 款）的评测，归纳出 12 类问题和 10 条启发式【仅搜索摘要；10 条原文没核对】 DOI 10.1145/1357054.1357282
- **Paavilainen 等（OUP 2018 ch.15）**【一手·摘要/目录】：F2P 启发式 FP1–FP6，包括不付费也能推进、内购信息清晰、内购有实际价值、可以对未成年人关闭内购、硬通货能靠游戏获得、付费与不付费玩家之间公平。和本项目的养成、成长线直接相关。 https://academic.oup.com/book/26677/chapter/195458662

---

## 4. RQ4：发现如何到达设计师手里

- **Bromley "Debriefing a study" 2021【一手·已读】：**
  - 现场讲解比发报告好，因为听众可以当场提问。
  - 讲解顺序：重申研究目标 → 简述方法和受众 → 按优先级逐条讲问题。
  - 紧接着开工作坊，每个问题走一轮：个人独立构思约 5 分钟 → 小组讨论评估 → 投票决定探索哪些方向 → 指定负责人。
  - 通常由制作人排优先级、分派任务。
  - 失败模式：只发报告不讲解；缺少背景信息（版本、任务、方法），后来的人看不懂；方案收窄了团队的思路；用省事的修法（比如再加一个教程）而不考虑它出现的时机；把 debrief 当成终点、不复测。
- **Bromley "Stop Being Ignored" 2025-08-08【一手·已读】** https://gamesuserresearch.com/stop-being-ignored-four-steps-to-increase-playtest-impact/ 提出四步：
  1. 让研究对齐决策者在意的事。
  2. 开放现场观看（团队很少回看录像）。
  3. **让设计师一起做综合**：大家现场分享观察、贴便签归主题，同时尽早纠正误解。
  4. 用行动工作坊推动团队行动，并和制作一起把行动排进待办列表（backlog）。
  - 发现被忽视的原因：决策者时间紧，玩家体验「很少是急事」；报告常被略读；团队衡量的是产出（做了几场研究）而不是结果（研究有没有改变方向）。
- **Bromley "Sharing…" 2021【一手·已读】：**
  - 交付形态要匹配团队，可选：工作坊、列出前 5 个问题的邮件、Slack 消息、**可查询的洞察库**、开放原始数据、直接对话。
  - Raphael Leroy 建议在报告开头放速读要点。
- **Hodent：** 是否修复，由 UX 和设计联合决定（Misconceptions 2015）。来自测试、专家评审、分析数据的反馈偏差最小，应该优先于其他意见（同上）【一手·已读】。
- **Halo 3 / Bungie 与微软的合作：** NPR 报道过两个改动：新目标出现时在屏幕上闪烁；因为太多玩家飞下公路摔死，加装了护栏【仅搜索摘要】 https://www.npr.org/transcripts/14649338 。Wixon & Pagulayan, "That's Entertainment – Halo 3: the theory and practice of a research-design partnership", *ACM Interactions* 2008【一手·摘要】 https://www.microsoft.com/en-us/research/publication/thats-entertainment-halo-3-the-theory-and-practice-of-a-research-design-partnership/ 。正文没读到，研究与设计如何协作的具体机制无法核实。
- **设计师觉得最有用的东西：** 能直接说明这一点的研究，我**只找到 GURB 一项**（跨职能沟通、简洁、及时）。其余都是研究员视角的经验之谈，这是一个缺口。

### 4.1 失败模式汇总（都有出处）
| 失败模式 | 出处 |
|---|---|
| 罗列式报告，平淡易忘；发现太多导致稀释 | Bromley Report 2022【一手·已读】 |
| 只发报告不讲解，没法消除误解 | Bromley Debrief 2021 / Sharing 2021【一手·已读】 |
| 研究目标没有团队参与，发现没人用 | Bromley Objectives 2021【一手·已读】 |
| 没有意图背景，同一个数据无法判断好坏（「死 3 次」例） | Bromley Designing 2021【一手·已读】 |
| 把玩家给的原因当诊断（「太难」其实是引导问题；「敌人体型」其实是寻路问题） | Kulik 2026；Hodent 2015【一手·已读】 |
| 把方案写成原因（「缺少教程」） | Bromley Analysing 2021【一手·已读】 |
| 分析没完成就分享初步结论，团队去修错问题 | 同上 |
| 研究员给出的方案太幼稚或收窄创意 | Bromley Debrief 2021【一手·已读】 |
| 衡量产出不衡量结果 | Bromley 2025【一手·已读】 |

---

## 5. RQ5：多人 / MMO / 长线运营专项

- **《命运》的团队式研究：** 硬核终局 raid（多人团本）用现成的玩家公会来测试。工具包括眼动、拨盘测试（dial testing）、3D 引擎内数据可视化、Hadoop 大数据，并产出了核心的「杂食型」（omnivore）玩家原型。——Hopson, GDC 2015【一手·摘要/目录】 https://gdcvault.com/play/1022354/User-Research-on
- **多人测试的实务限制：** 一名研究员很难同时可靠地观察「超过一两名参与者」，因此要增派研究员，并依赖问卷加数据分析（例如死亡、失败次数配合问卷，检查玩家体验是否符合意图）。合作玩法里的自然交流能暴露玩家的理解。——Bromley Methods 2020【一手·已读】
- **联网多人启发式（NGH）：** 从 382 篇联网 PC 游戏评测中归纳出 10 类问题，范围从会话管理到作弊，再到新手训练。动机在于联网游戏依赖玩家之间的沟通与协作，而当时的方法没有覆盖这一点。——Pinelle, Wong, Stach, Gutwin, "Usability Heuristics for Networked Multiplayer Games", GROUP 2009【仅搜索摘要；10 条原文没核对】 https://dl.eusset.eu/handle/20.500.12015/4868
- **移动端多人可玩性启发式：** Korhonen & Koivisto, "Playability heuristics for mobile multi-player games", DIMEA 2007【仅搜索摘要】
- **上线后研究：** Livingston 那一章的目录涵盖上线后的沟通、session 与问题、流程，以及实时数据与遥测报表。另有「评测分析」（review analysis，RVA），用扎根理论做竞品或口碑基准，流程是计划 → 采集 → 分析 → 报告。——Ian Livingston, "Post-launch in Games User Research", OUP 2018 ch.4【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195455393
- **遥测加定性三角互证：** Drachen & Connor 那一章有「三角互证」（Triangulation）、「实时假设检验」、「纳入业务指标」等小节。——OUP 2018 ch.19【一手·摘要/目录】 https://academic.oup.com/book/26677/chapter/195460224 。另有资料指出，行为遥测只能告诉你玩家做了什么，没法验证为什么，需要配合体验测量【仅搜索摘要】 https://gameanalytics.com/?p=3902 。Tan 等 2014（见 3.1）则说明，口述本身也有盲区。
- **Riot：** Nathan Blau 在 GDC 讲过如何用英雄遥测和大规模英雄调查（"Mass Champion Survey"）支撑团队、产品、工作室三个层级的决策，以及下一个改哪个英雄【仅搜索摘要；链接是 GDC Vault 的联系页，场次页没有定位到】 https://gdcvault.com/play/1026252/contactUs
- **F2P onboarding（和国内 F2P 语境相关）：** 腾讯基于 8 年、100 多款 F2P 手游提出 AGE 模型：Attraction（吸引）、Goal（目标）、Effectiveness（教学有效性）。——Fan Yi & Xingyu Zhang, "Start Right, Start Fun…", GDC 2024（赞助场次）【一手·摘要/目录】 https://gdcvault.com/play/1034684/Start-Right-Start-Fun-Unveiling
- **缺口：** 没有找到专门研究「MMO Boss 机制如何向团队传达、如何让玩家读懂」的 GUR 一手资料。最接近的是 NGH（沟通与协作类问题）和《命运》用公会测 raid 的做法（只有摘要）。

---

## 6. 本项目专项：N=1 设计师自玩 think-aloud，哪些职业做法能迁移

| 职业做法 | 能否迁移 | 理由 |
|---|---|---|
| 「主持人是否介入」作为严重度问题 | **不能** | 自玩没有主持人。可以换成「是否需要查外部资料或攻略才能继续」，这和 Bromley 2023 年版本里「被迫寻求外部帮助算难以克服」一致 |
| 「多少比例的参与者遇到」 | **不能** | N=1。Bromley 本来就反对在小样本里按人数排序 |
| 「持续性」（同一人反复踩坑） | **能，而且有优势** | 46 个 session、40 小时，天然可以跨 session 检查同一问题是否复现、学会以后是否又忘（对应 Hodent 的存储 / 提取失败） |
| 设计意图对照 | **能，但意图来源要显式** | 自玩者兼任设计师，意图可能是本人的预期，而不是项目方的设计意图。每条发现都要标明意图从哪来 |
| 首次体验与新手引导的结论 | **要打折扣** | 知识的诅咒（Hodent 2018）。设计师不是目标玩家 |
| 演绎式启发式编码（PLAY / GAP / Hodent 7+3 / NGH / F2P） | **能，而且是最贴近的职业对应物** | 专家评审本来就是这种范式（Desurvire & Wixon 2018；Laitinen 2006） |
| 口述内容与行为、画面三角互证 | **能** | Tan 等 2014 证明口述有盲区，录像画面可以补足 |
| 记录按意图运作的部分（正面发现） | **能** | Bromley 2021；Desurvire 的「符合项」 |

---

## 7. 对 agent 流程的启示（12 条可核查做法）

每条后面附「怎么核查」：拿 agent 的一份产出就能逐条判定是否做到。

1. **每条发现都写明它偏离的设计意图，并标出意图的来源**（项目文档 / 设计师陈述 / 自玩者推断）。
   - 怎么核查：随机抽 10 条，看是否都有「预期：…」字段，并带来源标签。
   - 依据：Bromley Find usability issues 2022、Designing 2021；Hodent Fortnite 2019；GURB 2016。
2. **先搭骨架，再挂问题。** 报告第一层是预先定义的轴：研究目标或系统（如 Boss 机制沟通、养成 UI、跨界面目标丢失、手柄、通知），可以再按旅程阶段（FTUE / 中期 / 终局）交叉。问题只能挂在骨架节点下，不允许按相似度自由聚类当作第一层。
   - 怎么核查：一级标题是否全部来自预先声明的分类表。
   - 依据：Bromley Analysing 2021 第 2 步、Report 2022；Hodent onboarding 阶段 2016；PlaytestCloud 每目标一节。
3. **报告以 1–3 句论点级洞察开头，加一页摘要**（最需要关注的区域和整体状态），而不是从第一条细碎问题开始。
   - 怎么核查：第一屏能否在 30 秒内复述出「这游戏在 X 上的体验和意图差多远、为什么」。
   - 依据：Bromley Report 2022。
4. **合并规则改成「是否需要同一个修复」。** 原因相同就合并，即使跨 session、跨界面；需要不同修复就拆开，即使描述的是同一个对象。
   - 怎么核查：每个合并簇写一句「共同原因」；拆开的一对写一句「为什么需要不同修复」。
   - 依据：Bromley Analysing 2021 jetpack 例。
5. **问题固定写成三段：陈述、原因、影响。** 原因必须是游戏的属性（物件、布局、信息架构、之前的流程）。出现「玩家不理解」这类原因时，标记为「待深挖」。原因里不能出现方案（「缺少引导」这种说法不合格）。
   - 怎么核查：可以用正则检查原因字段里有没有「缺少 / 没有 / 应该加」之类的方案措辞。
   - 依据：Bromley Analysing 2021。
6. **原因再打一个认知机制标签：** 知觉（符号、可供性）/ 注意（负荷、分心）/ 记忆（编码、存储、提取）。用作自上而下的编码维度，方便跨系统发现共性病根（比如通知和跨界面目标丢失都属于提取失败）。
   - 怎么核查：每条有且只有一个主机制标签。
   - 依据：Hodent Gamer's Brain Part 2, 2016；Epic 2015 的通知用色例。
7. **严重度用固定问题判定，不按出现次数。** 三问：是否阻断推进或核心体验；是否需要外部帮助或长时间卡住；是否跨 session 复现。可用性问题和主观意见分两条通道评级。
   - 怎么核查：每条严重度都附三问的答案；两条通道分开列。
   - 依据：Bromley Prioritise 2023、Analysing 2021。
8. **用演绎式启发式清单做第二编码维度：** Hodent 7 条可用性加 3 根可投入性支柱；PLAY / GAP（新手与入门）；NGH（多人沟通协作）；F2P FP1–FP6（养成与付费）。每条发现同时标注违反了哪条，并单独产出「符合项」（按意图运作的设计）。
   - 怎么核查：报告里有没有正面发现小节；每条问题是否有启发式编号。
   - 依据：Desurvire & Wixon 2018 ch.14；Hodent 2019；Pinelle 2009；Paavilainen 2018；Bromley Analysing 2021。
9. **分层透视：** 先判断是理解层的问题（不知道是什么、为什么）、可用性层的问题（知道但做不到或做着别扭），还是体验层的问题（做得到但感受不对），再考虑变现层。同一系统里，下层问题先报。
   - 怎么核查：每条有层级字段；同一骨架节点下，按层级从下到上排序。
   - 依据：McAllister & Long 2018 ch.8（摘要）；PocketGamer 2013。
10. **证据三角互证，并标出单一来源的风险。** 每条发现至少有一条行为或画面证据（时间戳 + 截帧）加一条口述证据。只有口述、没有行为证据的，降为「待验证」；玩家给出的原因不能直接写成原因字段。
    - 怎么核查：抽查证据字段的类型分布。
    - 依据：Tan, Leong, Shen 2014；Kulik 2026；Hodent 2015 敌人体型例。
11. **建议可以有，但要和问题分开写，并且用 HMW 的形式。** 默认把方案留给设计师；方案放在单独小节，不混进原因和影响。
    - 怎么核查：问题主体字段里没有「建议」措辞；建议小节用「我们如何…」开头。
    - 依据：Bromley Debrief 2021、Analysing 2021；Desurvire 2017 访谈。
12. **控制总量，并声明适用边界。** 主报告只放团队现在需要的高优先级发现（比如每个骨架节点最多列 3–5 条，其余进附录或洞察库）。报告开头说明这是「N=1 设计师自玩 / 专家评审式」证据，首次体验类结论需要外部玩家复测。
    - 怎么核查：主体条数是否在上限内；开头有没有适用性声明。
    - 依据：Bromley Report 2022、Sharing 2021（前 5 问题邮件、洞察库）；Hodent 知识的诅咒 2018；Laitinen 2006。
    - 注意：「每节点 3–5 条」是我按「稀释影响力」原则给的建议值，**来源没有给出具体数字**。

---

## 8. 未核实 / 缺口清单

- Pinelle 2008 的 10 条启发式、12 类问题，以及 NGH 2009 的 10 条，**原文措辞都没核对**（PDF 失效或在付费墙后），只确认了来源方法和数量。
- OUP 2018 各章（ch.4, 8, 11, 12, 14, 15, 18, 19, 23）**只读到摘要和目录**，正文主张没有核实。
- Gow 等 2010：PDF 只抓到二进制，正文没读。Hertzum 2024 元分析的结论没读到。
- 游戏专项的 think-aloud 反应性实证研究没有找到；CTA 与 RTA 的比较证据来自网站、图书馆目录类的可用性研究。
- 「一份报告典型有多少条问题」没有任何来源给出数字。
- 「设计师最觉得有用的是什么」只找到 GURB 一项设计师侧的研究，其余都是研究员视角。
- 没有找到 MMO Boss 机制沟通的 GUR 一手研究。
- Medlock 等 2002 的 RITE 原文、Pagulayan 等的 "User-centered design in games"、Wired 2007 的 Halo 3 报道都**没读到原文**，只能当作背景。
- Bromley 严重度第 3 问的措辞在不同文章里方向不一致（见 2.2）。

---

## 附：来源总表

| # | 作者 / 年 | 标题（原文） | URL | 标记 |
|---|---|---|---|---|
| 1 | Bromley 2021 | Defining research objectives | https://gamesuserresearch.com/defining-research-objectives/ | 一手·已读 |
| 2 | Bromley 2021 | Designing a games user research study | https://gamesuserresearch.com/designing-a-games-user-research-study/ | 一手·已读 |
| 3 | Bromley 2022 | Find usability issues in games with playtests | https://gamesuserresearch.com/find-usability-issues-in-games-with-playtests/ | 一手·已读 |
| 4 | Bromley 2021 | Analysing a games user research study | https://gamesuserresearch.com/analysing-a-games-user-research-study/ | 一手·已读 |
| 5 | Bromley 2022 | How to write a games user research report | https://gamesuserresearch.com/how-to-write-a-games-user-research-report/ | 一手·已读 |
| 6 | Bromley 2023 | How to prioritise playtest issues and player feedback | https://gamesuserresearch.com/how-to-prioritise-playtest-issues-and-player-feedback/ | 一手·已读 |
| 7 | Bromley 2021 | Debriefing a study | https://gamesuserresearch.com/debriefing-a-study/ | 一手·已读 |
| 8 | Bromley 2021 | Sharing Games User Research Findings | https://gamesuserresearch.com/sharing-games-user-research-findings | 一手·已读 |
| 9 | Bromley 2025 | Stop Being Ignored – Four Steps To Increase Playtest Impact | https://gamesuserresearch.com/stop-being-ignored-four-steps-to-increase-playtest-impact/ | 一手·已读 |
| 10 | Bromley 2020 | Games User Research Methods | https://gamesuserresearch.com/?p=2664 | 一手·已读 |
| 11 | Hodent 2019 | Understanding the Success of Fortnite: A UX & Psychology Perspective | https://celiahodent.com/understanding-the-success-of-fortnite-ux/ | 一手·已读 |
| 12 | Hodent 2016 | The Gamer's Brain, Part 2: UX of Onboarding and Player Engagement (GDC16) | https://celiahodent.com/gamers-brain-ux-onboarding/ | 一手·已读 |
| 13 | Hodent 2015 | Developing UX Practices at Epic Games | https://celiahodent.com/ux-practices-epic-games/ | 一手·已读 |
| 14 | Hodent 2015 | 5 Misconceptions about UX in Video Games | https://celiahodent.com/five-misconceptions-ux/ | 一手·已读 |
| 15 | DigiPen 2018 | Dr. Celia Hodent brings UX insight from Fortnite to DigiPen | https://www.digipen.edu/showcase/news/dr-celia-hodent-brings-ux-insight-from-fortnite-to-digipen/ | 二手·已读 |
| 16 | Plunkett / Taels 2025 | 'Dopamine Simply Doesn't Work Like That': An Interview With A User Experience Researcher | https://aftermath.site/video-games-user-experience-ux-research.md | 二手·已读 |
| 17 | Kulik 2026 | The 4 Ingredients of Effective Games User Research | https://start.playtestcloud.com/blog/the-4-ingredients-of-effective-games-user-research | 一手·已读 |
| 18 | Hugelmann 2020 | Writing A Playtest Report | https://start.playtestcloud.com/blog/writing-a-playtest-report | 一手·已读 |
| 19 | Cleaver / Desurvire 2017 | Deep Dive into Games User Research with Heather Desurvire (Part Two) | https://start.playtestcloud.com/blog/deep-dive-into-games-user-research-with-heather-desurvire-part-two-of-two | 二手·已读 |
| 20 | Moosajee 2016 | GURB: the game user research blueprint (MSc thesis) | https://ontariotechu.scholaris.ca/items/8d57f0d0-8c00-4bde-9d33-67bb215cf0eb/full | 一手·已读（摘要页） |
| 21 | Laitinen 2006 | Do Usability Expert Evaluation and Testing Provide Novel and Useful Data for Game Development? (JUS) | https://uxpajournal.org/wp-content/uploads/sites/7/pdf/JUS_Laitinen_Feb2006.pdf | 一手·已读（摘要页） |
| 22 | Tan, Leong, Shen 2014 | Combining think-aloud and physiological data to understand video game experiences (CHI) | https://opus.lib.uts.edu.au/handle/10453/41566 | 一手·已读（摘要页） |
| 23 | Drachen, Mirza-Babaei, Nacke (eds.) 2018 | Games User Research (OUP)，目录 | https://academic.oup.com/book/26677 | 一手·摘要/目录 |
| 24 | McAllister & Long 2018 | A framework for player research (ch.8) | https://academic.oup.com/book/26677/chapter/195455905 | 一手·摘要/目录 |
| 25 | Sangin 2018 | Observing the player experience (ch.11) | https://academic.oup.com/book/26677/chapter/195456889 | 一手·摘要/目录 |
| 26 | Knoll 2018 | The think-aloud protocol (ch.12) | https://academic.oup.com/book/26677/chapter/195457270 | 一手·摘要/目录 |
| 27 | Desurvire & Wixon 2018 | Heuristics uncovered for Games User Researchers and game designers (ch.14) | https://academic.oup.com/book/26677/chapter/195457780 | 一手·摘要/目录 |
| 28 | Paavilainen et al. 2018 | Heuristic evaluation of playability… free-to-play heuristics (ch.15) | https://academic.oup.com/book/26677/chapter/195458662 | 一手·摘要/目录 |
| 29 | Mirza-Babaei 2018 | Reporting user research findings to the development team (ch.18) | https://academic.oup.com/book/26677/chapter/195460088 | 一手·摘要/目录 |
| 30 | Drachen & Connor 2018 | Game Analytics for Games User Research (ch.19) | https://academic.oup.com/book/26677/chapter/195460224 | 一手·摘要/目录 |
| 31 | Livingston 2018 | Post-launch in Games User Research (ch.4) | https://academic.oup.com/book/26677/chapter/195455393 | 一手·摘要/目录 |
| 32 | Berg 2018 | Dissecting the Dragon: GUR for Dragon Age: Inquisition (ch.23) | https://academic.oup.com/book/26677/chapter/195461114 | 一手·摘要/目录 |
| 33 | Hopson 2015 | User Research on Destiny (GDC) | https://gdcvault.com/play/1022354/User-Research-on | 一手·摘要/目录 |
| 34 | Livingston 2014 | Where are the Sharks? User Research in the Far Cry Production Pipeline (GDC) | https://gdcvault.com/play/1020363/Where-are-the-Sharks-User | 一手·摘要/目录 |
| 35 | McAllister 2014 | Every Game Is A Hit (GDC China) | https://gdcvault.com/play/1021677/Every-Game-Is-A-Hit | 一手·摘要/目录 |
| 36 | Fan Yi & Xingyu Zhang 2024 | Start Right, Start Fun… (GDC, Tencent) | https://gdcvault.com/play/1034684/Start-Right-Start-Fun-Unveiling | 一手·摘要/目录 |
| 37 | Wixon & Pagulayan 2008 | That's Entertainment – Halo 3: the theory and practice of a research-design partnership | https://www.microsoft.com/en-us/research/publication/thats-entertainment-halo-3-the-theory-and-practice-of-a-research-design-partnership/ | 一手·摘要 |
| 38 | Lewis & Sauro 2020 | Ten Things to Know about the RITE Method（转述 Medlock et al. 2002） | https://measuringu.com/rite-method/ | 二手·已读 |
| 39 | Pinelle, Wong, Stach 2008 | Heuristic Evaluation for Games (CHI) | DOI 10.1145/1357054.1357282 | 仅搜索摘要 |
| 40 | Pinelle, Wong, Stach, Gutwin 2009 | Usability Heuristics for Networked Multiplayer Games (GROUP) | https://dl.eusset.eu/handle/20.500.12015/4868 | 仅搜索摘要 |
| 41 | Korhonen & Koivisto 2007 | Playability heuristics for mobile multi-player games (DIMEA) | DOI 10.1145/1306813.1306828 | 仅搜索摘要 |
| 42 | Gow et al. 2010 | Capturing Player Experience with Post-Game Commentaries | https://www-users.york.ac.uk/~pc530/pubs/Gow_cgat2010.pdf | 仅搜索摘要 |
| 43 | van den Haak, de Jong, Schellens（年份未核实） | Retrospective vs. concurrent think-aloud protocols… online library catalogue | https://www.semanticscholar.org/paper/Retrospective-vs.-concurrent-think-aloud-protocols:-Haak-Jong/bf7270b4c89944ab2e58c666d36a6e7815f131ea | 仅搜索摘要（非游戏） |
| 44 | Alhadreti & Mayhew（年份未核实） | Rethinking thinking aloud: A comparison of three think-aloud protocols | https://ueaeprints.uea.ac.uk/id/eprint/65771/ | 仅搜索摘要（非游戏） |
| 45 | Hertzum 2024 | Concurrent or Retrospective Thinking Aloud in Usability Tests: A Meta-Analytic Review (TOCHI) | https://rucforsk.ruc.dk/ws/files/105748016/Concurrent_or_Retrospective_Thinking_Aloud_in_Usability.pdf | 仅元数据，结论未读 |
| 46 | PocketGamer.biz 2013 | The key to F2P success? Know your player, says Player Research | https://www.pocketgamer.biz/the-key-to-f2p-success-know-your-player-says-player-research/ | 仅搜索摘要 |
| 47 | NPR 2007 | Halo 3 测试报道 transcript | https://www.npr.org/transcripts/14649338 | 仅搜索摘要 |
| 48 | Blau (Riot)（年份未核实） | Data Informed Decisions with the Champions of 'League of Legends' (GDC) | https://gdcvault.com/play/1026252/contactUs（GDC Vault 联系页） | 仅搜索摘要 |
| 49 | bugnet.io | What is playtesting | https://bugnet.io/blog/what-is-playtesting | 仅搜索摘要 |
| 50 | GameAnalytics | 行为遥测与体验测量（页面标题未核实） | https://gameanalytics.com/?p=3902 | 仅搜索摘要 |
| 51 | Wikipedia | RITE Method | https://en.wikipedia.org/wiki/RITE_Method | 仅搜索摘要（二手） |
