# Think Aloud Recorder

Windows 游戏体验记录器：录下游戏画面与口述，再到 Obsidian 回看、校对和整理观察。

## 使用

1. 完整解压 Windows x64 便携包，运行 `ExperienceRecorder.exe`。
2. 新建录制预设，建议用游戏或项目命名；在向导选择录制窗口或显示器、麦克风、画质、转写方式与保存位置。每套预设可使用不同资料库。
3. 保存一次，以后选择预设并点击 **开始录制**。选定窗口未打开、麦克风不可用、模型或密钥缺失时，按钮会禁用并显示具体原因。
4. 结束录制后，在场次列表打开 Obsidian 回看。场次详情提供独立网页后备、导出与重试。

需要 Windows 10/11 x64 和 [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)。软件不安装全局 Python、不改变系统代理。

## 转写方式

- **仅录制，稍后整理**：不需要模型或云端密钥，原始资料保留为待整理。
- **本地 Whisper large-v3**：在本机处理；模型约 3.09 GB，独立于软件包。向导可下载固定版本，或校验并直接引用已有模型文件夹，不复制权重。默认使用 CPU。
- **Qwen 云端转写**：使用自己的百炼 API Key。选择云端转写后，只将麦克风独立音轨上传到服务提供方，可能产生服务费用。密钥使用当前 Windows 用户的 DPAPI 加密保存，不进入场次导出。

模型清单固定上游版本和每个文件的 SHA256。支持暂停与断点续传；文件校验通过后才能用于转写。软件升级不要求重新下载模型。换到新软件目录时，可重新引用原模型目录和资料库。

向导中的「语言与词库」支持多选 TXT / 搜狗 SCEL 词库，展示文件名与词数，可逐项移除，重复词条自动合并。提供[搜狗官方词库下载入口](https://pinyin.sogou.com/dict/)，也可展开「手动补充词条」。词库内容随各自预设保存，原文件移动后仍可使用；需要更新内容时重新选择文件。

## 回看与资料

[Obsidian](https://obsidian.md/download) 单独安装，在向导中指定程序位置或使用自动检测。资料库附带 Media Transcript 和 Experience Opener 插件；首次打开时按 Obsidian 提示信任自己的资料库并启用插件。记录器收到插件确认后才报告回看成功；未收到确认时提供网页后备。

每个场次独立保存原始 MKV、回看 MP4、口述音频、带词级时间戳的逐字稿和 `复盘.md`。重新转写保留旧稿与手写笔记。导出包含所选场次和受控的回看插件模板，不复制资料库中的其他插件配置。

录制保存两条音轨：第 1 轨用于游戏声音与麦克风混合回放；第 2 轨仅包含选定麦克风，是唯一转写输入。扬声器传到麦克风的环境声音仍属于实际麦克风输入，音轨分离本身不会消除它。

## 开发与构建

核心为 Python + OBS WebSocket；界面为本地 HTML/CSS/JavaScript + pywebview/WebView2；耗时转写在独立进程运行。无需前端打包服务或远程网页。

```powershell
runtime/python.exe -m unittest discover -s tests
runtime/python.exe app.py
runtime/python.exe scripts/build_portable.py --outdir dist/candidate --candidate
```

准备运行环境、构建范围与依赖源码材料见 [构建说明](docs/build.md)。`--candidate` 生成供本地验证的包；公开二进制发行需满足构建器检查的第三方源码条件。源码许可证不自动涵盖第三方二进制。

实现约定见 [AGENTS.md](AGENTS.md)，体验要求见 [recorder-experience.md](docs/recorder-experience.md)，桌面接口见 [bridge-contract.md](docs/bridge-contract.md)。运行数据、密钥、模型与个人词库不进入 Git。

## 许可证

原创代码采用 [MIT](LICENSE)。第三方组件保留各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。不分发 Obsidian 程序本体。
