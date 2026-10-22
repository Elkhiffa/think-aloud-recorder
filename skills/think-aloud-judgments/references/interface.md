# 接口与结果格式（v2 草稿）

## 命令

在仓库根目录用 Bash 运行。路径含空格和中文，一律加引号。下面的变量由任务给出：`PY` 是 `runtime/python.exe`，`SESSION` 是场次目录，`VAULT` 是资料库目录，`WORK` 是你自己的工作目录（所有文件都放这里，不与其他会话共用）。

```bash
"$PY" -B -X utf8 agent_cli.py reprocess "$SESSION" --worker "<会话标识>" --reason "<为什么重做>" --seconds 3600
"$PY" -B -X utf8 agent_cli.py claim "$SESSION" --worker "<会话标识>" --seconds 3600
"$PY" -B -X utf8 agent_cli.py renew "$SESSION" --token "$TOKEN" --seconds 3600   # 领取后立刻执行一次，确认令牌可用
"$PY" -B -X utf8 agent_cli.py evidence "$SESSION"                      # 全场原话、说话人、时长、revision
"$PY" -B -X utf8 agent_cli.py evidence "$SESSION" --start 120 --end 300 # 区间原话 + 原始操作记录（最多 10 分钟）
"$PY" -B -X utf8 agent_cli.py inputs-summary "$SESSION" --start 120 --end 300  # 操作区段：同一按键或摇杆的连续操作合并，带首尾操作编号
"$PY" -B -X utf8 agent_cli.py quote-words "$SESSION" --ref t000040      # 一条原话的逐词时间
"$PY" -B -X utf8 agent_cli.py context-read "$SESSION" --start 300 --end 420 --compact  # 情景文字，合并相邻相同标题
"$PY" -B -X utf8 agent_cli.py context-read "$SESSION" --start 330 --end 345            # 不合并，含每帧全部文字和坐标
"$PY" -B -X utf8 agent_cli.py frame "$SESSION" --at 362.5 --output "$WORK/frames/f0362.5.jpg"  # 默认 1280 宽 JPEG；看小字加 --width 1920；文件名不能重复
"$PY" -B -X utf8 agent_cli.py validate "$SESSION" --file "$WORK/result.json"
"$PY" -B -X utf8 agent_cli.py submit "$SESSION" --token "$TOKEN" --file "$WORK/result.json"
"$PY" -B -X utf8 agent_cli.py status "$SESSION"
"$PY" -B -X utf8 agent_cli.py fail "$SESSION" --token "$TOKEN" --reason "<原因>"
"$PY" -B -X utf8 agent_cli.py name-activities "$SESSION"                                   # 提交后读命名上下文
"$PY" -B -X utf8 agent_cli.py name-activities "$SESSION" --file "$WORK/naming.json"          # 预览
"$PY" -B -X utf8 agent_cli.py name-activities "$SESSION" --file "$WORK/naming.json" --apply  # 写入
```

命名候选 `naming.json`。`session_id`、`revision`、`result_sha256`、`expected_name` 照抄第一条命令的返回值；`expected_name` 是读取时的原始名称，未命名时为 `""`：

```json
{"version": 1, "session_id": "...", "revision": "...", "result_sha256": "...", "expected_name": "",
 "worker": "<会话标识>", "title": "渡尘墟入门与两局尝试",
 "activities": [{"name": "渡尘墟", "event_ids": ["e01", "e02"]}, {"name": "据点仓库与备战", "event_ids": ["e05"]}]}
```

返回 `can_auto_name: false` 表示记录者手动写过标题：标题会原样保留，详情照常更新。

所有命令输出 UTF-8 JSON：成功是 `{ok:true,data:...}`，失败是 `{ok:false,error:...}`。令牌不要写进任何文档。时间一律是“相对录像开始的秒数”。

界面目录在 `VAULT/game-assets/<场次 session.json 的 game>/catalog.json`。每个界面的 `id` 是规范编号（按界面组命名，规则见 SKILL.md 第 4 步），`aliases` 是曾用过的其他写法，`path_note` 是带层级注释的路径。目录不存在时，界面全部按规则自行命名。

**转写修正**：从上下文认出误转写时，提议给用户确认，不改逐字稿。写一份 UTF-8 JSON，再运行：

```bash
"$PY" -B -X utf8 agent_cli.py transcript-fix-propose "$VAULT" --file "$WORK/fixes.json" --worker "<会话标识>"
```

- 同一个词在别的场次也会这样误听（多是术语、玩法名，如 `左交`→`走焦`），写全库规则：`{"from":"左交","to":"走焦","basis":"上下文在讲手柄焦点移动"}`；
- 只是这一句听错（常用词，如 `老师`→`老是`），写单处修正，加上 `"session_id"` 和 `"ref":"t000123"`；
- 全库规则的门槛（用户 2026-10-22 定）：同一个误转写出现多处、每处都按上下文核对过，而且原文不是常用词（“限时”“上传”“人影”“连续冲刺”这类日常词不行）；规则只是候选：确认前，把 `transcript-fix-list` 列出的每一处命中都结合上下文（拿不准就截图看画面）核对，不该改的用 `transcript-fix-exclude` 排除，剩下的都对了才确认。整理新场次时，也用 `transcript-fix-list VAULT --status confirmed --session <场次 id>` 核对已确认规则在这一场的命中，不该改的同样排除。
- 提议只写进资料库的 `transcript-corrections.json` 待确认，不改任何引用；用户确认后，引用自动带上 `corrected_text`。这是单场整理唯一可以写资料库根目录的地方，只能通过这条命令。

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
    "inputs": "partial",
    "limitations": ["只在需要核实的时刻看了画面，其余依据原话和情景文字。"]
  },
  "events": [{
    "id": "e01", "start": 300, "end": 620,
    "title": "清理背包",
    "summary": "玩家想做什么、主要过程、结果。",
    "basis": "explicit", "kind": "friction",
    "evidence": [{"kind": "quote", "ref": "t000020"}]
  }],
  "ideas": [],
  "questions": [],
  "instances": [{
    "id": "i01", "event_id": "e01",
    "said": [{"kind": "quote", "ref": "t000020"}],
    "refers_to": {"start": 350, "end": 355, "basis": "same_time", "note": "定位依据，可选"},
    "screen": "背包/道具", "elements": ["自动使用道具"],
    "kind": "expectation",
    "statement": "独立可读的陈述，原话加引号。",
    "issue_tags": [],
    "evidence": [{"kind": "video", "start": 362.5, "end": 362.5, "observation": "画面事实"},
                 {"kind": "input", "ref": "i0001234"}],
    "confidence": "high"
  }, {
    "id": "i02", "event_id": "e01",
    "said": [{"kind": "quote", "ref": "t000031"}],
    "refers_to": {"basis": "earlier_session", "note": "所指的更早游玩"},
    "compare_to": {"start": 330, "end": 332, "note": "被比较的另一个时刻，可选字段"},
    "screen": "某入口/某页签", "screen_proposed": true, "route": ["另一入口/页签", "某入口/某页签"],
    "elements": [], "kind": "negative", "statement": "……", "issue_tags": [], "evidence": [], "confidence": "medium"
  }]
}
```

## 校验规则（不满足会被拒）

- 活动：`basis` 只能是 `explicit`、`observed`、`inferred`；`kind` 只能是 `friction`、`positive`、`routine`、`question`。每个活动至少一条证据，`explicit` 的必须引用原话。活动的所有证据都必须落在它自己的 start–end 之内。标题最多 160 字。
- 证据类型：原话 `{"kind":"quote","ref":"t…"}`；原话节选 `{"kind":"quote_words","ref":"t…","word_range":[起,止)}`（半开区间、原始词序号，取自 `quote-words`）；画面 `{"kind":"video","start":…,"end":…,"observation":"…"}`，一帧时 start=end，而且必须落在 `coverage.video_ranges` 里；操作 `{"kind":"input","ref":"i…"}`，编号取自 `evidence` 区间或 `inputs-summary` 的首尾编号，`coverage.inputs` 不能是 `none`。引用不要手抄文字，程序会自动展开原文和时间。
- 实例 `said` 至少一条，只能是 quote 或 quote_words。
- `refers_to.basis` 只能是 `same_time`、`retrospective`、`unknown`、`earlier_session`。前三种必须有录像时长内的 start、end；回顾实例的 end 不能晚于最早那句 `said` 的开始时间。`earlier_session` 不填 start、end，`note` 必填。`note` 最多 200 字。
- `compare_to` 可选：`{start, end, note?}`，在录像时长之内。
- `kind` 只能是 `confusion`、`obstacle`、`cost`、`positive`、`negative`、`expectation`、`suggestion`、`self_correction`、`observation`；`confidence` 只能是 `high`、`medium`、`low`。
- `screen` 是字符串或 null。目录存在时，不在目录里的界面必须标 `screen_proposed: true`，否则整份结果被拒。`route` 可选，最多 20 个界面名。`screen_context` 只在 `screen` 为 null 时使用，取值 `hud`、`multi_screen`、`outside_game`、`unknown`。`elements` 是画面文字列表，最多 20 个。
- `statement` 最多 300 字；`evidence` 最多 12 条，每条 observation 最多 300 字；`issue_tags` 填 `[]`；只有记录者明说 bug、把问题归到程序本身或用跑测报缺陷的说法时填 `["BUG"]`（见 SKILL 第 7 步）。
- 数量上限：活动 300、每个活动的证据 30、实例 300；整个结果不超过 2 MB。
- `coverage.transcript` 和 `inputs` 只能是 `full`、`partial`、`none`，按实际读过的范围填。
