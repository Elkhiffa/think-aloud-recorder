# 交接：在家里这台电脑上用上 0.9.0（2026-10-23）

给家里电脑上的 agent。用户在公司电脑上已经发布了 0.9.0，并把公司的资料库处理好了。这份说明让家里这台电脑也达到同样的状态。按顺序做，每一步完成后向用户汇报“做了什么、怎么核对的、结果是什么”。遇到和这里描述不符的情况，先停下问用户，不要自行变通。

## 先读

- 仓库根目录的 `AGENTS.md`：红线和测试纪律。
- 本文提到的命令都在仓库根目录、用仓库自己的开发 runtime（`runtime\python.exe`）运行。命令用 PowerShell 写法。

## 规矩

- **真实资料库**：只做第 4、5 步写明的写入，也就是界面目录里加 `layout`、各场的 `context-track.json`。其他文件只读。
- **不 push、不 merge、不改发布脚本**。这些需要用户明确授权。
- 不读 `analysis` 目录；不输出密钥或完整配置。
- 家里的路径和公司不同，以实际为准。不知道就问用户，或者只读安装目录里 `app\config.json` 的资料库路径字段。

## 0. 先弄清三个路径，告诉用户并请他确认

1. Think Aloud 安装目录：有 `Think Aloud.exe` 的文件夹。
2. 源码目录：这个仓库的 checkout 或 worktree，里面有 `runtime\python.exe`。
3. 资料库里燕云的文件夹：形如 `<资料库>\燕云十六声`，下面有 `场次\` 和 `game-assets\燕云十六声\catalog.json`。

## 1. 把软件更新到 0.9.0（录制只需要这一步）

- 让用户在 Think Aloud 里点：设置 → 通用 →「版本与更新」→ 检查更新 → 下载 → 退出并更新。
  - 0.8.1 只下载改动的文件，约 58 MB；更早的版本会下载完整包。
  - 不要替用户点安装，也不要直接改安装目录。
- **核对**：安装目录 `app\portable.json` 的 `version` 是 `0.9.0`，`source_commit` 以 `9414de6` 开头。
- 这一版录制相关的变化：
  - 切到游戏时，录制块保持上次检查的结果；切回来时在后台重新检查；
  - 整个录制块都能点。

  用户如果问“为什么不再显示录制条件尚未满足”，就是这个原因。

## 2. 更新源码

- 先运行 `git branch --show-current` 看当前分支。在 main 上就 `git pull`；在别的分支上，先问用户要不要切到 main，或者合并 main。
- **核对**：
  - `git log --oneline -1` 里能看到 `Merge pull request` 并包含 `layout-scripts`；
  - `scripts\apply_layout.py`、`scripts\rebuild_context_tracks.py`、`docs\layouts\燕云十六声.json` 都存在。

## 3. 确认开发 runtime 能做文字识别

```powershell
.\runtime\python.exe -B -c "import rapidocr_onnxruntime, cv2; print('ok', cv2.__version__)"
```

- 打印出 `ok` 才能继续。
- 报缺模块就停下，告诉用户缺哪个。不要全局安装任何东西；在仓库自己的 `runtime` 里补装之前先问用户。
- 注意：`runtime\python312._pth` 里有 `..`，所以它导入的是 runtime 所在目录的上一级代码。确认 `runtime` 就在这个源码目录里，不是从别的 worktree 借来的。

## 4. 给资料库启用界面路径识别

先只检查，不写入：

```powershell
.\runtime\python.exe -B -X utf8 scripts\apply_layout.py "<资料库>\燕云十六声" --dry-run
```

- 应看到 `"replaced": false`（以前没有规则）。如果是 `"unchanged": true`，说明已经加过，这一步可以跳过。
- 再请用户关掉 Think Aloud，然后正式写入：

```powershell
.\runtime\python.exe -B -X utf8 scripts\apply_layout.py "<资料库>\燕云十六声"
```

- **核对**：
  - 输出里有 `backup`（旧目录留在 `catalog.json` 旁边）；
  - 运行 `.\runtime\python.exe -B -X utf8 agent_cli.py catalog-validate "<资料库>\燕云十六声" "燕云十六声"`，返回 `"ok": true`。

## 5. 重建已有场次的情景轨道（耗时，建议夜里跑）

```powershell
.\runtime\python.exe -B -X utf8 scripts\rebuild_context_tracks.py "<资料库>\燕云十六声"
```

- 两场并行。旧轨道没有字框角点，会整段重跑文字识别：一小时录像约 20–60 分钟，CPU 占用高。
- 中断了照原命令重跑即可，已经按当前规则建好的场次会跳过。每场一个日志，在源码目录的 `work\context-rebuild\` 里。
- **核对**：每行都是 `ok` 或 `skipped`，没有 `failed`。有 `failed` 就看对应日志，把错误原样告诉用户，不要改代码绕过。
- 新录的场次不用单独处理：之后整理时建情景轨道，会自动带上页签和标题信息。

## 6. 安装或更新两份分析 skill

- 按 `docs\agent-integration.md` 里“Skill 安装与更新”一节做：把源码里的 `skills\think-aloud-judgments` 和 `skills\think-aloud-insight` 两个目录，复制到这台电脑用到的 agent 技能目录。
  - Claude Code：`%USERPROFILE%\.claude\skills`
  - Codex：`%USERPROFILE%\.codex\skills`
- 目录里已有同名文件夹时，先备份到技能目录之外，再比较、再替换，不要直接覆盖。
- 如果装过旧的 `think-aloud-preprocess`，问用户要不要移走。它已经停用。
- **核对**：复制后两边逐文件 SHA-256 一致，向用户报告。

## 7. 转写修正：知道就好，这一步不用做

- 公司那台电脑的资料库根目录有 `transcript-corrections.json`：确认过的转写修正，包括“走交 / 左交 / 左焦 → 走焦”等全库规则和逐句修正。
- 家里的资料库如果是另一份，就没有这个文件。不要从别处复制过来，那些修正绑定的是公司库里的场次。
- 以后在家整理场次时，按 skill 里“转写修正”一节，用 `transcript-fix-propose` 提议，交用户确认。

## 汇报

全部做完后，交给用户一张表，每一步一行：做了什么、核对命令和结果、有没有异常。
