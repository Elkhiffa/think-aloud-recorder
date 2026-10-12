# 接口与结果格式（v2 草稿）

## 命令

在仓库根目录用 Bash 运行。路径含空格和中文，一律加引号。下面的变量由任务给出：`PY` 是 `runtime/python.exe`，`SESSION` 是场次目录，`WORK` 是资料库以外的工作目录。

```bash
"$PY" -B -X utf8 agent_cli.py reprocess "$SESSION" --worker "<会话标识>" --reason "<为什么重做>" --seconds 3600
"$PY" -B -X utf8 agent_cli.py claim "$SESSION" --worker "<会话标识>" --seconds 3600
"$PY" -B -X utf8 agent_cli.py renew "$SESSION" --token "$TOKEN" --seconds 3600
"$PY" -B -X utf8 agent_cli.py evidence "$SESSION"                      # 全场原话、说话人、时长、revision
"$PY" -B -X utf8 agent_cli.py evidence "$SESSION" --start 120 --end 300 # 区间原话 + 操作记录（最多 10 分钟）
"$PY" -B -X utf8 agent_cli.py quote-words "$SESSION" --ref t000040      # 一条原话的逐词时间
"$PY" -B -X utf8 agent_cli.py context-read "$SESSION" --start 300 --end 420 --compact  # 情景文字，合并相邻相同标题
"$PY" -B -X utf8 agent_cli.py context-read "$SESSION" --start 330 --end 345            # 不合并，含每帧全部文字和坐标
"$PY" -B -X utf8 agent_cli.py frame "$SESSION" --at 362.5 --output "$WORK/frames/f0362.5.png"  # 1920 宽截图；文件名不能重复
"$PY" -B -X utf8 agent_cli.py validate "$SESSION" --file "$WORK/result.json"
"$PY" -B -X utf8 agent_cli.py submit "$SESSION" --token "$TOKEN" --file "$WORK/result.json"
"$PY" -B -X utf8 agent_cli.py status "$SESSION"
"$PY" -B -X utf8 agent_cli.py fail "$SESSION" --token "$TOKEN" --reason "<原因>"
```

所有命令输出 UTF-8 JSON：成功是 `{ok:true,data:...}`，失败是 `{ok:false,error:...}`。令牌不要写进任何文档。时间一律是“相对录像开始的秒数”。

情景文字是每 5 秒一帧的本地 OCR，有错字、会漏掉短暂状态，只能当线索。`frame` 截的是那一刻的静态画面，不证明前后过程。

## 结果 JSON

```json
{
  "version": 2,
  "session_id": "<evidence 返回的 session_id>",
  "revision": "<evidence 返回的 revision>",
  "summary": "本场主要活动和整理范围，一两句。",
  "coverage": {
    "video_ranges": [{"start": 362.5, "end": 362.5}],
    "transcript": "full",
    "inputs": "none",
    "limitations": ["只在需要核实的时刻看了画面，其余依据原话和情景文字。"]
  },
  "events": [{
    "id": "e01", "start": 300, "end": 620,
    "title": "清理背包",
    "summary": "目标、主要过程、结果。",
    "basis": "explicit", "kind": "friction",
    "evidence": [{"kind": "quote", "ref": "t000020"}]
  }],
  "ideas": [],
  "questions": [],
  "instances": [{
    "id": "i01", "event_id": "e01",
    "said": [{"kind": "quote", "ref": "t000020"}],
    "refers_to": {"start": 350, "end": 355, "basis": "same_time", "note": "定位依据，可选"},
    "screen": "背包", "elements": ["自动使用道具"],
    "kind": "expectation",
    "statement": "独立可读的陈述。",
    "issue_tags": [],
    "evidence": [{"kind": "video", "start": 362.5, "end": 362.5, "observation": "画面事实"}],
    "confidence": "high"
  }]
}
```

## 校验规则（不满足会被拒）

- 活动：`basis` 只能是 `explicit`、`observed`、`inferred`；`kind` 只能是 `friction`、`positive`、`routine`、`question`。每个活动至少一条证据，`explicit` 的必须引用原话。活动的所有证据都必须落在它自己的 start–end 之内。标题最多 160 字。
- 证据类型：原话 `{"kind":"quote","ref":"t…"}`；原话节选 `{"kind":"quote_words","ref":"t…","word_range":[起,止)}`（半开区间、原始词序号，取自 `quote-words`）；画面 `{"kind":"video","start":…,"end":…,"observation":"…"}`，一帧时 start=end，而且必须落在 `coverage.video_ranges` 里。引用不要手抄文字，程序会自动展开原文和时间。
- 实例：`said` 至少一条，只能是 quote 或 quote_words。`refers_to` 必须在录像时长之内；`basis` 只能是 `same_time`、`retrospective`、`unknown`；回顾实例的 `refers_to.end` 不能晚于最早那句 `said` 的开始时间；`note` 最多 200 字。
- `kind` 只能是 `confusion`、`obstacle`、`positive`、`expectation`、`suggestion`、`self_correction`、`observation`；`confidence` 只能是 `high`、`medium`、`low`。
- `statement` 最多 300 字；`evidence` 只能是 video，最多 12 条，每条 observation 最多 300 字；`issue_tags` 填 `[]`；`screen` 是字符串或 null；`elements` 是字符串列表。
- 数量上限：活动 300、每个活动的证据 30、实例 300；整个结果不超过 2 MB。
- `coverage.transcript` 和 `inputs` 只能是 `full`、`partial`、`none`，按实际读过的范围填。没读操作记录就填 `none`，这时也不能引用 input。
