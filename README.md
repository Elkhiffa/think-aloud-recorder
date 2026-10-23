<div align="center">

<img alt="Think Aloud" src="ui/brand.svg" width="96" height="96">

# Think Aloud Recorder

A think-aloud recorder for game UX research on Windows: record gameplay with your spoken thoughts, review footage and transcript side by side, and hand each session to an AI agent for analysis.

English | [简体中文](https://github.com/Elkhiffa/think-aloud-recorder/blob/main/README.zh-CN.md)

[Download](https://github.com/Elkhiffa/think-aloud-recorder/releases/latest) · [Install the analysis skills](docs/agent-integration.md#skill-安装与更新) · [Changes in 0.10.0](docs/changes-2026-10-24.md)

</div>

## What it does

- **Record**: one button records the game window (or a whole display) through a bundled OBS, with your microphone on its own audio track. A short chime confirms that recording has really started.
- **Transcribe**: the microphone track is transcribed locally with Whisper large-v3, or in the cloud with Qwen using your own Bailian API key. Nothing is uploaded unless you choose the cloud option.
- **Review**: each session opens in its own review window: the video, a word-level transcript that follows playback, and, if enabled, a timeline of keyboard, mouse and gamepad input.
- **Organize**: the desk window lists every session of a game with its state and problem mix, and shows the insight reports an agent writes into the library, with every quote linked back to the moment it was said.

The recorder has no built-in AI. Analysis is done by an external agent (Codex or Claude) using the two skills in this repository; the recorder keeps the raw material and checks the citations in the reports.

## Getting started

1. Download the latest Windows x64 package from [Releases](https://github.com/Elkhiffa/think-aloud-recorder/releases/latest), extract the whole folder and run `Think Aloud.exe`.
2. The first-run setup walks through how to think aloud, the microphone and transcription method, the game and its window, and where to save. Each game gets its own library folder.
3. Pick the game at the top of the main window and press **Record**. If something is missing (game window, microphone, model or key), the button is disabled and the reason is shown next to it.
4. After you stop, the main window shows the latest session as saved, transcribing, and then ready to organize.

Requires Windows 10/11 x64 and the [Microsoft Edge WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/). The recorder does not install a global Python or change system proxy settings. The interface is in Chinese.

## After recording: the analysis skills

Two skills in [`skills/`](skills) turn sessions into analysis:

- [`think-aloud-judgments`](skills/think-aloud-judgments): organizes one session into traceable judgment instances (when it was said, which moment it refers to, which screen, and the evidence).
- [`think-aloud-insight`](skills/think-aloud-insight): works across sessions. It files instances under the issue tree and, from an analysis brief you confirm, writes an insight report in which every claim cites its evidence.

**Install them once** from the app: the first-run step **准备分析** (prepare analysis) downloads the text recognition component and installs both skills in one click, and can create a 燕云十六声 project with its interface rules ready. On a computer already set up, use Settings → 通用 → 记录方法 → **安装分析 skill**, which copies both skills, which ship with the app, into the skill folders of the agents you have (`%USERPROFILE%\.claude\skills` for Claude Code, `%USERPROFILE%\.codex\skills` for Codex), backing up any older copy first. Click it again after an app update to sync them. Manual steps are in [Skill install and update](docs/agent-integration.md#skill-安装与更新).

Context tracks and interface path recognition need local text recognition: download the **识别组件** (about 65 MB, pinned packages from files.pythonhosted.org) in Settings → 通用 once; it is kept across updates.

When a session is ready, click **复制整理指令** (copy the organize prompt) in the main window or the desk, and paste it to your agent. The recorder never starts an agent, schedules a task or scans the library on its own.

## Updates

The app checks GitHub for a new release once after it opens and shows a dot on the settings button when one is available. Download and verification run in the background, and the update is installed only when you click **退出并更新** (quit and update), never during a recording. Presets, library paths, keys, models and vocabularies are kept, and the previous version is backed up until the update succeeds. See [updates](docs/updates.md).

## Privacy

- Recordings, transcripts and analysis stay in your library folder on your computer.
- Cloud transcription uploads only the microphone track, and only when you choose it. The API key is encrypted with Windows DPAPI for the current user.
- The recorder never uploads anything silently.

## Building from source

The core is Python with OBS WebSocket; the interface is local HTML/CSS/JavaScript in pywebview/WebView2. No frontend build step or remote web pages.

```powershell
runtime/python.exe -m unittest discover -s tests
runtime/python.exe app.py
runtime/python.exe scripts/build_portable.py --outdir dist/candidate --candidate
```

See [build notes](docs/build.md) for the runtime and third-party sources, and [release readiness](docs/release-readiness.md) for publishing. Most documentation is in Chinese.

## License

Original code is under the [MIT License](LICENSE). Third-party components keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
