# lecture-to-md

> 视频 / 文字稿 / 课件 → 中文 **Markdown** 课堂笔记（与上游 `lecture-to-notes` 的 LaTeX/PDF 流并行存在）。

对应 GitHub issue [#14](https://github.com/ysyecust/lecture-to-notes/issues/14)。本 skill 包按上游维护者意见作为**子 skill** 合入，目录 `skills/lecture-to-md/` 下分两层：

```text
skills/lecture-to-md/
├── SKILL.md                 ← 父 skill：笔记生成主流程（Phase 0–7）
├── agents/openai.yaml
├── assets/notes-prompt.md   ← 写作规范（子代理也读这个）
├── references/
│   ├── splitting.md             ← >30min 长课程切分规范
│   ├── subagent-workflow.md     ← 子代理派发与汇总
│   └── structure-reorder.md     ← Phase 6 标题重排
├── scripts/
│   ├── clean_subs.py            ← YouTube 自动字幕去重
│   └── correct_srt.py           ← 词典级同音字修正
│
├── local-asr/                ← 默认 ASR 子 skill（sherpa-onnx X-ASR，已在 macOS Apple Silicon + Linux ARM64 + Windows 验证）
│   ├── SKILL.md
│   ├── agents/openai.yaml
│   ├── references/models.md
│   ├── scripts/
│   │   ├── common.py            ← ffmpeg/ffmpeg 探测与抽音频
│   │   ├── transcribe.py        ← 统一入口（CLI）
│   │   ├── asr_x.py             ← sherpa-onnx X-ASR 推理后端
│   │   ├── setup.sh             ← macOS / Linux 一键安装
│   │   └── setup.ps1            ← Windows PowerShell 一键安装
│   └── .gitignore
│
└── volcengine-asr/           ← 备用 ASR 子 skill（火山引擎豆包 BigASR，云端）
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/api-modes.md
    ├── .secret.example         ← 凭据示例（真实凭据走 .secret，已 gitignore）
    ├── requirements.txt        ← tos SDK（仅异步模式需要）
    └── scripts/
        ├── asr_common.py
        ├── turbo_transcribe.py     ← BigASR 1.0 Turbo（同步，Base64）
        ├── upload_submit.py        ← TOS 上传 + 异步任务提交
        ├── poll_transcript.py      ← 轮询异步任务
        └── test_scripts.py         ← 离线集成测试
```

## 与上游 `lecture-to-notes` 的关系

|       | `lecture-to-notes/`（上游） | `lecture-to-md/`（本包）        |
| ----- | --------------------- | ------------------------- |
| 输出    | `.tex` + PDF             | `notes.md` + 图片              |
| 抽帧密度 | 每 15s（按章节）              | 严格每 5s                     |
| 配图    | contact sheet + 人工       | 多模态按 `###` 自动选（课件 > 视频帧） |
| 默认 ASR | Whisper                | **sherpa-onnx X-ASR**（本地；已在 macOS Apple Silicon + Linux ARM64 + Windows 端到端验证） |
| 编译    | xelatex                | 无                          |

**两者完全独立**——本包不修改也不依赖上游 `lecture-to-notes/` 的脚本、模板、`scripts/` 目录；上游用户按需把 `lecture-to-md/` 拷到 `~/.codex/skills/` 或 `~/.claude/skills/` 即可启用。

## 默认 ASR：`local-asr/`（sherpa-onnx X-ASR）

- **模型**：[sherpa-onnx X-ASR](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2)（Zipformer transducer，int8 量化，中英双语带标点，约 200 MB）。
- **后端**：`sherpa-onnx`（纯 Python 推理，路径跨平台齐备；Windows 用 `setup.ps1` 已在 PowerShell 5.1 实测）。
- **核显支持**：macOS Apple Silicon 自动用 CoreML（coreml EP 不可用时 fallback CPU）；Linux NVIDIA 自动用 CUDA；其它默认 CPU。
- **默认**不要切到 Qwen。Qwen 链路仅 macOS 可用且实测准确率不如 X-ASR。

首次跑前先装环境：

```bash
cd skills/lecture-to-md/local-asr
bash scripts/setup.sh          # macOS / Linux
# 或 Windows PowerShell：scripts\setup.ps1
```

使用：

```bash
python3 scripts/transcribe.py /path/to/课程.mp4 --timestamps   # 转写 + 出 srt
```

详见 [`local-asr/SKILL.md`](local-asr/SKILL.md)。

## 备用 ASR：`volcengine-asr/`（火山引擎豆包）

需要 `VOLCENGINE_ASR_APP_ID` / `VOLCENGINE_ASR_ACCESS_TOKEN`（可选 TOS 凭据）。首次跑前：

```bash
cd skills/lecture-to-md/volcengine-asr
cp .secret.example .secret && chmod 600 .secret
# 编辑 .secret 填入真实凭据
```

使用 BigASR 1.0 Turbo（同步，最快）：

```bash
python3 scripts/turbo_transcribe.py /path/to/课程.mp4
```

异步 1.0/2.0 见 [`volcengine-asr/SKILL.md`](volcengine-asr/SKILL.md)。

## 快速启用

### 作为 Codex / Claude Code Skill

```bash
# 整包拷到 skills 目录
cp -R skills/lecture-to-md ~/.codex/skills/
# 或
cp -R skills/lecture-to-md ~/.claude/skills/
```

父 SKILL 的 `description` 会同时把 `lecture-to-md` 注册为顶层 skill；子 skill 的 description（含 sherpa-onnx / 火山引擎关键词）也会自动被匹配。

### 独立调用子 skill

```bash
cd skills/lecture-to-md/local-asr
bash scripts/setup.sh
python3 scripts/transcribe.py "/path/to/课程.mp4" --timestamps
```

## License

GPL-3.0 — 与上游项目保持一致。
