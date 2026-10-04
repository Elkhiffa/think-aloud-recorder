# 本机 agent 词库快照刷新（0.7.5）

词库导入后，预设保存的是词条快照；修改 TXT 不会自动改变快照。此接口让外部 agent 在补词完成后，明确预览并刷新指定预设。无需内置 AI，也不会启动转写、重做场次、扫描资料库或上传内容。

安装 0.7.5 或更新版本并重新启动记录器后可用。接口只在记录器运行期间存在，绑定 `127.0.0.1` 随机端口，并由安装内的私有令牌鉴权。CLI 自动读取本安装的端点；不要复制或打印 `app/state/vocabulary-agent.json`。接口未启动不影响录制和回看，CLI 会返回不可用，不绕过应用直接改 `config.json`。

## 调用

以下 PowerShell 示例以 `F:\ThinkAloud` 安装为例。`$presetId` 使用回读返回的真实 ID，`game-terms.txt` 替换为已导入该预设的游戏词库文件名；计划文件放在本次私人工作目录。

```powershell
$python = 'F:\ThinkAloud\app\runtime\python.exe'
$cli = 'F:\ThinkAloud\app\agent_cli.py'
& $python -X utf8 $cli vocabulary-status

# 预览：尚不写入预设，也不修改 TXT。
& $python -X utf8 $cli vocabulary-preview --preset $presetId --source 'game-terms.txt' --source 'uiux-terms.txt' --output .\vocabulary-plan.json

# 阅读计划后应用同一份文件。
& $python -X utf8 $cli vocabulary-apply --plan .\vocabulary-plan.json

# 回读运行中应用实际使用的快照及源文件摘要。
& $python -X utf8 $cli vocabulary-status --preset $presetId --source 'game-terms.txt' --source 'uiux-terms.txt'
```

CLI 返回 `{ok, data}` 或 `{ok:false, code, error}`，失败退出码为 1。默认连接 CLI 所属安装；开发验证可显式提供 `--app-root`，但旧应用不会因使用新 CLI 就获得接口能力。

预览包含源文件 SHA-256、文件词数、原快照和目标快照 ID、明确新增词、从文件缺失但保留的旧词数、手动词数和合并总数。计划带安装路径、预设 ID 与前后状态摘要。计划及回执包含私人词汇，不提交到 Git 或放入软件包；`--output` 不覆盖已有计划。

应用回执中的 `saved` 来自实际配置文件回读，`effective` 来自运行中应用；两者必须一致。`changed:false` 表示已经生效的相同计划或无新增词，不重复写配置。随后 `vocabulary-status` 可再次独立核对摘要和词数。选中的预设会同步当前录制配置；非选中预设只更新自身，不切换预设。

## 边界和冲突

- 每次一个预设、1–16 个明确的 TXT 文件名，仅从当前安装的 `vocabularies` 直接读取。不接受路径、SCEL、符号链接或目录联接。原文件应已备份、核实新增词并去重；此接口只刷新快照，不负责改源文件。
- 预设中必须已存在唯一同名快照；计划同时绑定旧快照内容 ID 和本次源文件 SHA。遇到同名多个快照或未导入的词库，先在设置中明确选择，不猜对应关系。
- 只合并新增词，保留原有词条与手动补充原文；源文件删词不会删除快照中的词。未指定的词库、其他预设、设备、密钥、历史场次和正在转写的场次设置不变。
- 整组词库先验证再原子保存：单文件不超过 8 MB；总词数沿用 2000 上限；Qwen 中文/混合词条最多 15 字符、纯英文最多 7 单词。超限不截断，不保存一半。
- `CONFLICT`：源文件或目标预设在预览后变化。保留原计划，重新预览为新文件并复核，不自行篡改计划摘要。
- `BUSY`：正在录制、保存、选择文件或操作录制引擎。当前任务继续运行，本次未应用；操作结束后重试同一计划。不让 agent 常驻轮询。已排队/进行中的转写继续使用自己的原场次快照。
- `CONFIG_CHANGED`：检测到其他工具直接改写配置。停止写入，正常重启记录器后再预览；不要覆盖外部改动。
- `RESPONSE_UNCONFIRMED`：连接中断，可能已经应用。先回读或重试同一计划，不推断失败或直接改配置。
- 刷新时打开着的旧设置草稿会在保存时提示重新打开，保留草稿供复制，避免它把新词库覆盖回旧快照。

更新仅供后续录制使用。历史转写不会自动改变；需要重转写时另按用户明确要求处理。新建预设的默认内置词库仍按应用启动时读取，更新该默认文件后，下次启动读取新版；本接口仅修改所指定的现有预设。
