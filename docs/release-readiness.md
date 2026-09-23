# GitHub Release 准备状态

核查日期：2026-09-23。目标仓库：`Elkhiffa/think-aloud-recorder`。

## 当前可以发布什么

原创源码已经采用 MIT，可以继续同步和维护。本轮固定来源的依赖材料已经收齐，正在准备正式命名的 Windows ZIP 三件套。它们尚未对外发布；最终归档、升级回滚和发布前预检以对应产物的报告为准。GitHub prerelease、改文件名或修改布尔标记不能补齐缺少的材料。

GitHub `main` 目前为 `208bee6489fd5ebb783e9f46745eb4a50b0ac447`，是最新功能的祖先。录制与回看最新功能在开发分支，更新功能和本轮发布准备将一并通过独立分支及 Pull Request 提供。不要直接从旧 `main` 创建软件版本标签。

## 首次发布流程

1. 合入已验证的源码，确定版本和具体提交。预览版使用 `v0.6.0-preview.N`，版本号每次递增；标签对应的提交必须包含包中实际应用代码。
2. 补齐并审核以下依赖材料，生成新的 source manifest，不覆盖旧证据。公开构建继续要求 `redistribution_ready: true` 且没有未解决的 `gaps`。
3. 用干净 staging 构建正式命名的三件套：`ExperienceRecorder-{version}-windows-x64.zip`、同前缀的 `-dependency-sources.zip`、`-SHA256SUMS.txt`。模型单独下载；个人数据不打包。
4. 运行 `scripts/prepare_release.py`，核对版本、目标提交、三件套、包内外清单和应用更新协议。预检失败只生成报告，不能得到可误发布的上传清单。成功也仅表示协议检查通过，不能代替真实运行验收。
5. 完成新目录原生启动、合成录制、独立麦克风音轨、回看及原目录更新回归。检查说明中的限制仍然准确后，准备 GitHub draft Release。
6. 三件套全部上传后，再次核对远端尺寸和 SHA256；确认对外发布后再发布 draft。发布后以较旧版本执行真实更新，不用同版本的“已是最新版”代替附件验收。

这一版采用手动准备和草稿流程，不引入 GitHub Actions 自动发布，不需要把个人 API Key 放进仓库或新增 CI 密钥。GitHub Release 的请求中固定 `draft: true`，预览标记由版本号推导，提交使用完整 SHA。[GitHub Release API](https://docs.github.com/en/rest/releases/releases#create-a-release)

## 已完成的依赖核对与剩余材料

已核对现有 dependency source manifest 的 9 项文件大小和 SHA256，清单摘要为 `050b4770f76f9824f5dfff005e348acdb483e662435e771c157e09cf91b713ff`。这证明列出的材料存在且未变，不证明清单覆盖了所有随包组件。

| 组件 | 当前已取得 | 尚需处理 |
| --- | --- | --- |
| 原 Gyan FFmpeg CLI | 已批准替换，并从新包排除 | 旧安装中的非活动 EXE 按更新器保留策略保留，不会再被应用选择 |
| 替换 CLI：OBS-project FFmpeg n8.1.2 | 官方 archive 和 12 文件闭包已校验；18 项固定源码输入、1 项 recipe 归档及 14 个补丁已核对 | 独立目录中另放已有运行环境的 3 个 VC DLL，不覆盖 OBS/PyAV 的库 |
| OBS 32.2.2 | 87 个 native 文件与官方 ZIP 一致；14 个 obs-deps DLL 仅有 PE 签名元数据差异 | Qtbase/Qtimageformats/Qtsvg、libdatachannel 及实际构建子模块已归档；w32-pthreads 在官方 OBS 源码内；CEF 原始 credits 已从实际随包资源提取 |
| PyAV 18.1.0 | 74 个 native 文件与官方 wheel 一致；固定 vendor recipe 的 14 项源码全部匹配摘要 | 保留 x264/x265 原始许可与源码；FFmpeg configure 中的许可列表补丁不改变库本身的条款 |
| CTranslate2 与 Intel/NVIDIA 组件 | 官方 wheel/DLL 字节绑定；取得 18 份原样许可与嵌套声明 | 静态 oneMKL 用配方、二进制日期标记、同版本 header 交叉绑定，不声称逐对象重编译验证 |

Gyan 7.1 的 [Release](https://github.com/GyanD/codexffmpeg/releases/tag/7.1) 只提供二进制附件和 FFmpeg core commit；[维护者关于构建脚本的回复](https://github.com/GyanD/codexffmpeg/issues/25#issuecomment-896110133) 指向通用 MABS，未给出该二进制的固定 recipe。当前 MABS 版本不能冒充这份历史构建的对应材料。

OBS 可沿 [32.2.2 固定依赖](https://raw.githubusercontent.com/obsproject/obs-studio/32.2.2/CMakePresets.json)、[obs-deps 2026-07-15](https://github.com/obsproject/obs-deps/releases/tag/2026-07-15) 和 [FFmpeg recipe](https://raw.githubusercontent.com/obsproject/obs-deps/2026-07-15/deps.ffmpeg/99-ffmpeg.ps1) 继续核对。PyAV 可沿 [v18.1.0 vendor pin](https://raw.githubusercontent.com/PyAV-Org/PyAV/v18.1.0/scripts/ffmpeg-latest.json) 和 [vendor 8.1.2-1](https://github.com/PyAV-Org/pyav-ffmpeg/releases/tag/8.1.2-1) 继续核对。其 [FFmpeg patch](https://raw.githubusercontent.com/PyAV-Org/pyav-ffmpeg/8.1.2-1/patches/ffmpeg.patch) 改动了 GPL 检查列表，因此库自报的 license 字符串不能单独作为实际许可结论。

本项目要求 companion sources ZIP 是发布流程约定。所需对应源码和构建控制脚本应以实际组件条款判断，不要求字节级可复现，也不能把源码清单中的布尔值当成独立法律审查。

## 已批准并实施的二进制替换

用户已确认保留 FFmpeg 命令行接口并替换为可追溯构建。应用现在从 `runtime/Lib/think_aloud_media` 选择固定 CLI；打包安装缺少该组件时不会偷偷使用环境变量、PATH 或 imageio 的其他 EXE。源码 Git checkout 可继续使用开发依赖。

已在旧 CLI、新 CLI，以及应用实际选中新 CLI 的 staging 中通过 5 项真实合成媒体检查：损坏录像恢复保留全部流、视频与混音轨 remux、仅麦克风轨提取及起始静音、无声口述整理回看、跨越 600/1200 秒边界的切段样本一致。没有调用录音设备、云端转写或模型推理。实际 WebView2 的 8 项界面/回看检查和 staging EXE 自检通过；旧版升级与最终归档检查另有报告，不能用 staging 通过代替。

发布预检把必需应用文件及包内所有已跟踪资产与目标提交绑定，并拒绝未提交的根目录 Python、UI 和 scripts 文件。`scripts/runtime-seed.json` 另固定已验证 preview.4 seed 的 6,979 个文件；构建和预检都核对运行环境实际文件集与字节，防止只改包内自校验清单就掩盖依赖变化。这证明接受的 seed 一致性，不等于上游签名或源到二进制可复现证明。

当前工作尚未创建或发布 GitHub Release。软件包和源码包各自的清单必须继续如实保留未解决项；没有用 prerelease 标志、改文件名或布尔值绕过材料检查。

## 材料审阅边界

此次已知材料获取缺口均已关闭。companion archive 保留原始许可、源文件、固定构建脚本/补丁、逐文件来源比对及限定说明。GCC/winpthread 的历史 MSYS 包修订未完全固定，但已提供实际组件对应的原始许可/例外声明；不把宽松许可组件的这个来源限定伪装成精确字节映射。PyAV x264/x265 的 GPL 材料原样保留，不把其 configure patch 当成替代授权。

正式发布还需发行者遵守归档的 NVIDIA、Intel、Microsoft 条件，并复核 release notes 和三件套远端摘要。材料获取和本地预检没有代替发行者接受协议，也没有执行公开发布。
