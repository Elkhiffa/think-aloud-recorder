# 内容概括与场次命名

标题与详情分开。标题像聊天会话名，简短概括本场核心内容，通常 8–20 个汉字，最多 60 字、单行。例如“清河探索与初次止戈”；不是用加号列全所有活动。示例不代表本场事实。

`activities` 尽量保留有依据的独立任务、地区、玩法和具体目标，不限前三项。使用“清河任务”“止戈”“萌宠争锋”等明确内容，不套固定粗分类；合并重复，排除仅提到但未参与的活动。每项关联当前结果中的事件。未知处不猜。项目名和日期由记录器另行显示。

手动标题完整保留，重新整理只更新内容详情；没有手动标题则使用新的短标题。尚未自动命名时默认项目名。旧长自动名称会作为详情呈现；仅依照记录器保存的所有权识别，不解析用户任意方括号。

先读取命名上下文，要求 `naming_policy="separate-title-v3"`（0.7.1）。旧版请先升级，不使用会追加长标题的旧策略，也不直接改 session.json。

```powershell
& "$app\runtime\python.exe" "$app\agent_cli.py" name-activities "$session"
& "$app\runtime\python.exe" "$app\agent_cli.py" name-activities "$session" --file "$candidate"
& "$app\runtime\python.exe" "$app\agent_cli.py" name-activities "$session" --file "$candidate" --apply
```

候选使用接口返回的真实身份和当前 `expected_name`（原始值，未命名为 ""；不要填界面默认项目名）：

```json
{
  "version": 1,
  "session_id": "实际场次ID",
  "revision": "实际素材revision",
  "result_sha256": "实际结果SHA256",
  "expected_name": "",
  "worker": "本次会话标识",
  "title": "清河探索与初次止戈",
  "activities": [
    {"name": "清河任务", "event_ids": ["e1"]},
    {"name": "探索", "event_ids": ["e2"]},
    {"name": "止戈", "event_ids": ["e3"]}
  ]
}
```

`can_auto_name=false` 表示保留手动标题，仍要更新详情。`--apply` 在场次锁内检查素材、结果摘要和名称，再保存元数据；返回 `short_title`、实际 `title` 和 `activity_details`。`manual_name_preserved=true` 意味手动标题原文未变，不再追加摘要。旧调用未给 title 时保留已有短标题或默认项目名，不从活动列表重新生成长标题。

并发改名或重做结果时拒绝旧候选：重新读取后核对内容，不只替换摘要。相同候选重试幂等。不得改源录像、就绪标记、事件原稿或领取记录。最多32个内容项、每项24字，至少一条有效 event_ids；名称不含加号、方括号或控制字符。引用有效不等于语义正确，仍需检查内容与覆盖。
