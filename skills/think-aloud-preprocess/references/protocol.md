# 本地接口 v1

选择实际安装路径后，用 PowerShell 的参数列表传参；包含空格与中文的路径需引用。以下 `$app`、`$session`、`$database`、`$candidate` 均为当前任务已确认的路径，不是系统变量。

```powershell
& "$app\runtime\python.exe" "$app\agent_cli.py" scan "$database"
& "$app\runtime\python.exe" "$app\agent_cli.py" publish "$session"
& "$app\runtime\python.exe" "$app\agent_cli.py" claim "$session" --worker "本次会话标识" --seconds 1800
& "$app\runtime\python.exe" "$app\agent_cli.py" reprocess "$session" --worker "本次会话标识" --reason "用户要求用画面节点重新分析并比较" --seconds 1800
& "$app\runtime\python.exe" "$app\agent_cli.py" evidence "$session"
& "$app\runtime\python.exe" "$app\agent_cli.py" visual-nodes "$session" --output "$work\visual-pass-01" --max-images 120
& "$app\runtime\python.exe" "$app\agent_cli.py" visual-overview "$work\visual-pass-01\index.json"
& "$app\runtime\python.exe" "$app\agent_cli.py" visual-plan "$work\visual-pass-01\index.json" --output "$work\evidence-plan-01" --total-views 24 --initial-views 12 --review-views 4
& "$app\runtime\python.exe" "$app\agent_cli.py" visual-packet "$work\evidence-plan-01\plan.json" --request-id first --phase initial --question "浏览主要过程的候选画面"
& "$app\runtime\python.exe" "$app\agent_cli.py" visual-candidates "$work\visual-pass-01\index.json" --start 120 --end 180 --limit 10
& "$app\runtime\python.exe" "$app\agent_cli.py" evidence "$session" --start 120 --end 180
& "$app\runtime\python.exe" "$app\agent_cli.py" visual-packet "$work\evidence-plan-01\plan.json" --request-id transition --phase inspect --question "这段操作前后界面是否切换" --start 132 --end 138 --limit 4
& "$app\runtime\python.exe" "$app\agent_cli.py" visual-budget "$work\evidence-plan-01\plan.json"
& "$app\runtime\python.exe" "$app\agent_cli.py" renew "$session" --token "$token" --seconds 1800
& "$app\runtime\python.exe" "$app\agent_cli.py" validate "$session" --file "$candidate"
& "$app\runtime\python.exe" "$app\agent_cli.py" submit "$session" --token "$token" --file "$candidate"
& "$app\runtime\python.exe" "$app\agent_cli.py" status "$session"
& "$app\runtime\python.exe" "$app\agent_cli.py" fail "$session" --token "$token" --reason "具体未完成原因"
```

输出是 UTF-8 JSON：成功 `{ok:true,data:...}`，失败 `{ok:false,error:...}` 并退出 1。领取时读取 `data.claimed`；false 时 reason 为 `busy` 或 `complete`。令牌仅属于该次领取，默认 30 分钟，可在到期前续期。不要将令牌写入分析文档。

`scan` 只读就绪信号；`scan --publish` 可为资料库中所有整理完成的旧场次补发/更新信号，所以只在已获授权的场次范围内使用。单场次用 `publish` 更精确。录制/转写未完成或失败的场次不会发布。合成测试仅用 `--include-test` 纳入。

`reprocess` 仅用于用户明确授权重做的已有结果，要求填写理由。领取成功前，接口将原结果的原始字节保存到场次 `agent-history` 并校验 SHA-256；返回备份路径与摘要。备份失败则不建立新任务。有效的其他领取仍返回 `busy`，不得手工抢占。重做中旧结果继续可读，失败或超时也不移除；新结果只有通过正常 `validate`／`submit` 后才替换。`status` 的 `reanalysis` 描述重做进展，`state=complete` 仍指原结果可用。无既有结果时用 `claim`。旧结果过期时也要保留基线，但比较报告须区分素材变更。

`visual-nodes` 默认检查整场，支持 `--start`／`--end` 和 1–500 的图片预算（默认 120）。输出必须为资料库以外的新目录，不覆盖已有索引。`visual-read` 按页（最多 100 节点）或时间段读取，校验源 revision 后返回实际图片路径、原话引用与有限操作摘要。须实际用看图工具检查图片才能计入 `video_ranges`；逐帧机械检测不等于模型检查。配图不足时按需缩短范围补取，详见安装目录的 `docs/visual-nodes.md`。`visual-review INDEX` 可启动仅本机的检查页。

`evidence` 提供原话稳定引用 `t000001`、说话人信息、素材路径、缺口与窗口状态。带时间范围时还提供输入引用 `i0000001`、已对齐的 start/end，以及原始 source_start/source_end。若 `inputs.truncated=true`，按更短时间段重读；不能把截断部分当没有输入。

`frame` 使用本机 FFmpeg，输出最大宽度 1920 的画面，并返回时间与源 revision。输出必须是场次之外工作目录中的新 `.jpg`/`.png`。调用成功并不等于已检查画面：用图像查看工具读取后才能记入检查范围。若需要判断状态变化，要检查前后帧或视频片段，不把一帧当成持续过程。原声路径由 evidence 提供。

`visual-overview INDEX [--bins 32]` 返回全时间范围的紧凑导航表，不含原话正文、图片或全部节点详情。它使用既有完整索引，不是重新抽帧；源 revision 检查与详细读取相同。原话仍单独完整读取，概览中的未配图、弱变化和省略范围仍需按需展开或标明未审查。`visual-read` 与概览的 `read_metrics` 只计返回字符／路径，不代表模型 token、费用或已看图数量。

`visual-plan` 绑定原索引摘要和源 revision，在新工作目录生成 `plan.json`、`budget.json`。只归并连续近似图／既有运动段并保留短变化组，不把像素相似当作相同 UI 或相同目标。完整索引保留不动，首轮包不是全部候选清单。默认 24/12/4 是总发放额／首轮上限／复核预留，实际是否足够须以小样本判断。

`visual-packet` 发放图片而不调用模型。`initial` 使用计划选图；`inspect/review` 必须给出问题与 1–12 个 `--at` 时间点，或最多 120 秒的 `--start/--end` 区间（`--limit` 2–12，默认 6）。复用现有图片或仅定位补图，返回实际显示时间、路径和 SHA-256。`state=ready` 后才能实际打开图片；`budget_exceeded` 不取图，`pending/failed` 保留预算且不自动重跑。重复相同请求编号只返回原回执，真正重看须用新编号；同一画面复核仍计次。`deferred_bundles`、`deferred_initial_transitions` 表示未完整发放的变化组，不能写成已检查。

`visual-budget` 是所有调用者共用的发放账本，不是实际看图或 token 统计。禁止通过另建计划、旧 `frame` 或直接打开完整图集绕过同场预算；超额时保留具体待查问题。不同阶段的图片联系表仍按原始时间点计次，未实际看的已发图也保守计入。源或索引变化需新版本计划，须连同已有用量报告交接，不得以素材变化静默重置整场预算。旧版本无这些命令时手工执行相同记录与限制，不能假装入口已经硬性拦截。

`visual-candidates`（0.6.5）要求 start/end，范围最长 120 秒，`limit` 1–60、默认 24。主要与弱候选共用分页数量上限，返回紧凑 columns/rows 与 next_offset，不展开原话、按键、图片或完整 motion 子树。它没有实际看图，也不是流程识别。`visual-read` 保留完整格式，但小 limit 不能保证小输出。

0.6.7 先用 `visual-candidates INDEX --start 120 --end 180 --level primary --limit 24`，按需再用 `--level weak --parent v000123` 展开该主要节点的弱观察。`--parent` 只适用于 weak；不填 parent 则查范围内全部保留的弱观察。默认 all 兼容旧顺序。筛选先于分页，切换筛选后从 offset 0 开始。新增列为 parent_id、retained_weak_in_range；matching_by_level 是筛选前该区间保留的两类数量。omissions 是全索引遗漏数量／时间包络和 overlaps_query，不代表包络内每一秒均缺失。主要分页读完不改变 node_index_complete；筛选不能代替短暂状态的弱观察核对。

`visual-nodes ... --image-mode seek`（0.6.7）仅优化配图，仍逐帧检测并精确匹配所选原时间戳；默认 sequential。若定位错过帧，最多恢复一次原范围顺序配图，只收集未完成图片。成功响应和 metrics 的 image_sequential_recovery 明示恢复，恢复后仍缺帧则失败不发布索引。image_decoder_frames 包含前滚／边界帧，image_decode_requests 包含恢复；比较完整耗时，不能只看交付图片数。已有索引与取材计划均继续复用。

0.6.5 新计划为 `version=2, selection_version=2`：首轮避免邻近动画重复占位，区间包按局部稳定程度与时间距离排序，选择变化中段而不是优先凑满一个末端三图组；回执 selection 记录来源候选与选择原因。`initial_already_issued` 表示首轮已发，若要取回原回执使用原请求编号。0.6.5 读取旧版计划时保持原始排序／回执／预算，不能自动改写旧计划。旧软件不支持新计划，不能混用。画面分组、稳定度、近黑筛选均是机械信号，不能替代 UI 文本核对或玩家目标判断。

## 候选结果

以下是虚构结构示例，ID 和时间需使用实际 evidence 返回值；不复用示例结论：

```json
{
  "version": 1,
  "session_id": "来自接口的场次ID",
  "revision": "来自接口的revision",
  "summary": "说明本轮整理范围和主要体验线索。",
  "coverage": {
    "video_ranges": [{"start": 132, "end": 132}, {"start": 136, "end": 136}],
    "transcript": "full",
    "inputs": "partial",
    "limitations": ["仅检查候选事件附近的画面，未连续看完整场录像。"]
  },
  "events": [{
    "id": "e1", "start": 130, "end": 140,
    "title": "尝试找到并比较适用的装备",
    "summary": "观察到什么、做了什么、结果如何；未知项明确标注。",
    "context": "记录者当前目标与前后关系；仅从画面推测时明确说明，无法识别时写目标未明。",
    "basis": "explicit", "kind": "friction",
    "evidence": [
      {"kind": "quote", "ref": "t000012"},
      {"kind": "input", "ref": "i0000042"},
      {"kind": "video", "start": 136, "end": 136, "observation": "实际检查到的画面事实"}
    ]
  }],
  "ideas": [{"id": "h1", "event_id": "e1", "idea": "后续值得比较或验证的方向", "reason": "为什么这段证据值得展开"}],
  "questions": [{"id": "q1", "event_id": "e1", "question": "一个可选补充问题", "reason": "当前材料缺少哪部分信息"}]
}
```

- 时间单位是相对录像开始的秒。所有证据必须位于对应事件时间段，画面证据还必须落在实际检查的 video_ranges 中。一帧用 start=end。
- basis：`explicit`（有原话引用的明确表达）、`observed`（可见现象）、`inferred`（推测）。这是事件依据类型，不是量化置信度。
- kind：`friction`、`positive`、`routine`、`question`。用 summary 区分事实与假设，分类本身不代表设计结论。
- 事件以目标与过程组织，沿用 v1 的 title/context/summary，正常过程可用 `routine`；不新增私有 schema。问题从事件中归纳，在 summary/ideas 或单独对比报告中记录，并引用事件和源证据。没有原话不等于没有目标；画面推测目标时用 `inferred`，不要因存在无关原话就标成 `explicit`。
- 原话和输入只填引用，不手工复制文本或调整时间；发布时程序从当前素材展开，防止引用漂移。参考 quote.speaker_id 保留其他讲述者的身份。
- coverage.transcript / inputs 为 `full`、`partial` 或 `none`，只描述本轮实际检查范围。无有效操作时记 `none` 并写限制；缺口不等于没有操作。
- events 最多 300，每事件证据最多 30；ideas 最多 100；questions 最多 30。多数场次应远少于上限，无充分依据可返回空列表。
- idea/question 的 event_id 可为 null，表示整场线索。问题无需答案即可完成。
- 候选与展开后的结果均不超过 2 MB。只支持 v1；未知附加字段不会进入回看。

原子提交位置是场次内的 `experience-events.json`，就绪文件 `agent-ready.json`，领取文件 `agent-state.json`。不要直接改这些文件；通过 CLI 更新才有并发检查、版本校验和历史保留。revision 包含素材文件大小/修改时间、同步偏移和记录者选择，不是内容真实性签名。结果中自动加入回执，UI 不显示领取令牌。
