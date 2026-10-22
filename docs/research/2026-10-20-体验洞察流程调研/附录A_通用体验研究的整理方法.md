# 研究 A：专业 UX 研究者如何把出声思维 / 可用性录像综合成设计洞察报告

> 用途：作为评估 Think Aloud agent 流程（46 场、约 40 小时、同一位游戏设计师的自玩出声思维 → 跨会话洞察报告）的外部参照。用户的抱怨是「agent 的组织太 bottom-up，专业研究者会更 top-down 地组织和聚合问题」。
> 检索日期：2026-10-20。检索方式：WebSearch + WebFetch。

## 标注规则

| 标签 | 含义 |
|---|---|
| **[主]** | 原作者本人的文字，本次读到了正文（含作者本人网站、NN/g 署名文章、署名从业者的自述方法） |
| **[主·摘要]** | 原始出处，但只读到摘要、目录或作者页的简介，没读到正文 |
| **[次]** | 第三方转述、二手综述、厂商博客对他人方法的总结、搜索结果片段 |
| **[推论]** | 本文作者根据上述来源推出来的，来源本身没有直接这么说 |
| **未核实** | 没能拿到可信文本，只能列出来提醒 |

- NN/g 页面多数带有「last reviewed 2026」字样。文中年份一律写**原始发布年**，复审日期不单独标。
- 引文每个来源最多一处，均不超过 15 个英文词。其余都是意译。
- Medium（Tomer Sharon、Daniel Pidcock 的原文）、PMC / Springer（Thomas & Harden 全文）、UWE 仓库（Braun & Clarke 论文 PDF）本次均返回 403 / 断连，相关结论都降级标注。

---

## 0. 结论先行

1. **专业的综合流程是双向的，不是纯 bottom-up。** 先定框架（研究问题、假设、任务 / 旅程 / 模块），证据自下而上填进去，最后再按框架收口成少数几条有观点的主题。证据见 1.3 节的对照表：Rosala 2022、Gale et al. 2013、Sharon 2013、Torres 2023、Bromley 2022、Dmitrieva（Bentley）。
2. **bottom-up 本身并没有错，它有明确的用处（Chesterton's Fence）。** 亲和图和反身性主题分析之所以刻意不预设类目，是为了防止研究者只看见自己预期的东西。NN/g 的亲和图文章（Krause & Pernice 2024）[主] 要求聚类从便签内容里长出来、不要硬凑。Rosala 2022 [主] 把「忽视不符合研究者信念的观点」列为一种偏差。所以要做的是「给 bottom-up 加一层框架，再加一道收口」，不是把 bottom-up 换掉。
3. **「太 bottom-up」在文献里对应几个能叫得出名字的毛病：**
   - 主题其实是「话题桶」（topic summary），比如「X 的障碍」「Y 的体验」，而不是带中心观点的主题。来源：Braun & Clarke FAQ [主]。
   - 按功能分组，而不是按洞察分组。Jess Tompkins 的建议，见 Bromley 2022 [主]。
   - 把发现平铺列出、没有主线，难以记住。Bromley 2022 [主]。
   - 拿便签数量当重要性。GOV.UK, Fu 2019 [主]。
4. **n=1、而且受试者就是设计师本人，是本语料最大的方法学限制。** 单一评估者给出的严重度不可靠（Nielsen 1994 [主]），不同评估者之间的问题重叠率中位数只有约 27%（Sauro 2018 [主]）。设计师在自己的作品上还容易犯错误共识效应（Budiu 2017 [主]）。另外，**46 场里反复出现，衡量的是同一个人身上的 persistence（持续性），不是跨用户的 frequency（普遍程度）**[推论，依据 Nielsen 1994 的三因素框架]。

---

## 1. 端到端综合流程

### 1.1 通用层级：data → findings → insights → recommendations

| 层级 | 定义（意译） | 出处 |
|---|---|---|
| Data | 未经分析的用户观察 | NN/g, Sara Paul, *Data vs. Findings vs. Insights*（视频页，2023）https://www.nngroup.com/videos/data-findings-insights/ [主·摘要：只读到页面摘要] |
| Findings | 多个数据点之间浮现的模式 | 同上 |
| Insights | 结合研究证据与业务目标、可以行动的机会 | 同上 |
| Findings 与 Insights 的区别 | finding 是「观察到了什么」，insight 是研究者对观察的解释；insight 必须能回溯到具体 finding；"Ideally, findings will outnumber your insights."；如果 insight 比 finding 还多，说明分析下得过早 | Michael A. Morgan（Bloomberg），*Data Analysis: Making Sense of Tally Sheets*，UXmatters，2019-12-16，http://www.uxmatters.com/mt/archives/2019/12/data-analysis-making-sense-of-tally-sheets.php [主] |
| Insight 公式 | What happened + Why + So what；另有 hindsight / foresight 两层 | Vitaly Friedman, *Data Vs. Findings Vs. Insights In UX*, Smashing Magazine, 2025-05-27, https://smashingmagazine.com/2025/05/data-vs-findings-vs-insights-ux/ [主：作者自己的框架] |

> 矛盾提示：Friedman 文中的示例把 6 人样本的发现写成「60% of users struggled」。这正是 NN/g 的 Moran 2021 和 Budiu 2020 明确反对的写法（见 3.3 节）。他的公式可以引用，示例写法不要照抄。

Morgan 2019 [主] 给出的一条完整流程如下：

1. 把讨论指南上的标注汇总到 tally sheet。
2. 把 finding 和解释分开记。
3. 编码。可以用预设的 selective code，也可以用开放编码。
4. 做恒定比较（constant comparative analysis，扎根理论里的核心手法）。
5. 识别主题，包括「没有发生的事」。样本小，所以频次只作粗略参考；对每个主题都要问它对产品成败有多重要。
6. 从分组后的 finding 推出 insight，并且能逐条回溯。

这基本就是 UX 行业里的「轻量扎根理论」做法。

### 1.2 主要方法逐一说明

**(a) 亲和图（Affinity diagramming / KJ 法）**

- NN/g 的步骤 [主]：每人独立写便签（5–10 分钟），然后聚类，最后对每个聚类排优先级并写下一步。
  - 聚类按内容涌现，不预设数量；小聚类不能因为小就忽略。
  - 一张便签同时属于两类时就复制一份，不要强行二选一。
  - 排序用讨论或点投票，并给每个聚类指定负责人。
  - 文章强调讨论过程比最终产物更重要，没有规定报告格式。
  - 来源：Rachel Krause & Kara Pernice, *Affinity Diagramming*, NN/g, 2024-04-26, https://www.nngroup.com/articles/affinity-diagram/
- Contextual Design 版（Holtzblatt & Beyer）[次：IxDF 和 Wikipedia 的转述，没有读原书]：
  - 黄色便签记单条观察。蓝色标签概括一组黄签，粉色标签概括一组蓝签，绿色标签是顶层关注领域，**最多三层**。
  - 除顶层以外，各层标签都用第一人称、用户口吻来写；顶层可以用抽象的话题词。
  - 原书建议用一两次集中会话做完，不要分很多次拼小图。
  - 来源：IxDF, *How to create affinity diagrams*（2025）https://ixdf.org/literature/article/how-to-create-affinity-diagrams ；https://en.wikipedia.org/wiki/Contextual_design
  - 课程讲义（UMass, LSU）[次]把亲和图明确称为「bottom-up 方法，组别不预定义」：https://groups.cs.umass.edu/nmahyar/wp-content/uploads/sites/8/2019/02/690A-07-affinity-diagrams.pdf
- Lucero，*Using Affinity Diagrams to Evaluate Interactive Prototypes*（2015）[主·摘要：只核实了标题和章节结构]：
  - 章节依次是建便签、聚类、Walking the Wall、文档化，讨论部分谈 ROI、便签数量、遗留便签。
  - PDF 没能解析出正文，发表会议未核实。
  - https://users.aalto.fi/~luceroa1/publications/2015/lucero15_affinity.pdf

**(b) 主题分析（Thematic Analysis）**

- NN/g 版 [主]，Maria Rosala, *How to Analyze Qualitative Data from UX Research: Thematic Analysis*, 2022-08-17, https://www.nngroup.com/articles/thematic-analysis/
  - 六步：收集全部数据（最好是转写稿）→ 通读 → 描述性编码 → 生成解释性编码、找关系 → 隔一天再回头看 → 检验主题是否被数据支持、是否反复出现、他人独立分析是否同意。
  - **建议编码时把研究问题一直放在眼前**，随时问新出现的编码和研究问题是什么关系。
  - 列出的陷阱有：只描述、不分析（把参与者说了什么罗列出来）；只盯住印象深刻的引语；忽视矛盾；没有目标时分析会漂移。
- Braun & Clarke 反身性主题分析（reflexive TA）[主：作者官方站 thematicanalysis.net]
  - 六阶段（https://www.thematicanalysis.net/doing-reflexive-ta/ ）：熟悉数据 → 编码 → 生成初始主题 → 发展并复核主题 → 精炼、定义、命名主题 → 写作。各阶段之间是递归的。
  - 主题的定义是「由一个中心概念支撑的共享意义模式」。
  - FAQ（https://www.thematicanalysis.net/faqs/ ）里的要点：
    - **话题摘要不等于主题。** topic summary 只是共享一个话题，没有共享的意义。像「Y 的体验」「X 的好处」这样的名字，是话题摘要式命名的典型例子。
    - 主题分析分三类：coding reliability、codebook、reflexive。codebook 型会早早建好编码本并拿它去套数据；反身性主题分析不用编码本。主题分析既可以归纳（inductive），也可以演绎（deductive），也可以两者都用，但**声称用了哪种，就必须真的那样做**。
    - **不建议用数字或百分比报告主题。** FAQ 引用 Pyett 的话："counting responses misses the point of qualitative research"。原因是各次访谈内容不同，某人的数据里没有某个主题，并不代表此人不同意。
    - 5 场访谈对主题分析「可能偏少」，建议小项目 6–10 场。主题分析回答的是跨数据集的模式问题，按个案来用属于偏离常规的用法，需要专门论证。
  - 原始论文：Braun & Clarke (2006). Using thematic analysis in psychology. *Qualitative Research in Psychology* 3(2) [未在本次抓取]。Braun & Clarke (2021). One size fits all? What counts as quality practice in (reflexive) thematic analysis? *QRP* [次：只看到书目记录]。

**(c) 框架分析（Framework Method）** [主]

来源：Gale, Heath, Cameron, Rashid & Redwood (2013). Using the framework method for the analysis of qualitative data in multi-disciplinary health research. *BMC Med Res Methodol* 13:117。读的是 PMC 全文：https://pmc.ncbi.nlm.nih.gov/articles/PMC3848812/

- 七阶段：转写 → 熟悉 → 编码 → 建立工作分析框架（分类码，**每个类目都留一个「其他」码**）→ 套用框架（indexing）→ 制表（charting）→ 解释。
- **矩阵结构**：行是个案，列是编码，单元格里放摘要和引语出处。这样既能跨个案比较，也能在单个个案内部比较。
- 方法本身不绑定归纳或演绎。演绎型研究用研究问题、文献或理论预设编码；很多研究两者结合，**已知问题用 a priori 码，同时给涌现码留位置**。
- 适用条件：数据话题同质、需要按主题加按个案分析、团队里有非质性背景的成员、数据量大。不适用的情况：数据高度异质。
- 警告：表格的外观容易诱使人去计数，但质性研究的抽样是立意抽样，计数没有意义。

**(d) 跨研究综合：主题综合（Thematic Synthesis）** [主·摘要]

来源：Thomas & Harden (2008). Methods for the thematic synthesis of qualitative research in systematic reviews. *BMC Med Res Methodol* 8:45。只读到摘要和题录：https://discovery-pp.ucl.ac.uk/id/eprint/10005258 ；https://doaj.org/article/17ab902869544887910382732247cf68

- 三步：逐行编码 → 描述性主题（贴近原始研究）→ 分析性主题（超出原始研究，产生新的解释或假设）。
- 分析性主题是不是「用综述问题去拷问描述性主题」生成的？笔者记忆中是这样，但**没能读到全文核实**。

**(e) 原子化研究（Atomic Research）与 nugget**

- Tomer Sharon 版：nugget 是「有证据支撑、带标签的观察」，由观察、证据、标签三部分组成，在 WeWork 的 Polaris 中实现。
  - 出处 [次]：Zack Naylor, Aurelius, 2018, https://blog.aureliuslab.com/2018/07/31/ux-research-nuggets-like-polaris-from-tomer-sharon-and-wework/ ；User Interviews *UX Research Field Guide*（2019 版内容，2025 更新）https://www.userinterviews.com/ux-research-field-guide-chapter/atomic-research-nuggets
  - Sharon 的原文 *The atomic unit of a research insight*（Medium, 2016-04-08）和 *Democratizing UX*（Medium, 2017-01-12）本次返回 403，只从搜索结果确认了标题和日期：https://tsharon.medium.com/the-atomic-unit-of-a-research-insight-7bf13ec8fabe
- Daniel Pidcock 版：Experiments → Facts → Insights → Recommendations/Conclusions 四层。
  - fact 只记录单次经历中用户做了什么、说了什么，不带解释（"Facts make no assumptions"，转引）。insight 是对一个或多个 fact 的解释。fact 与 insight、insight 与 recommendation 都是多对多关系。
  - 出处 [次]：上面的 User Interviews 指南。原文 *What is Atomic Research?*（https://blog.prototypr.io/what-is-atomic-research-e5d9fbc1285c ）本次断连。
- 主要批评 [次，同一出处]：
  - 拆成原子后**丢失上下文**：研究类型、原始数据、局限都没了。Pidcock 的回应是，丢不丢上下文取决于怎么用。
  - 打标签成本高。
  - Sharon 本人认为，原子化研究在大型、分布式、多渠道的组织里最划算。

**(f) Rainbow Spreadsheet（彩虹表）** [主]

- 来源：Tomer Sharon, *The Rainbow Spreadsheet: A Collaborative Lean UX Research Tool*, Smashing Magazine, 2013-04-11, https://www.smashingmagazine.com/2013/04/rainbow-spreadsheet-collaborative-ux-research-tool/
- 工作表包括 Summary、Participants（含录像链接）、Observations、Metrics、Raw。
  - **Observations 表的行是预先定好的行为**，每位参与者占一列并有固定颜色，观察到就给对应格子涂色。同一行为再次出现时，在已有行里涂色，不新建行。
  - 团队在每场之间做 debrief，删掉重复项和「非直接观察」（结论、推断、解决方案），这些等研究结束后再讨论。
  - 研究结束后填写 Summary 表：研究问题、答案、行动项、主要发现。文中说约 10 条行动项就是好结果。
  - 这张表本身就是报告；遇到需要正式文档的高层，就只发 Summary 表。
- GOV.UK 变体 [主]：Crispin Fu, *How a spreadsheet can make usability analysis faster and easier*, GOV.UK User Research blog, 2019-09-13, https://userresearch.blog.gov.uk/2019/09/13/how-a-spreadsheet-can-make-usability-analysis-faster-and-easier/
  - 行是按旅程逐步列出的、可以用是 / 否判断的「假设」，列是参与者，用绿 / 红标记。
  - **作者提醒：亲和图可能仅仅因为很多人记了同一件事，就让某个问题显得重要，而不是因为它在用户旅程中真的重要。**
  - 这种表适合原型和上线旅程的可用性测试，不适合访谈或情境研究。

**(g) 严重度评级（Severity）** [主]

- 来源：Jakob Nielsen, *Severity Ratings for Usability Problems*, NN/g, 1994-11-01, https://www.nngroup.com/articles/how-to-rate-the-severity-of-usability-problems/
  - 严重度由三个因素组成：**frequency**（常见程度）、**impact**（克服难度）、**persistence**（一次性问题，还是会反复困扰同一个用户），另外还要考虑 market impact。
  - 等级 0–4：0 = 不是问题，1 = 外观问题，2 = 次要问题，3 = 主要问题，4 = 灾难性问题。
  - **单个评估者的严重度评级不可靠，取 3 位评估者的平均值在多数实际场合已经足够。**
  - 应在测试会话结束后评级，并让每位评估者给完整问题清单独立打分，包括他们自己没发现的问题。
- Jeff Sauro, *Rating the Severity of Usability Problems*, MeasuringU, 2013-07-30, https://measuringu.com/rating-severity/
  - 文中对比了 Nielsen、Rubin、Dumas & Redish（多了全局 / 局部这一维）、Molich & Jeffries 等几种量表 [次：对他人量表的转述]。
  - MeasuringU 自己的做法 [主]：
    - 三级严重度，另加一个「洞察 / 建议 / 正面」类别。
    - **频次与严重度分开报告**。最好由不知道频次的另一位分析者来评严重度。
    - 用「用户 × 问题」矩阵展示频次。
    - 低频问题不能因为频次低就忽略。

**(h) 设计综合理论：Kolko** [主：作者本人网站上的全文]

- 来源：Jon Kolko (2010). Abductive Thinking and Sensemaking: The Drivers of Design Synthesis. *Design Issues* 26(1):15–28. https://www.jonkolko.com/writingAbductiveThinking.php
- 设计综合是一种溯因式的意义建构（sensemaking），包含三个核心动作：
  - **prioritizing**：按一致的尺度排出重要性。
  - **judging**：判断哪些与问题相关。
  - **forging connections**：建立数据点之间的关系，并给出一个说得通的解释。
- 具体方法有三种：reframing（换视角重构问题）、concept mapping（概念图）、insight combination（把洞察与已有设计模式组合）。
- 主张把数据外化到墙上，让团队能看到全貌、反复重组和改标签，这样意义建构才能共享、才能被质疑。

**(i) 两份「配方」：Top-down 与 Bottom-up** [主：从业者自述]

- 来源：Lena Dmitrieva（Bentley University UX Center），*Formative UX Study Data Analysis: 2 Simple Recipes*（无日期），https://www.bentley.edu/centers/user-experience-center/formative-ux-study-data-analysis-2-simple-recipes
- **Bottom-up**：逐个参与者读笔记，把发现连同参与者编号写进报告模板，同时附上带时间戳的引语，并用高亮标出已经用过的笔记。最后精简措辞、删掉参与者编号，再写执行摘要。
- **Top-down**：团队先把印象写成假设性发现，按从大结论到细节的顺序放进报告框架，再逐条拿笔记核对、给每条补上参与者编号。**最后没有任何参与者编号支撑的条目一律删除**，因为它们只是没被数据证实的回忆。
- 适用场景：Top-down 适合多名分析者分工；Bottom-up 适合单人分析，或者很难先形成假设的时候。

### 1.3 专业者如何把 bottom-up 聚类和 top-down 结构结合起来

**各来源用什么做顶层框架：**

| 来源 | Top-down 框架是什么 | Bottom-up 部分是什么 | 标签 |
|---|---|---|---|
| Rosala 2022（NN/g） | 研究问题全程可见 | 描述性编码 → 解释性编码 | [主] |
| Gale et al. 2013 | 来自研究问题的 a priori 编码，每类都有「其他」码 | 开放编码，迭代到不再出现新码 | [主] |
| Sharon 2013 彩虹表 | 预先定好的行为行；Summary 表按研究问题作答 | Raw 表兜底，debrief 时补新行 | [主] |
| GOV.UK, Fu 2019 | 按任务、旅程逐步列出的假设 | 偏离假设的地方写成便签再聚类 | [主] |
| Torres 2023 OST | 先画体验地图（experience map），**把旅程中的时刻作为顶层 opportunity** | 访谈中的具体 opportunity 挂到对应时刻下，形成父子关系；**顶层随时间趋于稳定，细节在下面长**；每 3–4 次访谈更新一次 | [主] |
| Bromley 2022（游戏 UR） | 按游戏机制、问题类型或研究目标分组；**按洞察类别分组，而不是按功能分组**；以最重要的论点开头 | 每条问题写清原因和影响 | [主] |
| Dmitrieva（Bentley） | 先写假设性结论 | 逐条拿证据核对，删掉没有支撑的 | [主] |
| Thomas & Harden 2008 | 分析性主题（解释层） | 逐行编码 → 描述性主题 | [主·摘要] |
| Contextual Design | 顶层用抽象话题标签 | 黄签逐级向上概括，最多三层 | [次] |
| Condens（厂商） | **标签类别取自利益相关者常问的问题和组织 / 产品结构**（旅程步骤、产品区域等） | 项目标签用来发现新主题，复现之后才升为全局标签 | [主：厂商自述] https://condens.io/taxonomy_uw |

**三种组合机制，各自在什么场景明显占优**（综合上表）[推论]：

| 机制 | 做法 | 明显占优的场景 | 风险 |
|---|---|---|---|
| A. 框架先行（演绎为主，留「其他」桶） | 研究问题、模块、旅程先定成一级目录，证据往里填 | 评估型可用性测试，任务和假设已知；读者按模块或职责来找内容（Gale、Sharon、Fu、Bromley） | 漏掉框架外的新现象，确认偏差 |
| B. 先归纳、再按问题重组（两段式） | 先 bottom-up 得出描述性主题，再用研究问题或设计目标去拷问，产出分析性主题 | 探索型研究，事先不知道会冒出什么（Thomas & Harden、Kolko 的 reframing） | 第二段常被省掉，最后只剩话题桶 |
| C. 假设先行、证据验真 | 先写结论草稿，再逐条拿会话证据核对，没有支撑的删掉 | 团队对产品已有强先验，需要快速出报告（Bentley top-down 配方） | 先验太强会挤掉意外发现 |

**怎么选：** 本项目的语料是开放式自玩，不是任务化测试，读者又是按系统 / 模块分工的专业设计师。比较合理的是 **B 为主、用 A 的框架做收口**：自下而上的描述层保留，在报告层强制按预先声明的框架重组，并保留一个「框架外的新发现」栏 [推论]。

---

## 2. 什么样才算好的 insight

1. **层级要分清。** data、finding、insight、recommendation 是四个不同的东西。insight 必须能回溯到 finding，finding 的数量应该多于 insight（Morgan 2019 [主]；Paul 2023 [主·摘要]）。
2. **主题要有观点，不能只是话题。** 好的主题围绕一个中心组织概念（central organising concept）。像「X 的障碍」「Y 的体验」这种名字只是话题摘要，说明分析停在了描述层（Braun & Clarke FAQ [主]）。NN/g 也把「只描述、不分析」列为常见陷阱（Rosala 2022 [主]）。
3. **游戏 UR 的 finding 写法**（Bromley 2022 [主]，https://gamesuserresearch.com/how-to-write-a-games-user-research-report/ ）：
   - 写清问题是什么、原因（让团队知道该在哪里动手）、对玩家的影响（帮团队排优先级）。
   - 常用格式是对照「预期体验 vs 玩家实际体验」。
   - 关于玩家本身的更深层发现，可以用别的形式来表达。
4. **公式化写法**：What happened + Why + So what（Friedman 2025 [主]）。Miro 的厂商指南把输出写成「insight + implication」成对出现，并主张用统一模板方便跨研究比较（https://miro.com/research-and-design/user-insights/ ）[次：只读到搜索摘要]。
5. **建议本身的质量普遍不高。** Molich, Jeffries & Dumas (2007), *Making Usability Recommendations Useful and Usable*, *Journal of Usability Studies* 2(4):162–179 [次：只读到搜索摘要；URL 未定位，uxpajournal / uxpa.org 上的链接均返回 404]：
   - 17 个专业团队针对 6 个问题写了 84 条评论，只有 14 条（17%）既有用又可用。
   - 常见缺陷是含糊、不可执行、对整体可用性没有帮助。
   - 作者建议：在概念层面把建议说清楚，确认它能改善整体，并给出具体例子。
6. **从 insight 走到设计问题。** How Might We 问题必须能追溯到具体的发现或 insight；不要把方案写进问题里，不要只针对症状，不要过宽也不要过窄（Rosala, *Using "How Might We" Questions to Ideate on the Right Problems*, NN/g, 2021-01-17, https://www.nngroup.com/articles/how-might-we-questions/ [主]）。
7. **Opportunity 的写法。** opportunity 是从客户视角出发的未满足需求、痛点或渴望，不是功能。检验方法是：至少要有两种以上的解法；如果只想得到一种，说明写的其实是方案（Torres, *Opportunity Solution Trees*, Product Talk, 2023-12-06, https://www.producttalk.org/opportunity-solution-tree/ [主]）。
8. **JTBD**：Christensen, Hall, Dillon & Duncan, *Know Your Customers' "Jobs to Be Done"*, HBR, 2016-09。核心观点是「客户雇用产品来完成某个 job」[次：只看到再版片段和书目，未读全文；URL 未定位]。

---

## 3. 报告结构与交付

### 3.1 一份专业报告里有什么

- **游戏 UR 报告结构**（Bromley 2022 [主]）：
  1. 一页摘要：同时写给设计 / 程序和制作人。要说明最重要的发现、最需要关注的区域、游戏的整体状态，标准是能在一次电梯时间里讲完。
  2. 背景：为什么做这次研究，为什么是现在。
  3. 分组的问题：按机制、问题类型或研究目标分组，让各团队直接看自己相关的部分。
  4. 每条问题的完整解释：描述 + 原因 + 影响。
  5. 建议（可选）。
  6. 下一步：工作坊、后续研究、修复后复测。
  7. 附录：复杂图表和原始数据。
- **排序**：线性游戏按玩家遇到的先后排，否则按严重度排；组内的排序也二选一；**整体以最重要的洞察开头，开头可以是一个论点，而不是某个细小的 UX 问题**（Tompkins）。
- **少而强**：资深研究者的功夫在于挑出团队现在必须知道的那几条；只罗列发现的报告容易被忘掉。
- 另外几条写作建议（Laure Duchamp）：每一部分末尾小结；用图、GIF、视频片段维持注意力；报告要能脱离作者独立阅读。
- **彩虹表就是报告**（Sharon 2013 [主]）：Summary 表 = 研究问题 + 答案 + 行动项（约 10 条）。
- **Bentley 报告模板**（Dmitrieva [主]）：方法、执行摘要、详细发现；正面和负面发现都要写；引语带时间戳和参与者编号。
- **常见的报告缺陷**（CUE-2：9 个团队评测 Hotmail；Molich, Ede, Kaasgaard & Karyukin 2004）[次：只读到搜索片段，转引自另一篇论文；URL 未定位]：篇幅过长、没有执行摘要、问题没有严重度分级、问题描述含糊。
- **标准**：ISO 25062:2025（Common Industry Format）规定可用性评估报告的格式，报告应包含哪些内容取决于用了哪类评估方法（https://www.iso.org/standard/84255.html ）[主·摘要：只看到 ISO 摘要页，条目清单未见]。

### 3.2 Opportunity Solution Tree 作为交付结构

Torres 2023 [主]：

- 树的层级是 outcome → opportunity → solution → assumption test。outcome 最好是一个产品层面的结果，也就是客户行为或感受，而不是业务指标。
- opportunity 空间由故事型访谈得出：先画体验地图，再以「时刻」作为顶层，往下逐支细化。
- 一次只选一个目标 opportunity，并至少比较三个解法。

对设计师读者来说，它把「问题清单」变成了「目标 → 机会 → 解法」的树，本身就是一种 top-down 的交付结构 [推论]。

### 3.3 证据和频次怎么呈现（小样本）

| 主张 | 出处 |
|---|---|
| 质性研究里可以采集指标，但只能当轶事来报，不做统计。"report individual values, not aggregated statistics"；写成「6 人中 1 人」，不要换算成百分比 | Kate Moran, *Collecting Metrics During Qualitative Studies*, NN/g, 2021-06-13, https://www.nngroup.com/articles/metrics-qualitative/ [主] |
| 小样本不能推断出「约 80% 的用户会这样」 | Raluca Budiu, *Don't Report Numbers from Small UX Studies*（视频页），NN/g, 2020-01-31, https://www.nngroup.com/videos/numbers-small-ux-studies/ [主·摘要] |
| 不用数字或百分比报主题；某人的数据里没有某个主题 ≠ 此人不同意 | Braun & Clarke FAQ [主] |
| 立意抽样下计数没有意义；矩阵式的表格容易诱人去计数 | Gale et al. 2013 [主] |
| 频次只作粗略参考；要追问每个主题对产品成败的重要性 | Morgan 2019 [主] |
| 亲和图会因「很多人记了」而放大某个问题的重要性 | Fu 2019（GOV.UK）[主] |
| 频次 = 遇到问题的人数 ÷ 总人数，和严重度分开报；用「用户 × 问题」矩阵；低频问题不能忽略 | Sauro 2013 [主] |
| 证据形式：带时间戳和参与者编号的引语（Bentley）；图、GIF、视频片段（Bromley / Duchamp）；nugget 可以串成「playlist」用来讲一个观点（Sharon 在 Portigal 播客中的说法 [次：搜索摘要]，https://portigal.com/podcast/17-tomer-sharon-of-goldman-sachs/ ） | 见各行所列 |

---

## 4. 单人研究 / 自我研究 / 自我民族志的局限

### 4.1 单一评估者

- 启发式评估中，单个评估者平均只能发现约 **35%** 的可用性问题（Nielsen 6 个项目的平均值）。Nielsen 建议用 3–5 人，至少 3 人（Nielsen, *How to Conduct a Heuristic Evaluation / Theory*, NN/g, 1994, https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/theory-heuristic-evaluations/ [主]）。
- 2023 年的版本仍建议 3–5 人独立评估，并强调启发式评估**不能替代**用户研究（Moran & Gordon, NN/g, 2023-06-25, https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/ [主]）。
- 严重度方面，单一评估者的评级不可靠，3 人平均才算够用（Nielsen 1994 [主]，见 1.2(g)）。
- **评估者效应**（evaluator effect）：
  - Sauro 汇总了 33 个数据点，任意两名评估者的问题重叠率中位数为 27%（范围 4–75%）；看同一批参与者时，中位数升到 59%。CUE-1 中 4 个团队共发现 162 个问题，只有 1 个是四队都发现的（*How Large Is the Evaluator Effect in Usability Testing?*, MeasuringU, 2018-03-28, https://measuringu.com/evaluator-effect/ [主：Sauro 的汇总；CUE 数据为次]）。
  - Hertzum & Jacobsen (2001). The Evaluator Effect: A Chilling Fact About Usability Evaluation Methods. *IJHCI* 13(4):421–443 [次：只有 DBLP 题录，https://dblp.uni-trier.de/pid/07/3815.html ]。
  - 1998 年的研究：4 名评估者分析同样 4 段录像，93 个问题中只有 20% 被所有人发现，46% 只被一个人发现 [次：搜索片段，https://researchprofiles.ku.dk/en/publications/the-evaluator-effect-in-usability-studies-problem-detection-and-s/ ]。

### 4.2 专家走查与出声思维的区别

- **认知走查**（cognitive walkthrough）由评审者以新用户视角逐步回答四个问题，依据的是评审者的预测，而不是观察到的行为，不能代替可用性测试（Kim Flaherty, *Evaluate Interface Learnability with Cognitive Walkthroughs*, NN/g, 2022-02-13, https://www.nngroup.com/articles/cognitive-walkthroughs/ [主]）。
- **出声思维的弱点**（Nielsen, *Thinking Aloud: The #1 Usability Tool*, NN/g, 2012-01-15, https://www.nngroup.com/articles/thinking-aloud-the-1-usability-tool/ [主]）：
  - 情境不自然。
  - 参与者会先过滤，想好了再说，所以要捕捉原始的思维流。
  - 主持人可能带偏参与者，受影响的片段应当丢弃。
  - 不适合做统计。

### 4.3 设计者自评 / 第一人称研究

- **错误共识效应**（false consensus）：人们倾向于以为别人和自己想法、行为一致。设计师和研究者对用户的印象主要来自自己和同事这样的小样本，因此特别容易犯这个错。对策是承认偏差、观察真实目标用户、主动去证伪而不是去证实（Raluca Budiu, *You Are Not the User: The False-Consensus Effect*, NN/g, 2017-10-22, https://www.nngroup.com/articles/false-consensus/ [主]）。
- **研究者本人也是用户时**（Rachel Abbott, Hippo, 2022-02-17, https://hippodigital.co.uk/blog/you-are-not-the-user-but-what-about-when-you-are/ [主：作者自述]）：
  - 自己的体验能加深共情，但很难把个人的挫败感和对更广泛用户的证据区分开。
  - 对策：请别人参与记录和分析；当「我」字出现得太多时停下来看看；把个人体验当作讨论的起点，设计决策要落到更广的研究上。
- **第一人称 HCI 方法**（自我民族志 autoethnography、自传式设计 autobiographical design）：
  - Lucero et al. (2019). *A Sample of One: First-Person Research Methods in HCI*. DIS '19 Companion, pp. 385–388 [主·摘要]：第一人称研究正在成为传统 HCI 方法的补充，甚至替代，但其实践与含义还需要界定。https://users.aalto.fi/~luceroa1/research/first-person/
  - Lucero (2018). *Living Without a Mobile Phone: An Autoethnography*. DIS '18 [主·摘要]：作者用文献中「成功民族志的七条标准」检验自己的研究，结果整理成 4 个主题。https://arxiv.org/abs/1804.04833
  - Neustaedter & Sengers (2012) 提出自传式设计的五条原则：genuine need、real system、fast tinkering、record keeping、long-term usage [次：由 2025 年 arXiv 论文转述，https://arxiv.org/pdf/2502.07125 ，原文未读]。
  - ACM TOCHI 2021 年出过第一人称方法专刊，28(6)，Desjardins et al. [次：题录，列于 https://users.aalto.fi/~luceroa1/research/first-person/ ]。
- **主题分析与单个个案**：按个案使用主题分析属于偏离常规的用法，需要专门论证；5 场访谈已经「偏少」（Braun & Clarke FAQ [主]）。

### 4.4 套到本语料 [推论]

- 本语料是**一位评估者（设计师）× 一位参与者（同一人）× 46 场**，而且出声思维的说话者就是分析对象本人。
- 在 Nielsen 三因素框架里，跨场反复出现对应的是 **persistence**（同一用户反复被同一问题困扰），不是跨用户的 **frequency**。所以「出现在 30/46 场」不能写成「普遍问题」。
- 评级、选材、措辞都由单一来源（设计师加 agent）完成，评估者效应和错误共识的风险都存在。

---

## 5. 研究库与跨研究聚合

- **NN/g 的研究库指南**（Maria Rosala, *Research Repositories 101*, NN/g, 2024-07-05, https://www.nngroup.com/articles/research-repositories/ [主]）：
  - 研究库里放研究报告、单条 insight、研究材料、录像和转写稿、原始笔记。
  - **标签从少量宽泛的开始**，预期分类体系会演变；在研究平台里要定义清楚的全局标签。
  - 跨研究、跨时间追踪发现，能看出单次研究看不出的主题。
  - 失败模式：
    - insight 埋在报告里找不到，导致研究重复做。
    - **insight 数据库缺乏做决策需要的上下文**，贡献成本高，还要持续维护。
    - 利益相关者找不到东西就不再来找。
  - 推荐的混合架构：**insight 数据库中的每条 insight 链接回它来源研究的文档夹**。
- **Condens 的标签体系建议**（厂商自述 [主]，https://condens.io/taxonomy_uw ）：
  - 项目标签用来理解新数据，全局标签用来追踪已知主题。判断一条观察能不能打全局标签，看它在本项目之外是否也成立。
  - 先用宽泛的「收集型」标签，某个话题复现后再拆成具体标签。
  - 警惕只挂了一两条证据的标签。
  - 全局标签过多会造成选择困难和理解分歧；只用项目标签又会让跨项目的证据被遗忘。
- **Dovetail 的标签体系建议**（厂商页面，无署名，更新于 2026-08-18 [主：厂商自述]，https://dovetail.com/research/tagging-taxonomy-research-repository-scales-across-teams/ ）：
  - 父子标签最多 2–3 层，围绕用户问题和话题来组织，而不是按团队名组织。
  - **标签表达主题，元数据表达结构**：研究方法、人群、产品区域、日期用字段记录，不要按项目打标签。
  - 每个标签写一句定义，包括它不包含什么。
  - 失败模式：近义词泛滥（例如 onboarding / first-time experience / FTUE 三个标签并存）、颗粒度混杂、废弃标签残留、没有负责人。
  - 治理办法：指定 1–3 名 steward；每月、每季度复审，合并、重命名、归档、拆分；保留变更日志。
- **原子化研究的上下文损失**：见 1.2(e)。User Interviews 指南认为，业务越大越复杂，原子化 insight 越有价值；小型、单渠道的工作未必划算 [次]。
- **研究库失败率**：Looppanel 白皮书（2024）称「80% 的研究库失败」，但没有给出数据来源 [次 / 未核实]。页面上能看到的失败原因是维护跟不上、采用率低（Nikki Anderson 的说法）。https://www.looppanel.com/reports/why-research-repositories-fail
- **跨研究的元综合方法**：Thomas & Harden 2008，描述性主题 → 分析性主题 [主·摘要]，见 1.2(d)。

---

## 附：来源总表

| # | 来源 | 年份 | 类型 | 本次读到的程度 |
|---|---|---|---|---|
| 1 | Krause & Pernice, *Affinity Diagramming*, NN/g — https://www.nngroup.com/articles/affinity-diagram/ | 2024 | 从业者权威 | 正文 [主] |
| 2 | Rosala, *Thematic Analysis*, NN/g — https://www.nngroup.com/articles/thematic-analysis/ | 2022 | 从业者权威 | 正文 [主] |
| 3 | Paul, *Data vs. Findings vs. Insights*（视频）, NN/g — https://www.nngroup.com/videos/data-findings-insights/ | 2023 | 从业者权威 | 页面摘要 [主·摘要] |
| 4 | Nielsen, *Severity Ratings for Usability Problems* — https://www.nngroup.com/articles/how-to-rate-the-severity-of-usability-problems/ | 1994 | 从业者权威 | 正文 [主] |
| 5 | Nielsen, *Heuristic Evaluation theory* — https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/theory-heuristic-evaluations/ | 1994 | 从业者权威 | 正文 [主] |
| 6 | Moran & Gordon, *How to Conduct a Heuristic Evaluation* — https://www.nngroup.com/articles/how-to-conduct-a-heuristic-evaluation/ | 2023 | 从业者权威 | 正文 [主] |
| 7 | Nielsen, *Thinking Aloud: The #1 Usability Tool* — https://www.nngroup.com/articles/thinking-aloud-the-1-usability-tool/ | 2012 | 从业者权威 | 正文 [主] |
| 8 | Moran, *Collecting Metrics During Qualitative Studies* — https://www.nngroup.com/articles/metrics-qualitative/ | 2021 | 从业者权威 | 正文 [主] |
| 9 | Budiu, *Don't Report Numbers from Small UX Studies*（视频）— https://www.nngroup.com/videos/numbers-small-ux-studies/ | 2020 | 从业者权威 | 页面摘要 [主·摘要] |
| 10 | Budiu, *You Are Not the User: The False-Consensus Effect* — https://www.nngroup.com/articles/false-consensus/ | 2017 | 从业者权威 | 正文 [主] |
| 11 | Flaherty, *Cognitive Walkthroughs* — https://www.nngroup.com/articles/cognitive-walkthroughs/ | 2022 | 从业者权威 | 正文 [主] |
| 12 | Rosala, *How Might We Questions* — https://www.nngroup.com/articles/how-might-we-questions/ | 2021 | 从业者权威 | 正文 [主] |
| 13 | Rosala, *Research Repositories 101* — https://www.nngroup.com/articles/research-repositories/ | 2024 | 从业者权威 | 正文 [主] |
| 14 | Braun & Clarke, thematicanalysis.net FAQ / Doing reflexive TA — https://www.thematicanalysis.net/faqs/ | 不详（官方站） | 方法作者本人 | 正文 [主] |
| 15 | Gale et al., Framework method, *BMC Med Res Methodol* 13:117 — https://pmc.ncbi.nlm.nih.gov/articles/PMC3848812/ | 2013 | 同行评审 | 全文 [主] |
| 16 | Thomas & Harden, Thematic synthesis, *BMC Med Res Methodol* 8:45 — https://discovery-pp.ucl.ac.uk/id/eprint/10005258 | 2008 | 同行评审 | 摘要 [主·摘要] |
| 17 | Kolko, Abductive Thinking and Sensemaking, *Design Issues* 26(1) — https://www.jonkolko.com/writingAbductiveThinking.php | 2010 | 同行评审（作者站全文） | 全文 [主] |
| 18 | Sharon, *The Rainbow Spreadsheet*, Smashing Magazine — https://www.smashingmagazine.com/2013/04/rainbow-spreadsheet-collaborative-ux-research-tool/ | 2013 | 从业者自述 | 正文 [主] |
| 19 | Fu, GOV.UK User Research blog — https://userresearch.blog.gov.uk/2019/09/13/how-a-spreadsheet-can-make-usability-analysis-faster-and-easier/ | 2019 | 从业者自述 | 正文 [主] |
| 20 | Sharon, *The atomic unit of a research insight*（Medium）— https://tsharon.medium.com/the-atomic-unit-of-a-research-insight-7bf13ec8fabe | 2016 | 从业者自述 | 403，只核实了题名和日期 |
| 21 | Naylor, Aurelius blog（nugget）— https://blog.aureliuslab.com/2018/07/31/ux-research-nuggets-like-polaris-from-tomer-sharon-and-wework/ | 2018 | 厂商转述 | 正文 [次] |
| 22 | User Interviews, *Atomic Research Nuggets* — https://www.userinterviews.com/ux-research-field-guide-chapter/atomic-research-nuggets | 2019 / 2025 | 厂商转述 | 正文 [次] |
| 23 | Pidcock, *What is Atomic Research?* — https://blog.prototypr.io/what-is-atomic-research-e5d9fbc1285c | 2018 | 从业者自述 | 断连，未读 |
| 24 | Morgan, UXmatters tally sheets — http://www.uxmatters.com/mt/archives/2019/12/data-analysis-making-sense-of-tally-sheets.php | 2019 | 从业者自述 | 正文 [主] |
| 25 | Friedman, Smashing Magazine — https://smashingmagazine.com/2025/05/data-vs-findings-vs-insights-ux/ | 2025 | 从业者综述 | 正文 [主 / 次混合] |
| 26 | Dmitrieva, Bentley UX Center 2 recipes — https://www.bentley.edu/centers/user-experience-center/formative-ux-study-data-analysis-2-simple-recipes | 无日期 | 从业者自述 | 正文 [主] |
| 27 | Torres, *Opportunity Solution Trees*, Product Talk — https://www.producttalk.org/opportunity-solution-tree/ | 2023 | 从业者自述 | 正文 [主] |
| 28 | Bromley, *How to write a games user research report* — https://gamesuserresearch.com/how-to-write-a-games-user-research-report/ | 2022（更新） | 从业者自述（游戏） | 正文 [主] |
| 29 | Sauro, *Rating the Severity of Usability Problems*, MeasuringU — https://measuringu.com/rating-severity/ | 2013 | 从业者 | 正文 [主] |
| 30 | Sauro, *How Large Is the Evaluator Effect*, MeasuringU — https://measuringu.com/evaluator-effect/ | 2018 | 从业者汇总 | 正文 [主] |
| 31 | Hertzum & Jacobsen, *IJHCI* 13(4) — https://dblp.uni-trier.de/pid/07/3815.html | 2001 | 同行评审 | 只有题录和片段 [次] |
| 32 | Molich, Jeffries & Dumas, *JUS* 2(4) — URL 未定位（链接均 404） | 2007 | 同行评审 | 只有搜索摘要 [次] |
| 33 | Molich et al., CUE-2 报告分析 — URL 未定位 | 2004 | 同行评审 | 只有搜索片段 [次] |
| 34 | ISO 25062:2025 — https://www.iso.org/standard/84255.html | 2025 | 标准 | 摘要页 [主·摘要] |
| 35 | Lucero et al., *A Sample of One*, DIS '19 — https://users.aalto.fi/~luceroa1/research/first-person/ | 2019 | 同行评审（工作坊） | 摘要 [主·摘要] |
| 36 | Lucero, *Living Without a Mobile Phone* — https://arxiv.org/abs/1804.04833 | 2018 | 同行评审 | 摘要 [主·摘要] |
| 37 | Neustaedter & Sengers, Autobiographical design, DIS '12（转述见 https://arxiv.org/pdf/2502.07125 ） | 2012 | 同行评审 | 只有他人转述 [次] |
| 38 | Abbott, Hippo blog — https://hippodigital.co.uk/blog/you-are-not-the-user-but-what-about-when-you-are/ | 2022 | 从业者自述 | 正文 [主] |
| 39 | Condens taxonomy guide — https://condens.io/taxonomy_uw | 不详 | 厂商 | 正文 [主：厂商自述] |
| 40 | Dovetail taxonomy page — https://dovetail.com/research/tagging-taxonomy-research-repository-scales-across-teams/ | 2026（更新） | 厂商 | 正文 [主：厂商自述] |
| 41 | Looppanel, *Why research repositories fail* — https://www.looppanel.com/reports/why-research-repositories-fail | 2024 | 厂商 | 落地页 [次 / 数据未核实] |
| 42 | Lucero, *Using Affinity Diagrams to Evaluate Interactive Prototypes* — https://users.aalto.fi/~luceroa1/publications/2015/lucero15_affinity.pdf | 2015 | 同行评审 | 只有标题和目录 |
| 43 | Christensen et al., *Know Your Customers' Jobs to Be Done*, HBR — URL 未定位 | 2016 | 期刊文章 | 只有再版片段 [次] |
| 44 | Miro, *User insights* — https://miro.com/research-and-design/user-insights/ | 不详 | 厂商 | 只有搜索摘要 [次] |

**没能核实的点：**

- Pidcock 原文中各层的确切措辞。
- Sharon 原文中 nugget 的标签分类。
- Thomas & Harden 里分析性主题的具体生成机制。
- Contextual Design 原书中「最多三层」「不预设类目」的原话。
- ISO 25062 报告条目清单。
- Fullerton《Game Design Workshop》中关于设计者自测的论述：只找到书商简介，已从正文中删去。

---

## 6. 对 agent 流程的启示

下面每条都写成可以拿 agent 产出来判断是 / 否的检查项，括号里是依据。

1. **编码前先声明分析框架，并保留「框架外」一栏。** 跑分析之前，先写出本轮的研究问题或设计目标，以及游戏系统 / 模块（或旅程阶段）清单。报告一级标题必须一一对应到框架项，另设一栏「框架外的新发现」，用来放自下而上冒出的新类别，并注明它们是涌现出来的。
   - 检查：报告每个一级标题能否在开工前写下的框架清单里找到？
   - 依据：Rosala 2022；Gale et al. 2013（a priori 码 + 每类留「其他」码）；Sharon 2013（预设观察行 + Summary 表回答研究问题）；Torres 2023（体验地图的时刻作为顶层）；Fu 2019。
2. **主题名测试：每个主题都要是一句有中心观点的断言，不能是话题桶。** 「X 相关问题」「Y 体验」「关于 Z」这类名字一律不合格。
   - 检查：随机抽 5 个主题名，有没有一个能套进「X 的障碍 / Y 的体验」句式？有就是 topic summary。
   - 依据：Braun & Clarke FAQ；Rosala 2022 的「只描述不分析」陷阱。
3. **按洞察类别分组、以论点开头、少而强。** 报告开头先给 1 个最重要的论点和一页摘要。分组依据（机制 / 问题类型 / 研究目标）要显式写明，优先按洞察类别分组，而不是按功能列表分组。主体只保留团队现在必须知道的若干条，其余放附录。
   - 检查：首页有没有一句可以被反驳的论点？有没有写明分组依据？主体条目是否明显少于附录？
   - 依据：Bromley 2022 / Tompkins；Sharon 2013（约 10 条行动项）；CUE-2 报告缺陷 [次]。
4. **每条发现都用「说 / 做分离 + 原因 + 对玩家的影响 + 设计意图 vs 实际体验」的结构来写。** 原话和实际操作分开记；推断不能写进事实层。
   - 检查：每条发现是否都有这四个字段，并且事实字段里不含推断用词？
   - 依据：Bromley 2022（原因 / 影响、预期 vs 实际）；Sharon 2013（debrief 时剔除推断）；Pidcock「fact 不含假设」[次]；Nielsen 2012（出声内容会被过滤）。
5. **四层分开存，并能逐层回溯；finding 数量多于 insight 数量。** 证据片段（会话 ID + 时间戳）、finding、insight、建议分层保存。每条 insight 都要列出它所依据的 finding ID 和会话 ID，报告里的每条 insight 都要能点回原始片段。
   - 检查：随便抽一条 insight，能否在两步之内点到原始片段？finding 总数是否大于 insight 总数？
   - 依据：Morgan 2019；Paul 2023；Rosala 2024（insight 数据库链接回来源研究）。
6. **两段式收口：先归纳，再拿框架拷问。** 描述性主题出来之后，必须再跑一轮「用研究问题 / 设计目标去追问」，产出分析性主题。也可以反过来先写假设性结论再核证据，但**没有会话证据支撑的结论必须删掉**。
   - 检查：流程里有没有一个显式的「重组 / 核证」步骤，并留有被删条目的记录？
   - 依据：Thomas & Harden 2008 [主·摘要]；Dmitrieva（Bentley）的 top-down 配方；Kolko 2010（prioritizing / judging / forging connections）。
7. **计数口径：只写原始计数，不写百分比；频次和严重度分开报；低频高影响的问题不能丢。**
   - 检查：全文有没有「%」「多数玩家」之类的推广性措辞？严重度和频次是不是分两列？
   - 依据：Moran 2021；Budiu 2020；Braun & Clarke FAQ；Gale et al. 2013；Sauro 2013；Fu 2019（亲和图会放大重要性）。
8. **把跨场重复写成 persistence，而不是 prevalence。** 报告里要明说：「出现在 N/46 场」衡量的是同一位玩家被反复困扰的程度，不代表在玩家群体中有多普遍。
   - 检查：频次列的表头或注释里有没有这层说明？
   - 依据：Nielsen 1994 三因素框架 [推论应用]。
9. **严重度要么由多个独立评审给出，要么明确标成「单评估者自评」。** 如果要给严重度，就由不知道频次的多个独立评审（多人；或多个独立设定的模型，这一替代是否满足 Nielsen 的多评估者原则没有来源支持 [推论]）分别打分再取平均，并报告一致性；做不到的话，明确标注是单评估者评级、可靠性有限。
   - 检查：严重度字段有没有注明评审数量和评审方式？
   - 依据：Nielsen 1994（单人不可靠，3 人平均）；Sauro 2013（由不知道频次的人来评）；Sauro 2018 评估者效应；Hertzum & Jacobsen 2001 [次]。
10. **首页声明 n=1、设计师自玩的方法限制，并把 insight 写成待验证的假设或机会。** 首页写明：第一人称 / 自我研究的性质、错误共识风险、出声思维会被过滤，以及主题分析用在单个个案上属于非常规用法。insight 的措辞用「对设计师本人成立；建议用目标玩家验证 ……」，并附上验证建议。
    - 检查：首页有没有限制声明？insight 有没有绝对化地断言「玩家会 ……」？
    - 依据：Budiu 2017；Abbott 2022；Lucero 2018 / 2019；Braun & Clarke FAQ（单个案属偏离常规的用法）；Flaherty 2022（预测 ≠ 观察）；Moran & Gordon 2023（专家评估不能替代用户研究）。
11. **建议要具体、可执行，或者改写成不含方案的机会 / HMW。** 每条建议要写到概念层面、对整体体验有益，并附具体例子；拿不准的写成 opportunity 或 HMW，并检验「至少有两种解法」。
    - 检查：抽查建议里有没有「优化体验」「提升引导」这类不可执行的空话？每个 opportunity 能不能举出两个以上的解法？
    - 依据：Molich, Jeffries & Dumas 2007 [次]；Rosala 2021（HMW）；Torres 2023。
12. **跨会话的标签库要有卫生规则。** 先用少量宽泛的标签，某个话题复现之后再拆；父子层级不超过 3 层。标签只表达主题，日期、游戏、模块、会话类型用元数据字段记录。新建标签前要先查重，并写一句含「不包含什么」的定义。定期合并近义标签，并保留变更日志。
    - 检查：标签总数和层级深度各是多少？有没有近义标签并存？有没有只挂了 1–2 条证据的标签？
    - 依据：Rosala 2024；Condens；Dovetail；Contextual Design 最多三层 [次]。
