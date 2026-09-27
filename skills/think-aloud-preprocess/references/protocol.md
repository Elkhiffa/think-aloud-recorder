# 本地接口 v1

选择实际安装路径后，用 PowerShell 的参数列表传参；包含空格与中文的路径需引用。以下 `$app`、`$session`、`$database`、`$candidate` 均为当前任务已确认的路径，不是系统变量。

```powershell
& "$app\runtime\python.exe" "$app\agent_cli.py" scan "$database"
& "$app\runtime\python.exe" "$app\agent_cli.py" publish "$session"
& "$app\runtime\python.exe" "$app\agent_cli.py" claim "$session" --worker "本次会话标识" --seconds 1800
& "$app\runtime\python.exe" "$app\agent_cli.py" evidence "$session"
& "$app\runtime\python.exe" "$app\agent_cli.py" evidence "$session" --start 120 --end 180
& "$app\runtime\python.exe" "$app\agent_cli.py" frame "$session" --at 135 --output "$work\frame-135.jpg"
& "$app\runtime\python.exe" "$app\agent_cli.py" renew "$session" --token "$token" --seconds 1800
& "$app\runtime\python.exe" "$app\agent_cli.py" validate "$session" --file "$candidate"
& "$app\runtime\python.exe" "$app\agent_cli.py" submit "$session" --token "$token" --file "$candidate"
& "$app\runtime\python.exe" "$app\agent_cli.py" status "$session"
& "$app\runtime\python.exe" "$app\agent_cli.py" fail "$session" --token "$token" --reason "具体未完成原因"
```

输出是 UTF-8 JSON：成功 `{ok:true,data:...}`，失败 `{ok:false,error:...}` 并退出 1。领取时读取 `data.claimed`；false 时 reason 为 `busy` 或 `complete`。令牌仅属于该次领取，默认 30 分钟，可在到期前续期。不要将令牌写入分析文档。

`scan` 只读就绪信号；`scan --publish` 可为资料库中所有整理完成的旧场次补发/更新信号，所以只在已获授权的场次范围内使用。单场次用 `publish` 更精确。录制/转写未完成或失败的场次不会发布。合成测试仅用 `--include-test` 纳入。

`evidence` 提供原话稳定引用 `t000001`、说话人信息、素材路径、缺口与窗口状态。带时间范围时还提供输入引用 `i0000001`、已对齐的 start/end，以及原始 source_start/source_end。若 `inputs.truncated=true`，按更短时间段重读；不能把截断部分当没有输入。

`frame` 使用本机 FFmpeg，输出最大宽度 1920 的画面，并返回时间与源 revision。输出必须是场次之外工作目录中的新 `.jpg`/`.png`。调用成功并不等于已检查画面：用图像查看工具读取后才能记入检查范围。若需要判断状态变化，要检查前后帧或视频片段，不把一帧当成持续过程。原声路径由 evidence 提供。

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
    "title": "符合证据的简短事件名",
    "summary": "观察到什么、做了什么、结果如何；未知项明确标注。",
    "context": "补充当时的目标或前后关系；推测须说明。",
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
- 原话和输入只填引用，不手工复制文本或调整时间；发布时程序从当前素材展开，防止引用漂移。参考 quote.speaker_id 保留其他讲述者的身份。
- coverage.transcript / inputs 为 `full`、`partial` 或 `none`，只描述本轮实际检查范围。无有效操作时记 `none` 并写限制；缺口不等于没有操作。
- events 最多 300，每事件证据最多 30；ideas 最多 100；questions 最多 30。多数场次应远少于上限，无充分依据可返回空列表。
- idea/question 的 event_id 可为 null，表示整场线索。问题无需答案即可完成。
- 候选与展开后的结果均不超过 2 MB。只支持 v1；未知附加字段不会进入回看。

原子提交位置是场次内的 `experience-events.json`，就绪文件 `agent-ready.json`，领取文件 `agent-state.json`。不要直接改这些文件；通过 CLI 更新才有并发检查、版本校验和历史保留。revision 包含素材文件大小/修改时间、同步偏移和记录者选择，不是内容真实性签名。结果中自动加入回执，UI 不显示领取令牌。
