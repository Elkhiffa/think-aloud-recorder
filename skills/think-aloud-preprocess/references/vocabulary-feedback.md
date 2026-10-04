# 经核实词条回流

仅在用户授权本次补词时执行。游戏专有名词与可复用 UX 术语分别加入用户指定的现有词库；不把未经核实的转写猜测加入热词。保留原文件备份、去重，并把词条对应的场次、原话/画面依据和核实情况记在私人来源记录中。不要把个人词库或来源记录复制进源码、skill 或发行包。

修改 TXT 不等于预设已生效。记录器 0.7.5 起支持以下本机接口，使用已安装版本的 `app/runtime/python.exe -X utf8 app/agent_cli.py`：

1. `vocabulary-status` 返回预设 ID、当前快照摘要与词数。明确目标预设，不默认刷新所有同名游戏预设。
2. `vocabulary-preview --preset ID --source 游戏词库文件名.txt --source uiux-terms.txt --output 工作目录/词库计划.json`。可重复 `--source`，只指定本次授权且已导入该预设的文件。核对新增词、保留的旧词、手动词数、总数与文件 SHA。计划包含私有新增词，不发布到公共仓库。
3. `vocabulary-apply --plan 工作目录/词库计划.json`。应用只增补快照，不改源文件、手动词、其他预设或历史场次。
4. `vocabulary-status --preset ID --source 游戏词库文件名.txt --source uiux-terms.txt` 回读。记录应用回执的 `saved`/`effective` 一致情况、词数、摘要及版本，区分“TXT 已追加”和“预设已生效”。

`BUSY` 时不打断录制/保存，不启动循环扫描；本轮等操作结束后可重试同一计划，否则报告仍待生效。`CONFLICT` 表示文件或预设又变了，保留旧计划后重新预览并复核；不改计划摘要硬提交。`RESPONSE_UNCONFIRMED` 时先回读或重试原计划；同一有效计划重复应用不会再次写入。`APP_UNAVAILABLE` 或旧版本没有命令时保留已核实词和来源记录，说明需更新/启动应用，不能直接编辑 `config.json` 或宣称已经生效。预设没有唯一同名快照时，在设置中明确导入后再继续。

默认不重跑已有分析、不重转写，也不改变历史场次的术语快照。超限不静默截断或删除用户词。需要更多接口细节时读安装的 `app/docs/vocabulary-agent.md`。
