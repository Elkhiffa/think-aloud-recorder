# 研究 C：专业研究者的质性分析工具 × AI 辅助综合的证据

> 用途：评估「think-aloud 录像（46 场：转写 + 屏幕 OCR + 输入日志）→ 单场 judgment instance → 跨场问题树 / 洞见报告」这条 agent 流程。用户的不满是 agent 组织方式过于自下而上，而专业做法更偏自上而下。
> 检索日期：2026-10-20。检索方式：WebSearch + WebFetch。nngroup.com 有一段时间返回 503，之后恢复，部分页面已读到。
> **标记约定**：`P` = 本次直接打开了原始页面或论文（含仅摘要页）并在原文里读到该说法；`S` = 只来自搜索引擎摘要、第三方转述，或原页打不开（403/404/空）。`厂商自述` = 厂商对自家产品的描述，没有经过独立验证。年份写发布年或最后审阅年；帮助文档没有日期的，写「检索 2026」。引文每个来源最多一句，且不超过 15 词。来源键（如 〔NN-24〕）对应 §6 来源清单。

---

## 0. 结论先行

1. **专业工具把三层分开存放，层级是需要维护的独立对象，不是聚类自然长出来的结果。** 证据单元（highlight / clip / note / finding）→ 编码（tag / label，按 taxonomy 管理）→ 主题 / 洞见（单独写成的文档，引用证据）。层级放在 tag board / tag group / workspace tag / 父子 label 里，由人创建、合并、锁定〔DV-WT〕〔CD-GT〕〔MV-TL〕〔LB-F〕。
2. **专业流程里的「自上而下」是指先搭框架，而不是先定结论。** 动手打标签之前，先固定研究问题、访谈提纲、项目 Goals、设计意图或固定类目：Looppanel 按提纲问题归档笔记〔LP-DG〕，Lookback 的 AI 依据事先定义的 Goals 找时刻〔LB-F〕，PlaytestCloud 先配置「最多 6 个类目 + 研究问题 + 游戏描述」〔PTC-H〕，Dovetail 的 taxonomy 指南明确说从单个研究的数据自下而上搭是最常见的错误〔DV-TAX〕，游戏 UR 把问题定义为「体验偏离了设计意图」〔GUR-B〕。自下而上的输入走另外几条通道：试点标注、受治理的新标签提案、残差补漏。
3. **重复出现仍然重要，但它是框架定下之后的确认，不负责搭框架。** NN/g 用「在多个参与者 / 数据源中反复出现」来界定主题〔NN-TA〕。游戏 UR 则明确说可用性问题的严重度不按频次排〔GUR-B〕。NN/g 2023 发现，工具因为拿不到研究目标等上下文，没法按重要性排序，甚至把琐碎发现排在第一〔NN-23〕。
4. **工具里的 AI 大多是「建议 + 人工接受」，作用在证据层和标签层。** 跨项目「问资料库」本质上是带引用的检索〔DV-AI〕〔LP-AA〕〔GQ〕。自主性最高的功能是 Dovetail Agents（无人值守运行），它的文档里没有写人工复核步骤；AI 聚类则绕开已有 tag，直接按内容生成主题〔DV-AI〕。
5. **NN/g 的立场（2023→2024→2026 一致）**：AI 编码只能算初稿。只看转写不能分析可用性测试。解释必须由人主导〔NN-23〕〔NN-24〕〔NN-V26〕。
6. **学术证据是混合的**：
   - 用定义清楚的 codebook 做演绎编码，在描述性 / 语义层编码上能达到接近人工的一致性〔XIAO23〕〔CHEW23〕〔DUN24〕〔MARS26〕。
   - 解释性 / 潜在主题两头都弱〔MORG23〕〔PRES24〕〔SEYL25〕。
   - 但也有研究发现演绎一致性反而低于归纳〔PRES24〕，所以「演绎一定更好」这个结论不成立。
7. **证据最好的层级构建方法有四个共同点**：每个概念带显式纳入判据〔LLOOM24〕；子主题在父主题下生成〔TGPT24〕；分配必须附引文〔TGPT24〕；对未覆盖样本做残差循环〔LLOOM24〕。另外还要对引文做逐字校验〔DETAILS25〕。
8. **本次没找到的东西**：引文幻觉的量化比率（同行评审）；任何一款工具在「游戏 think-aloud + 屏幕 + 输入日志」上的独立评测；多数工具层级深度上限的官方说明。详见 §5。

---

## 1. 工具与分析数据模型

### 1.1 通用骨架：证据 → 编码 → 主题 / 洞见

- **Atomic research（Pidcock / Sharon）**把链条拆成四步：实验（做了什么）→ 事实（看到什么）→ 洞见（因此想到什么）→ 结论 / 建议。最小单元是带证据的 nugget，一条 nugget 可以支撑多个上层发现〔ATOM, S〕。EnjoyHQ、Glean.ly 等资料库都以此为设计参照〔EQ, S〕。
- **映射到本流程（推断，非来源结论）**：judgment instance ≈ nugget / highlight + code；跨场问题树 ≈ tag board 层级 + 主题；洞见报告 ≈ Insights / Docs。差别在于：专业工具里，层级（taxonomy）是**先于数据、被治理的对象**；如果 agent 是「先逐场抽取，再全量聚类命名」，层级就成了抽取结果的副产品。

### 1.2 逐工具要点

**Dovetail**
- 数据模型：Data（转写 / 文档）→ Highlight（文本片段；音视频片段自动成为 clip）→ Tag（与 highlight 多对多）〔DV-HL, P 检索 2026〕。
- Tag 默认只在项目内有效。Workspace tag board 是跨项目的全局标签，链接到多个项目后实时同步，用于 persona、JTBD、平台流程等标准集。tag 可以归入「tag group」〔DV-WT, P 检索 2026〕。帮助页没说明 group 能不能嵌套。
- 洞见层：原「Insights」已改名「Docs」，可以引用 highlight / tag / note〔DV-DOCS, S〕。
- 官方 taxonomy 指南〔DV-TAX, P 2026-06，厂商指南〕：
  - 层级 2–3 级，顶层 4–8 个大类，起步约 20–40 个标签。
  - 每个标签要有名称、1–2 句定义、一个纳入例、一个排除例。
  - 从组织跨研究要学什么出发；只用单个研究自下而上搭是最常见的错误。
  - 通过多人试点标注同一批数据来校验；新标签由 2–3 人小组审批；每年审计 1–2 次。
- 访谈材料：发现期偏自下而上，评估期偏自上而下或混合；从假设出发建 taxonomy 容易引入确认偏误〔DV-INT, S，原页 404，只读到搜索摘要〕。

**Condens**
- Highlight（来自笔记 / 转写 / 图像 / 音视频，可附摘要）→ Tag → Tag group。Artifact 里会显示每条 highlight 被哪些产出引用了〔CD-TAG, P 检索 2026〕。
- 跨项目：Global Tags 和 Tag Boards（按团队 / 产品 / 研究领域组织，例如 Feature Requests、User Emotions）。管理员可以锁定全局标签，锁定后研究员只能用、不能改。每个项目可单独开关全局标签〔CD-GT, P 检索 2026〕。帮助页没写层级深度。
- AI：划选文本时按所选内容建议标签（键入 1/2/3 选择）〔CD-TAG, P〕；「Find similar Highlights」〔S〕；AI 搜索 / 汇总〔CD-AI, S 营销页〕。

**Marvin（HeyMarvin）**
- 双轨分类：Tag 用来标**文件和 Insights**，Label 用来标**笔记**。两者都用模板管理，可以设为对全部项目可见，或只对指定项目可见〔MV-TL, P 检索 2026〕。
- Label 支持父 / 子层级，AI 建议时会考虑父子关系〔MV-LB, S〕。「Label 最多 5 级」的说法**没核实到**（搜索里出现的 5 级来自 Craft 等其它产品）。
- AI：Ask AI、跨项目分析、Deep Research 都能按标签过滤〔MV-TL, P〕。「自动打标签」只出现在营销博客里〔MV-MKT, S，厂商自述〕。

**Aurelius**：Notes 打 tag → Key Insights（附支撑数据）→ Recommendations（单独的对象，和洞见关联）。AI Assist 从笔记组生成摘要和关键主题，一键存成 Key Insight〔AU, S〕。没找到数据模型的官方说明。

**EnjoyHQ（已并入 UserTesting）**：Tag 做粗分类；Property 是带多个取值的维度（例如 Product Area）。Tag 和 Property 标原始证据，Label 标 Story（nugget）〔EQ, S；官方帮助页 403/404〕。有 G2 评论说新用户觉得 tag / property 的结构难懂〔EQ, S〕。

**Notably**：AI 可以从 tag、主题或整个项目生成 insight，要选匹配的「insight 模板」（如 persona 模板）〔NB, S〕。没找到 tag group 层级的官方说明。

**Looppanel**（在「框架先行」上做得最明确）
- 上传访谈提纲后，AI **逐题**到转写里找答案，把笔记归到各题下，可在 Analysis 页按问题或按主题查看〔LP-DG, P 检索 2026〕。
- 帮助页的提醒：每题是独立读的，问题措辞要具体；上传后再改提纲，旧笔记不会重新归档〔LP-DG〕。
- Auto-Analyze 流程：先填研究背景（目标、竞品、关注点）→ 审阅并编辑 AI 建议的标签表（每个标签要有描述）→ 再批量打标签 → AI 标签带 sparkle 图标 → 建议的洞见附转写引文和视频片段〔LP-AA, P〕。
- 厂商自述：AI 并不完美，建议复核打好标签的数据〔LP-AA〕。自动打标签 2024-10 上线〔LP-REL, S〕。

**Great Question**：Highlight（可打 tag）→ Synthesis 把 highlight 分组为主题。Tag 分两种：跨研究的 Tags 和单研究的 Study Tags。AI 可以按研究目标生成 highlight、建议标签。Ask AI 能检索最多约 50 小时访谈并返回引文。官方称每条引文都链接到转写原位〔GQ, S；帮助页抓取失败〕。资料库级查询有「已上线」和「Coming soon」两种说法，相互矛盾〔GQ, S〕。

**Reframer（Optimal Workshop）**：Session → Observation（单条陈述，可打 tag、标显著性）→ Theme builder 按 tag 组合把观察分组〔RF, S 第三方评测〕。有评论建议事先定好标签集，以免出现重复标签〔RF, S 单条评论〕。AI 功能在另一款产品 Optimal Interviews 里，Reframer 本身是否有 AI**没核实到**。

**UserTesting**：AI Insight Summary（2023 发布，当时是 beta）声称每条洞见都链回源视频；Friction detection 用 ML 从视频中识别过度点击 / 滚动等摩擦〔UT, S 新闻稿，厂商自述〕。没有公开的准确率。

**Lookback**
- Session → Finding（带时间戳的片段，明确说明「不是结论」）→ Theme（跨场归组，finding 保持可追溯）→ Reel。Goals 事先定义（常与干系人共同定），作为 AI（Eureka）的上下文〔LB-F, P 检索 2026〕。
- 引文："AI does not decide what is important."〔LB-F〕
- Eureka 在主持人按键时生成带时间戳的笔记，并按 Goals 跨场浮现 Findings〔LB-E, S〕。

**Miro / FigJam（亲和图白板）**
- Miro AI 的 Cluster 可以按关键词或按情感给便签分簇，簇名可改。另有不用 AI 的按 tag / 颜色 / 作者分簇〔MIRO, S〕。
- FigJam AI 的 Sort stickies 可以按 Topic / 颜色 / 作者 / 印章排序，生成副本后可手动调整。帮助页的定位是这只是大流程中的一步，仍需人工完成〔FJ, S〕。
- 两者都没有 codebook 概念，是纯自下而上的聚类。

**PlaytestCloud（游戏）**
- 输入：玩家 think-aloud 转写 + 问卷 + **分析配置**（从 13 个类目中选最多 6 个、游戏描述、研究问题）+ 游戏名。
- 两段式：先逐玩家对照配置找趋势，再综合成 First Findings 报告。
- 输出：逐视频的 AI 标注（作者标为 AI，可过滤）、逐场摘要、报告〔PTC-H, P 检索 2026〕。
- 限制：纯问卷研究或没录音（即没有 think-aloud）时不可用。重新生成会覆盖旧的 AI 标注。帮助页承认输出有不确定性和随机性〔PTC-H〕。
- First Findings（2025-07）列出五个主题：Usability / Game Design / Enjoyment / Monetization / Frustration，每个主题链接到各玩家的片段，定位为「初步分析」〔PTC-FF, P〕。
- 厂商博客：AI 标注关键时刻、做初步跨场主题，人负责解释「为什么」和给建议〔PTC-B1, P 2025-12，厂商自述〕。博客里「AI 从未幻觉」一类说法属于厂商自述，没有独立验证。
- 研究总监 Bui-Xuan 列出的局限：玩家会叫错功能名（比如把合成菜单叫成「商店」）、反讽、缺乏品类经验〔PTC-B2, P 2025-08〕。

**Antidote（Sekg）**：采集问卷、游玩、面部录像、think-aloud、触控 / 手柄输入、游戏事件，宣传有 AI 洞见、情感检测、自动报告〔ANT, S 目录页〕。**数据模型没核实到。**

**PlayerXP**：不是 playtest 工具，而是商店评论 / 社区反馈的 AI 聚合分析平台〔PXP, S〕。**超出本题范围**，只在表里列出。

**内部 GUR 工具**：微软游戏工作室的 TRUE（Kim et al., CHI 2008）把行为埋点、态度问卷和视频关联起来〔TRUE, S 只有书目信息，正文没读到〕。Fan et al. 用转写的言语和语音特征自动检测 think-aloud 中的可用性问题；VisTA 研究里有 30 名 UX 专业人员参与〔FAN, S〕。没找到 Ubisoft / EA / Riot 等内部工具的公开文档。

### 1.3 对比表

| 工具 | 证据 → 编码 → 主题 / 洞见 | 层级支持 | 跨项目 | AI 功能 | 已记录局限 / 厂商自述的警告 | 来源 |
|---|---|---|---|---|---|---|
| Dovetail | Data → Highlight/clip → Tag（多对多）→ Docs（原 Insights） | Tag group（嵌套没写明）；官方指南建议 2–3 级 | Workspace tag board 链接多个项目、实时同步 | AI 建议 highlight（复用已有 tag，接受时显示理由）、AI 聚类（按内容，不看 tag）、Chat（声称可溯源）、Docs 生成、Channels、Agents | 聚类英语效果最好；部分功能限 Enterprise；不能按 workspace 关闭 AI；Agents 无需人工值守 | DV-HL/WT/AI P 2026；DV-TAX P 2026 |
| Condens | Highlight（可附摘要）→ Tag → Tag group；Artifact 记录引用 | Tag group + Tag Board；深度没写 | Global Tags（可锁定、按项目开关） | 按所选文本建议标签；找相似 highlight；AI 搜索 | 建议质量取决于所选文本；没有准确率数据 | CD-TAG/GT P；CD-AI S |
| Marvin | 文件 / Insight ← Tag；笔记 ← Label | Label 有父 / 子；深度没核实 | 模板可设为全局或指定项目 | Ask AI、跨项目分析、Deep Research（都可按标签过滤） | 自动打标签只见于营销页 | MV-TL P；MV-LB/MKT S |
| Aurelius | Note → Tag → Key Insight → Recommendation | 没写明 | 没写明 | AI Assist 从笔记组生成摘要 / 主题 | 没公开数据模型 | AU S |
| EnjoyHQ | 证据 ← Tag + Property（多值维度）；Story ← Label | Property 是维度而不是树 | 资料库级 | 没核实到 | 结构对新手不友好（评论） | EQ S |
| Notably | 证据 → Tag → AI insight（套模板） | 没核实到 | 没核实到 | 从 tag / 主题 / 项目生成 insight | 要选对模板 | NB S |
| Looppanel | 转写 → 自动笔记（按提纲问题归档）→ Tag → Insight（附引文） | 按问题 / 按主题两种视图 | 项目内 | 先给背景再审阅标签表，然后自动打标签；建议洞见附引文 | AI 不完美，要复核；改提纲后旧笔记不重新归档 | LP-DG/AA P |
| Great Question | Highlight → Tag → Synthesis 主题 | 全局 Tags vs Study Tags | 有（资料库级查询状态有冲突） | 按研究目标生成 highlight、建议标签、Ask AI | 帮助页没抓到 | GQ S |
| Reframer | Observation（tag + 显著性）→ Theme builder | 平铺标签组合 | 项目内 | Reframer 本身没核实到 | 标签会重复 | RF S |
| UserTesting | 视频 → AI Insight Summary / 摩擦点 | — | — | 洞见摘要、摩擦检测 | 没有准确率；2023 时为 beta | UT S |
| Lookback | Session → Finding（片段）→ Theme → Reel；Goals 先定 | Theme 一层 | 项目内 | Eureka 按 Goals 浮现 Findings | AI 不决定什么重要 | LB-F P；LB-E S |
| Miro / FigJam | 便签 → AI 分簇 / 排序 → 人工命名 | 无 codebook | — | 按关键词 / 情感 / 主题分簇 | 只是流程中的一步 | MIRO/FJ S |
| PlaytestCloud | 视频转写 → AI 标注 → 逐场摘要 → First Findings（固定类目主题） | 类目 → 洞见 → 片段 | 单次 playtest | 配置驱动（≤6 类目 + 研究问题 + 游戏描述） | 只用转写和问卷；没录音时不可用；有随机性；会叫错名 / 读不懂反讽 | PTC-H/FF/B2 P |
| Antidote | 多模态采集 → AI 洞见 / 报告 | 没核实到 | — | 情感 / 情绪检测、自动结论 | 没有独立信息 | ANT S |
| PlayerXP | 商店评论 / 社区 → AI 归类 | — | — | 评论聚类与趋势 | 不在本题范围 | PXP S |
| TRUE（微软内部） | 行为埋点 + 态度 + 视频关联 | — | — | （2008，非 LLM） | 正文没读到 | TRUE S |

### 1.4 「自上而下」在工具里具体落在哪

| 机制 | 例子 | 对应本流程的做法 |
|---|---|---|
| 研究问题 / 提纲先行，按问题归档证据 | Looppanel 提纲〔LP-DG〕、NN/g 主题分析第 3 步把 RQ 一直放在视野内〔NN-TA〕 | 每条 judgment 挂到某个 RQ / 意图 ID 上 |
| 事先定义的目标作为 AI 的上下文 | Lookback Goals〔LB-F〕、Looppanel 研究背景〔LP-AA〕、PlaytestCloud 研究问题 + 游戏描述〔PTC-H〕 | 把设计意图 / 体验目标写进每轮 prompt |
| 固定顶层类目 | PlaytestCloud 13 选 6〔PTC-H〕、Dovetail 4–8 个大类〔DV-TAX〕 | 问题树顶层先定死 |
| 受治理的全局标签 | Dovetail workspace tags〔DV-WT〕、Condens 锁定 Global Tags〔CD-GT〕 | codebook 跨场共享、改动要审批 |
| 先审阅标签表，再批量打标签 | Looppanel Auto-Analyze〔LP-AA〕 | 每轮跑之前人确认 codebook |
| 自下而上的入口 | 试点 + 治理提案〔DV-TAX〕；发现期偏自下而上〔DV-INT, S〕 | 残差补漏 → 候选新 code → 人工审批 |

---

## 2. 工具里的 AI 功能与有记录的局限

### 2.1 厂商自述的警告

- **Dovetail**〔DV-AI, P〕：
  - 合成文档的定位是承担初稿的重活，人来精修和验证。
  - AI 生成的内容带特定图标，人编辑过的加头像，以区分来源。
  - 聚类按 highlight 内容而不是 tag 生成主题，英语效果最好；Chat 的质量取决于给的上下文。
  - 不能按 workspace 关闭 AI；Agents 可以按计划持续运行，无需人工值守。
  - 引文："Themes are created from the content of your highlights, not the tags or titles."——这说明它的 AI 聚类是**绕过已有 taxonomy 的纯自下而上**做法。
- **Looppanel**：建议复核 AI 标签；标签质量取决于背景信息和标签描述〔LP-AA, P〕。
- **PlaytestCloud**：承认输出有不确定性和随机性；如果结果缺上下文，建议补充游戏描述或研究问题后重新生成〔PTC-H, P〕。
- **Lookback**：AI 只减少需要看的视频量，不判断什么重要〔LB-F, P〕。
- **FigJam**：AI 排序和汇总只是流程中的一步〔FJ, S〕。

### 2.2 NN/g 的评估

- **Liu & Moran, 2023**〔NN-23, P；页面已标注被 2024 新文取代〕：
  - 评测了一个 insight 生成器和一个 AI 协作工具，用 NN/g 自己的可用性研究录像，与人工分析对比。
  - 工具只接受转写，不能输入研究目标、过往发现、任务，所以**没法按重要性排序**，曾把「参与者乐意给反馈」这种琐碎发现排在第一。
  - 没有一个工具能处理视频或画面。建议笼统、无法执行。
  - 引用常常不标场次 / 时间戳；协作工具分不清研究员笔记和参与者原话。
  - 引文："no human or AI tool can analyze usability-testing sessions by the transcript alone"（13 词）。
- **Moran & Rosala, 2024（2026-01 复审）**〔NN-24, P〕：
  - AI 适合做的分析环节：转写、翻译、摘要、清洗数据、**第一遍编码和聚类**。
  - 必须由人主导的：结合上下文解释（包括主题分析）、检查有无诱导、判断参与者是否合适、说明发现的含义和局限。
  - 列出的风险：聚类分组薄弱、大量「Other」、漏码或码不贴合；随机性导致关注错数据、漏读、误读甚至编造洞见。
  - 引文："Treat AI's coding as an initial pass."
- **Rosala, 2026-04 视频**〔NN-V26, P 仅页面摘要〕：AI 可以当分析时的思考伙伴，但不应主导。视频里的「四种负责任用法」没有文字稿，**没核实**。
- **Rosenfeld Advancing Research 2026 演讲摘要**〔RF-26, S，原页 403〕：NN/g 持续测试 LLM 综合工具，结论是少数工具能给资深研究员带来小幅提速，但都远不能替代人工；会编造发现、抓不住有意义的模式、处理不了细腻的研究问题、只给出浅层摘要。讲者身份和日期没核实。
- **Rosala, 2022（2026-09 复审）**〔NN-TA, P〕：主题分析六步，研究问题全程放在视野内。主题指在参与者或数据源中反复出现的信念 / 做法 / 需求。亲和图快、便宜，但不够彻底（片段很少被多次编码）。

### 2.3 按用户列出的失效模式整理

| 失效模式 | 证据 | 强度 |
|---|---|---|
| 编造引文 / 洞见 | NN/g 2024 列为风险〔NN-24, P〕；LLooM 自承没有校验引文准确性的步骤〔LLOOM24, P〕；有关「引文全部被编造」的说法存在争议〔ARX-QUOTE, S〕 | **没找到同行评审的量化比率** |
| 主题浅、泛 | NN/g 2023 建议笼统〔NN-23, P〕；Morgan 认为 ChatGPT 擅长描述性主题、不擅长解释性主题〔MORG23, S〕；LLM 产出的主题更少、更宽〔JELD26, P〕；LLooM 把匹配超过 50% 数据的概念视为过泛〔LLOOM24, P〕 | 中–强 |
| 过度碎片化 / 弱聚类 | NN/g 2024：分组薄弱、大量 Other〔NN-24, P〕 | 中（还有与之相反的「过宽」证据，见上一行） |
| 缺上下文和「为什么」 | NN/g 2023 无法输入研究目标〔NN-23〕；PlaytestCloud 提到叫错名、反讽、缺品类经验〔PTC-B2〕；只用转写，看不到行为〔NN-23〕〔PTC-H〕 | 强 |
| 频次 ≠ 重要性 | 没有上下文就没法按重要性排〔NN-23〕；游戏 UR 的严重度决策树不使用频次〔GUR-B, P〕 | 中（主要是从业者文献） |
| 丢失反例 / codebook 外的内容 | LLM 漏掉间接表达和类目外的需求〔MARS26, P〕；LLooM 专门为未覆盖样本设了循环〔LLOOM24〕 | 中；**没找到专门研究「反证 / 否定案例」的论文** |
| 研究员笔记与参与者原话混在一起 | 〔NN-23, P〕 | 单一来源 |
| 速度与信任之间的差距 | Condens 调查 332 人：91% 在用 AI，但信任跟不上速度，动手做分析最多的人感受最明显〔CD-SURV, S 厂商调查〕 | 弱–中 |

---

## 3. 学术证据：LLM 辅助质性分析

### 3.1 演绎编码（codebook 驱动）

- **Xiao et al., IUI'23 Companion**〔XIAO23, P 摘要〕：GPT-3 + 专家写的 codebook，不做微调；与专家编码的一致性为 fair 到 substantial。
- **Chew et al., 2023（LACA）**〔CHEW23, P 摘要〕：GPT-3.5 在多个公开数据集的演绎编码上常能达到与人工相当的一致性；该框架还能识别出模型其实在随机猜的那些 code。
- **Dunivin, 2024**〔DUN24, P 摘要〕：GPT-4 在 9 个 code 中有 3 个 κ≥0.79、8 个 κ≥0.6，GPT-3.5 平均 κ 只有 0.34；**让模型写出编码理由后，保真度明显提高**。后续期刊版把它定位为混合流程：人建 codebook，再对照人工金标准校验〔DUN25, S〕。
- **Marston et al., 2026**〔MARS26, P 摘要〕：46 个 LLM、150 份人道主义访谈（合成数据）。多个模型在结构化 codebook + 推理模式下能达到资深编码员的水平。
  - 但总体一致性指标对部署决策来说不够，要逐主题评估。
  - 模型容易漏掉间接表达的需求、类目外的需求、安全 / 歧视类关切。
  - 建议分层人审：后果越重的类目，人审越多。
- **JMIR Formative, 2026**〔JMIR26, S，全文抓取失败〕：GPT-4o 用人工 codebook 做演绎编码，一致率 96%、κ≈0.71；归纳生成的 code 与人工吻合度低得多。
- **反例：Prescott et al., JMIR AI 2024**〔PRES24, S〕：归纳主题与人工一致 71.4%，演绎反而更低（ChatGPT 50%，Bard 58.3%）。人更擅长细腻、解释性的主题。数据只有 40 条短信，规模很小。

### 3.2 归纳主题生成

- **De Paoli, SSCR 2024**〔DEPA24, S〕：GPT-3.5 做归纳主题分析，在**电子游戏玩家访谈**和讲师访谈两个公开数据集上，复现了原研究的大部分主要主题。
- **Dai et al., EMNLP Findings 2023**〔DAI23, P 摘要〕：用 in-context learning 与 LLM 协作生成 codebook，两组问卷数据上编码质量接近人工，省时省力。
- **Morgan, IJQM 2023**〔MORG23, S〕：擅长具体、描述性的主题，不擅长微妙、解释性的主题，分析者自己要熟悉数据。
- **Seyler 2025 系统综述（海报）**〔SEYL25, S〕：纳入 23 项研究。语义主题上表现中到高，解释性 / 依赖上下文的主题较弱，目前没有标准化流程。
- **Jeldtoft & Yousef, 2026**〔JELD26, P 摘要〕：可审计的工作流。设计原则包括保持源材料与产出之间的可追溯链接、显式写出分析理由、LLM 只用于解释性任务、流程由确定性程序控制。code 层覆盖接近人工，但**主题更少、更宽**。

### 3.3 层级主题构建 / 概念归纳（与「自上而下」最相关）

- **LLooM（Lam et al., CHI 2024）**〔LLOOM24, P〕：
  - 流程：Distill（抽原文引文 → 要点）→ Cluster（HDBSCAN，不强制每个点都入簇）→ Synthesize（产出概念名 + **自然语言纳入判据** + 代表样例）→ Score（用判据给每条数据打分）→ Loop（把未被覆盖、或只被过泛概念覆盖的样本送进下一轮）。
  - 可选的 **Seed** 词用来自上而下引导。概念「越往上越一般」，并保留可追溯的子概念。
  - 结果：比 BERTopic 多出约 2 倍高质量主题，覆盖率约 93% 对 77.7%。
  - 作者承认的局限：没有引文 / 打分正确性校验；重跑结果会变；场景研究只用了约 200 条样本。
- **TopicGPT（Pham et al., NAACL 2024）**〔TGPT24, P〕：
  - 生成阶段用少量人写的种子主题（标签 + 一句描述）作示范。
  - 分层扩展：以精炼后的顶层主题为父节点，给模型「父主题 + 示例子主题 + 已分到该父主题的文档」，生成子主题并引用支撑文档。
  - 分配时必须给出文档内的支撑引文；解析器发现无效或幻觉的分配会打回重分。
  - 与人工标注的 Wikipedia 主题相比，harmonic purity 0.74，最强基线为 0.64。
- **Thematic-LM（Qiao et al., WWW 2025）**〔TLM25, S〕：多 agent 分工（编码、聚合 code、维护 codebook），coder 可以带不同身份视角。是否有 reviewer agent **没核实**。
- **DeTAILS（Sharma et al., 2025 预印本）**〔DETAILS25, P〕：
  - 六阶段：背景研究（研究问题 + 文献 → 概念大纲）→ 载入 → 编码（LLM 先起草 codebook → 人编辑 → 全量应用，**引文不逐字匹配就丢弃**）→ 审 code 簇 → 生成主题 → 报告。
  - 每个阶段都有人工检查点；18 名研究者参与评估。
  - 设计建议：后面阶段的修改能回传到前面；显示不确定性；标注人 / AI 来源；用提示问题支撑反思。

### 3.4 人机协作流程与研究者态度

- **CollabCoder（Gao et al., CHI 2024）**〔COLLAB24, S〕：三阶段：独立开放编码（LLM 按需建议，记录关键词和确定度）→ 依据分歧指标讨论 → 系统提议 code 分组，形成 codebook。
- **CoAIcoder（Gao et al., TOCHI 2024）**〔COAI24, S〕：共享 AI 能提高早期效率和一致性，**但可能降低最终 code 的多样性**。这说明由 AI 起草的 codebook 有锚定风险。
- **Jiang et al., CSCW 2021**〔JIANG21, S 摘要〕：研究者愿意接受归纳分析的模糊性，但要求对过程完全掌控。设计上应保护意外发现、人的主导权和模糊性。
- **Schroeder et al., 2024/25**〔SCHR24, P 摘要〕：访谈 20 名质性研究者，认为严重缺少规范和工具；LLM 无处不在，会削弱刻意、审慎的使用。
- **Kirsten et al., NordiCHI'26**〔KIRS25, P 摘要〕：访谈 15 名 HCI 研究者，担心隐私、自主权和输出质量；按「从极少到高度」的 AI 参与程度建了分级框架。
- **方法论争议**：Jowsey、Braun、Clarke 等 2025 年发表立场文章，拒绝在**反身性**主题分析中使用生成式 AI，400 余人联署〔JOWS25, S〕；Friese 等人回应主张有批判地整合〔FRIESE, S〕。本流程属于应用型的设计评估、带 codebook，方法上更接近 codebook / framework 式分析，而不是反身性 TA（这是推断，不是来源结论）。

### 3.5 综合解读：什么有效、什么失败

**有效**（多源支持）：
- 有定义、有纳入 / 排除例的 codebook 用于演绎编码，尤其是描述性 code〔XIAO23〕〔CHEW23〕〔DUN24〕〔MARS26〕。
- 让模型写编码理由〔DUN24〕。
- 显式纳入判据 + 用判据回打全量〔LLOOM24〕。
- 子主题在父主题下生成并引证〔TGPT24〕。
- 逐字校验引文〔DETAILS25〕〔TGPT24〕。
- 残差循环〔LLOOM24〕。
- 逐主题评估、分层人审〔MARS26〕。
- 每个阶段设人工检查点〔DETAILS25〕。

**失败或存疑**：
- 解释性 / 潜在主题〔MORG23〕〔PRES24〕〔SEYL25〕。
- codebook 外的内容和间接表达〔MARS26〕。
- 主题过泛或过碎〔JELD26〕〔NN-24〕〔LLOOM24〕。
- 重跑结果不稳定〔LLOOM24〕〔PTC-H〕。
- AI 建议导致 code 多样性下降〔COAI24〕。
- 只有转写、看不到行为〔NN-23〕。
- 演绎是否一定优于归纳：证据冲突〔PRES24〕vs〔JMIR26〕。

---

## 4. 可信来源推荐的人机分工

| 环节 | AI 可以做 | 人必须拍板 | 来源 |
|---|---|---|---|
| 框架：研究问题 / 设计意图 / 顶层类目 | 起草候选（有锚定风险） | 确认框架和顶层类目 | NN-TA P；LB-F P；DV-TAX P；MSD P；COAI24 S |
| codebook | 从样本起草、提议合并 | 定义、纳入 / 排除例、审批新增 | DV-TAX P；DETAILS25 P；DUN25 S |
| 逐条编码 | 第一遍演绎编码 + 理由 | 抽检；高后果类目全检 | NN-24 P；MARS26 P；DUN24 P |
| 聚类 / 主题 | 提议簇和候选主题 | 命名解释性主题、合并或拆分 | NN-24 P；LLOOM24 P；DETAILS25 P |
| 优先级 | 统计频次 | 严重度、对设计意图的影响、取舍 | GUR-B P；NN-23 P |
| 报告 | 初稿、按受众改写、检索资料库并给引文 | 说明含义、局限、要不要追加研究 | NN-24 P；PTC-B1 P |
| 流程设计 | — | 方法、prompt、流水线顺序、对输出做系统评估 | MSD P（Anthropic 的 Hawkins 访谈，2026） |

---

## 5. 没能核实 / 有争议的内容

- Marvin「项目分组 2 级 / Label 5 级」：只在搜索摘要里出现，二次检索把「5 级」指向了 Craft 等其它产品。可以确认的只有：Label 有父 / 子关系。
- Dovetail「Insights 改名 Docs」「tag summary 已弃用」：只有搜索摘要。Sareff-Hibbert、McCurrie 访谈原页 404，「发现期自下而上、评估期自上而下」只来自搜索摘要。
- NN/g「四种负责任用法」：视频页能打开，但四种做法本身没核实到。Rosenfeld 演讲摘要原页 403，讲者身份不确定。
- 「Jowsey 发现引文全部被编造」：只在一篇持反对意见的 arXiv 评论里出现〔ARX-QUOTE〕，属于有争议的转述。Jowsey 等人的立场文章本身是方法论上的反对，不是对编造率的测量。
- PlaytestCloud 博客说「AI 从未幻觉」：厂商自述。
- Antidote 数据模型、Great Question 帮助页、EnjoyHQ 官方帮助、Reframer 有无 AI、UserTesting 准确率：都没核实到原始文档。
- JMIR Formative 2026（96% / κ 0.71）和 Prescott 2024 的数字：全文没读到，来自搜索摘要。
- Thematic-LM 是否有 reviewer agent：没核实。
- 范围比较（PMC13270661）：原页被浏览器验证拦住，只有搜索摘要。
- **完全没找到的**：
  - 同行评审的引文幻觉率。
  - 专门研究 LLM 处理反例 / 否定案例的论文。
  - 任何 AI 工具在「think-aloud + 屏幕 OCR + 输入日志」三模态上的评测。
  - Ubisoft / EA / Riot 等内部 GUR 工具的公开文档。

---

## 6. 来源清单

### 工具文档 / 厂商材料

| 键 | 标题（原文） | URL | 类型 / 年 |
|---|---|---|---|
| DV-HL | Dovetail Help: Highlights | https://docs.dovetail.com/help/projects/highlights | P，检索 2026 |
| DV-WT | Dovetail Help: Workspace tags | https://docs.dovetail.com/help/projects/workspace-tags.md | P，检索 2026 |
| DV-AI | Dovetail Help: Dovetail AI overview | https://docs.dovetail.com/help/dovetail-ai/overview.md | P，检索 2026 |
| DV-TAX | How to build a tagging taxonomy for qualitative research that scales across teams | https://dovetail.com/research/how-to-build-tagging-taxonomy-qualitative-research/ | P（厂商指南），2026-06 |
| DV-DOCS | Dovetail Help: Docs | https://docs.dovetail.com/help/docs | S |
| DV-INT | Talking tagging taxonomies (Bec Sareff-Hibbert) / Tagging taxonomies (Caitlin McCurrie) / Laura Mata | https://dovetail.com/blog/talking-tagging-taxonomies-bec-sareff-hibbert/ ; https://dovetail.com/blog/tagging-taxonomies-caitlin-mccurrie/ ; https://dovetail.com/blog/talking-tagging-taxonomies-with-laura-mata | S（404，只有搜索摘要），年份未知 |
| CD-TAG | Condens Help: Structuring data with tags | https://condens.io/help/using-condens/structuring-and-analyzing/structuring-data-with-tags | P，检索 2026 |
| CD-GT | Condens Help: Connecting data across projects with global tags | https://condens.io/help/using-condens/research-repository-functionality/connecting-data-across-projects-with-global-tags | P，检索 2026 |
| CD-AI | Condens AI: Purpose-built for UX Research | https://condens.io/ai | S（营销页） |
| CD-SURV | AI in User Research Analysis (332 respondents) | https://condens.io/blog/ai-in-user-research-analysis-report | S（厂商调查），检索 2026 |
| MV-TL | Marvin Help: The difference between tags and labels | https://help.heymarvin.com/en/articles/10261004-the-difference-between-tags-and-labels | P，检索 2026 |
| MV-LB | Marvin Help: Add and manage labels in a project | https://help.heymarvin.com/en/articles/15083563-add-and-manage-labels-in-a-project | S |
| MV-MKT | Marvin: Content tagging | https://heymarvin.com/resources/content-tagging | S（营销） |
| AU | Aurelius features / help center | https://www.aureliuslab.com/features ; https://intercom.help/aurelius/en | S |
| EQ | Key concepts in EnjoyHQ (UserTesting Help) | https://help.usertesting.com/hc/articles/11880326255645-Key-concepts-in-EnjoyHQ | S（403） |
| NB | Notably Help: How to generate an AI insight | https://help.notably.ai/en/articles/6977525-how-to-generate-an-ai-insight | S |
| LP-AA | Looppanel Help: How to auto analyze on Looppanel | https://help.looppanel.com/en/articles/11009985-how-to-auto-analyze-on-looppanel | P，检索 2026 |
| LP-DG | Looppanel Help: How to add a discussion guide to a project | https://help.looppanel.com/en/articles/8146331-how-to-add-a-discussion-guide-to-a-project-on-looppanel | P，检索 2026 |
| LP-REL | Looppanel release notes: Auto-tagging launch | https://www.looppanel.com/release-notes/auto-tagging-launch | S，2024-10 |
| GQ | Great Question Support: Great Question AI | https://greatquestion.co/support/repository/great-question-ai | S（抓取失败） |
| RF | Reframer Review: A Qualitative Research Tool (PINT) | https://blog.pint.com/reframer-review/ | S（第三方） |
| UT | UserTesting press releases (2023); Friction detection (CMSWire) | https://www.businesswire.com/news/home/20230829003257/en ; https://www.businesswire.com/news/home/20230412005272/en ; https://www.cmswire.com/the-wire/usertesting-launches-new-behavioral-analytics-capabilityfriction-detection-powered-by-machine-learning/ | S，2023 |
| LB-F | Lookback Help: From sessions to findings | https://help.lookback.io/en/articles/13429122-from-sessions-to-findings | P，检索 2026 |
| LB-E | Lookback Help: Eureka | https://help.lookback.io/en/articles/13455441-eureka | S |
| MIRO | Miro Help: Miro AI cluster | https://help.miro.com/hc/articles/28781881506834 | S |
| FJ | Figma Help: Sort and summarize stickies with FigJam AI | https://help.figma.com/hc/en-us/articles/18711926790423 | S |
| PTC-H | PlaytestCloud Help: Understanding AI-powered analysis | https://help.playtestcloud.com/en/articles/7941599-understanding-ai-powered-analysis | P，检索 2026 |
| PTC-FF | Meet First Findings | https://start.playtestcloud.com/product-updates/meet-first-findings-a-completely-revamped-ai-analysis-experience-across-your-entire-playtest | P，2025-07 |
| PTC-B1 | Supercharging game research with human-in-the-loop AI analysis (J. Kulik) | https://start.playtestcloud.com/blog/supercharging-game-research-with-human-in-the-loop-ai-analysis | P（厂商博客），2025-12 |
| PTC-B2 | AI and Games Research: benefits, limitations and what comes next (U. Bui-Xuan) | https://start.playtestcloud.com/blog/ai-and-games-research-benefits-limitations-and-what-comes-next | P（厂商博客），2025-08 |
| ANT | Sekg / Antidote | https://sekg.net/ ; https://startupshub.catalonia.com/startup/barcelona/antidote/1192 | S |
| PXP | How Player XP's AI is helping devs find the reviews that matter (MCV) | https://www.mcvuk.com/development-news/how-player-xps-artificial-intelligence-is-helping-devs-find-the-reviews-that-matter/ | S |
| TRUE | Kim et al., Tracking real-time user experience (TRUE), CHI 2008 | https://doi.org/10.1145/1357054.1357126 | S（只有书目），2008 |
| GUR-B | S. Bromley, How to prioritise playtest issues and player feedback | https://gamesuserresearch.com/how-to-prioritise-playtest-issues-and-player-feedback/ | P（从业者），2023 |
| FAN | Fan et al., Automatic Detection of Usability Problem Encounters in Think-aloud Sessions (TOCHI 2020); VisTA (TVCG 2019); CoUX (VIS 2021) | https://doi.org/10.1145/3385732 ; https://virtual.ieeevis.org/year/2021/paper_v-full-1209.html | S，2019–2021 |
| ATOM | Atomic research explained (Maze); Atomic research nuggets (UX Studio) | https://maze.co/collections/user-research/atomic-research/ ; https://uxstudioteam.com/ux-blog/?p=14272 | S |

### NN/g 与从业者

| 键 | 标题 | URL | 类型 / 年 |
|---|---|---|---|
| NN-23 | AI-Powered Tools for UX Research: Issues and Limitations (Liu & Moran) | https://www.nngroup.com/articles/ai-powered-tools-limitations/ | P，2023-07（已被 NN-24 取代） |
| NN-24 | Accelerating Research with AI (Moran & Rosala) | https://www.nngroup.com/articles/research-with-ai/ | P，2024-09，2026-01 复审 |
| NN-TA | Analyze Qualitative Data: Thematic Analysis (Rosala) | https://www.nngroup.com/articles/thematic-analysis/ | P，2022，2026-09 复审 |
| NN-V26 | Use AI Responsibly in Analysis (video, Rosala) | https://www.nngroup.com/videos/use-ai-responsibly-in-analysis/ | P（只有页面摘要），2026-04 |
| NN-HL | Why Human-Led Research Still Matters in the Age of AI | https://www.nngroup.com/articles/human-led-research-still-matters/ | S（503，只有搜索摘要） |
| RF-26 | Human vs. machine: Testing AI's ability to synthesize and analyze research (Advancing Research 2026) | https://rosenfeldmedia.com/advancing-research/?p=1154 | S（403） |
| MSD | AI-accelerated research: speed and scale without compromising rigor (Think First, Savina Hawkins) | https://microsoft.design/articles/ai-accelerated-research-speed-and-scale-without-compromising-rigor/ | P，2026-02 |

### 学术

| 键 | 标题 | URL | 类型 / 年 |
|---|---|---|---|
| XIAO23 | Supporting Qualitative Analysis with Large Language Models: Combining Codebook with GPT-3 for Deductive Coding (IUI'23 Companion) | https://arxiv.org/abs/2304.10548 | P 摘要，2023 |
| CHEW23 | LLM-Assisted Content Analysis: Using Large Language Models to Support Deductive Coding | https://arxiv.org/abs/2306.14924 | P 摘要，2023 |
| DAI23 | LLM-in-the-loop: Leveraging Large Language Model for Thematic Analysis (Findings of EMNLP) | https://arxiv.org/abs/2310.15100 | P 摘要，2023 |
| DUN24 | Scalable Qualitative Coding with LLMs: Chain-of-Thought Reasoning Matches Human Performance in Some Hermeneutic Tasks | https://arxiv.org/abs/2401.15170 | P 摘要，2024 |
| DUN25 | Scaling hermeneutics: a guide to qualitative coding with LLMs for reflexive content analysis | https://epjdatascience.springeropen.com/articles/10.1140/epjds/s13688-025-00548-8 | S（抓取失败），2025 |
| PRES24 | Comparing the Efficacy and Efficiency of Human and Generative AI: Qualitative Thematic Analyses (JMIR AI) | https://ai.jmir.org/2024/1/e54482 | S，2024 |
| MORG23 | Exploring the Use of Artificial Intelligence for Qualitative Data Analysis: The Case of ChatGPT (IJQM) | https://journals.sagepub.com/doi/10.1177/16094069231211248 | S，2023 |
| DEPA24 | Performing an Inductive Thematic Analysis of Semi-Structured Interviews With a Large Language Model (SSCR) | https://rke.abertay.ac.uk/ws/files/81658175/DePaoli_PerformingAnInductiveThematicAnalysis_Published_2024.pdf | S，2024 |
| JMIR26 | GPT-4o deductive/inductive coding of focus-group data (JMIR Formative Research) | https://formative.jmir.org/2026/1/e85572 | S（全文为空），2026 |
| MARS26 | Can Large Language Models Reliably Code Qualitative Humanitarian Data? A Benchmark Study Against Human Expert Adjudication | https://arxiv.org/abs/2606.26541 | P 摘要，2026 |
| JELD26 | Designing an Auditable LLM-Supported Workflow for Qualitative Thematic Analysis | https://arxiv.org/abs/2608.30543 | P 摘要，2026 |
| LLOOM24 | Concept Induction: Analyzing Unstructured Text with High-Level Concepts Using LLooM (CHI 2024) | https://arxiv.org/html/2404.12259v1 | P，2024 |
| TGPT24 | TopicGPT: A Prompt-based Topic Modeling Framework (NAACL 2024) | https://arxiv.org/html/2311.01449v2 | P，2024 |
| TLM25 | Thematic-LM: A LLM-based Multi-agent System for Large-scale Thematic Analysis (WWW 2025) | https://doi.org/10.1145/3696410.3714595 | S，2025 |
| DETAILS25 | DeTAILS: Deep Thematic Analysis with Iterative LLM Support | https://arxiv.org/html/2510.17575 | P（预印本），2025 |
| COLLAB24 | CollabCoder: A Lower-barrier, Rigorous Workflow for Inductive Collaborative Qualitative Analysis with LLMs (CHI 2024) | https://arxiv.org/abs/2304.07366 | S，2024 |
| COAI24 | CoAIcoder: Examining the Effectiveness of AI-assisted Human-to-Human Collaboration in Qualitative Analysis (TOCHI) | https://doi.org/10.1145/3617362 | S，2024 |
| JIANG21 | Supporting Serendipity: Opportunities and Challenges for Human-AI Collaboration in Qualitative Analysis (CSCW) | https://arxiv.org/abs/2102.03702 | S 摘要，2021 |
| SCHR24 | Large Language Models in Qualitative Research: Uses, Tensions, and Intentions | https://arxiv.org/abs/2410.07362 | P 摘要，2024/2025 |
| KIRS25 | From Assistance to Autonomy: A Researcher Study on the Potential of AI Support for Qualitative Data Analysis (NordiCHI'26) | https://arxiv.org/abs/2501.19275 | P 摘要，2025/2026 |
| SEYL25 | Evaluating the Validity and Reliability of LLMs for Qualitative Data Analysis: A Systematic Review (poster) | https://www.researchgate.net/publication/391735643_Evaluating_the_Validity_and_Reliability_of_Large_Language_Models_for_Qualitative_Data_Analysis_A_Systematic_Review | S，2025 |
| SCOPE | The use and methodological reporting of LLMs in qualitative research: a scoping review | https://pmc.ncbi.nlm.nih.gov/articles/PMC13270661/ | S（被浏览器验证拦截） |
| JOWS25 | We reject the use of generative artificial intelligence for reflexive qualitative research (Qualitative Inquiry) | https://papers.ssrn.com/abstract=5676462 | S，2025 |
| FRIESE | Beyond Binary Positions: Making Space for Critical and Reflexive GenAI Integration in Qualitative Research | https://papers.ssrn.com/abstract=5962174 | S，2025 |
| ARX-QUOTE | Can machines perform a qualitative data analysis? Reading the debate with Alan Turing | https://arxiv.org/abs/2512.04121 | S，2025 |

---

## 7. 对 agent 流程的启示

每条都写了「怎么检查」。

1. **框架锚定**：每轮分析的输入头部固定写入「研究问题 + 设计意图 / 体验目标」清单（带 ID）。每条 judgment instance 必须挂一个 RQ / 意图 ID，挂不上的显式标 `off-frame`。
   - 检查：随机抽 20 条，ID 字段 100% 非空；`off-frame` 的比例单独报告。
   - 依据：〔NN-TA〕〔LP-DG〕〔LB-F〕〔PTC-H〕〔GUR-B〕。
2. **问题树的骨架先于数据**：顶层 4–8 类，最多 2–3 层，起步 20–40 个叶子 code。顶层由人确认后，在 46 场里保持不变。
   - 检查：codebook 文件的层级深度 ≤3；顶层类目在多次运行之间完全一致。
   - 依据：〔DV-TAX〕〔PTC-H〕。
3. **codebook 每条四个字段齐全**：名称、1–2 句定义、纳入例、排除例。
   - 检查：用脚本校验字段完整率 100%。
   - 依据：〔DV-TAX〕〔XIAO23〕〔CHEW23〕〔MARS26〕。
4. **两遍式：先演绎，再残差补漏**。第一遍按 codebook 编码。第二遍只处理没被任何 code 覆盖、或只被过泛 code 覆盖的片段，产出「候选新 code」，人审批后才能进 codebook。
   - 检查：报告里有残差片段数、候选 code 数、通过 / 驳回记录。
   - 依据：〔LLOOM24〕〔MARS26〕〔NN-24〕〔DV-TAX〕。
5. **子节点在父节点下生成，不做全量自由聚类后再起名**。给模型「父主题 + 已分到这里的证据」去生成子主题，每个子主题都要引证。
   - 检查：问题树每个非根节点有 `parent_id`，且至少有 N 条证据引用（N 预先定好）。
   - 依据：〔TGPT24〕〔LLOOM24〕。
6. **每个主题 / 概念带纳入判据，并能用判据回打全量**。用判据对 46 场重新打分；匹配超过 50% 场次的概念视为过泛，必须拆分。
   - 检查：每个主题有 `criteria` 字段；有回打覆盖率表。
   - 依据：〔LLOOM24〕。
7. **每条编码 / 判断附理由（rationale）**。
   - 检查：字段非空率 100%；人工抽检时理由能指向具体证据。
   - 依据：〔DUN24〕〔JELD26〕〔DV-HL〕（Dovetail 的 AI highlight 接受时会显示生成理由）。
8. **引文逐字校验，并带场次和时间戳**。每条 quote 都要在源转写或 OCR 里字符串命中（只做空白规范化），命不中就丢弃或标红。
   - 检查：自动脚本的命中率 = 100%，或者未命中条目列表为空。
   - 依据：〔DETAILS25〕〔TGPT24〕〔NN-23〕〔LLOOM24 自承缺这一步〕。
9. **频次和严重度分两列，默认按严重度排序**。严重度按「偏离设计意图」的决策树判定：是不是核心体验？是否难以克服？是否持续？频次只作为确认依据。
   - 检查：问题树节点同时有 `session_count` 和 `severity` 两个字段；报告写明排序规则。
   - 依据：〔GUR-B〕〔NN-23〕〔NN-TA〕。
10. **行为证据优先于口述**。可用性类判断必须引用屏幕 OCR 或输入日志中的证据；只凭口述得出的结论标为低置信。
    - 检查：可用性类节点里，带非转写证据的比例单独报告。
    - 依据：〔NN-23〕〔PTC-H〕〔TRUE, S〕〔FAN, S〕。
11. **逐主题评估 + 分层人审，解释和排序归人**。按主题报告人机一致性，不只报总体数字。高后果类目和解释性主题由人全检，描述性主题抽检。主题命名、优先级、「所以呢」由设计师拍板，AI 输出一律标「初稿」。
    - 检查：有逐主题的一致性表；人审记录里有覆盖范围说明。
    - 依据：〔MARS26〕〔NN-24〕〔NN-V26〕〔PRES24〕〔JIANG21〕。
12. **来源标识 + codebook 版本化**。每个对象标明是 AI 还是人生成或修改的。codebook 改版后，要么对已处理的场次重跑，要么在旧产出上标出所用的版本号，不允许静默混用。
    - 检查：对象上有 `author: ai|human` 和 `codebook_version` 字段；改版日志与重跑记录能对上。
    - 依据：〔DV-AI〕〔LP-AA〕〔PTC-H〕〔LP-DG〕〔DETAILS25〕。

> 风险提示：由 AI 起草的顶层框架或 codebook 可能锚定、压缩多样性〔COAI24〕，自上而下也可能放大确认偏误〔DV-INT, S〕。所以第 2 条的「人确认」和第 4 条的残差通道是一对，不能只做其中一个。
