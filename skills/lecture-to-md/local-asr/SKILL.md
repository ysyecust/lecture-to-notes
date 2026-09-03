---
name: local-asr
description: 把本地长视频/音频转写成文字稿 + 可选字幕，纯本地（不上传云端），用 sherpa-onnx X-ASR Zipformer transducer 模型（int8 量化、中英双语、自动标点）；跨平台支持 macOS / Linux / Windows；对核显支持较好（macOS 自动走 CoreML，Linux 自动检测 CUDA）。Use when the user wants 音视频转文字、课程录转录、转录稿、ASR、speech to text、transcribe a lecture video、给转写稿加时间戳、生成字幕 srt，especially for 一两个小时的课程视频 → 文字稿/字幕 → 再整理笔记 的场景。Trigger words include 转写、转录、转文字、语音识别、asr、transcribe、时间戳、字幕、srt。本 skill 是 `lecture-to-md` 的默认 ASR 后端；默认不要换成 Qwen（Qwen 链路只在 macOS 可用，且实测准确率不如 X-ASR）。
---

# Local ASR Transcribe（`lecture-to-md` 子 skill，sherpa-onnx X-ASR）

在本地（macOS / Linux / Windows）把**长课程视频/音频**转成文字稿，可选补时间戳出字幕。单一后端，中英文通用：

```text
中文/英文 ──→ sherpa-onnx OfflineRecognizer (X-ASR Zipformer transducer, int8) ──→ 文本 + token 级时间戳 ──→ txt / md / srt / vtt
```

**首选这个 skill 而非 `volcengine-asr/`**：纯本地不上传、对核显/集显支持较好（Apple Silicon 自动用 CoreML 加速，Linux 上自动检测 CUDA）、int8 量化体积小、首包延迟低。

前提只要：`ffmpeg` / `ffprobe`、`python3`、`sherpa-onnx` pip 包、X-ASR 模型权重。**首次跑 `bash scripts/setup.sh` 一键完成**（macOS / Linux；Windows 用户见后文「Windows 设置」一节）。

## 关键约定

1. **语言由用户指定；没说就默认中文**（`--lang zh`），也支持 `en` / `auto`。
2. **输出目录默认与源文件同目录**，文件名取源文件同名干：
   `课程.mp4` → `课程.txt` / `课程.md`（纯文本）、`课程.srt`（字幕）。
3. **模型不吃视频**。入口脚本统一先用 ffmpeg 抽成 16 kHz 单声道 wav 再送模型，
   视频、m4a、mp3、wav 都一样处理，不用手工转码。
4. 已存在同名输出时**不覆盖**，需显式加 `--overwrite`。
5. **sherpa-onnx X-ASR 默认产出 token 级时间戳**（Zipformer transducer 自带对齐能力，无需独立 ForcedAligner 模型），所以 `--timestamps` 不带来额外权重、也不多花一倍时间。要字幕就加 `--timestamps`，否则只出 txt/md。
6. **已有稿子想补时间戳**：直接对原音频跑一次 `transcribe.py --timestamps --formats srt,vtt`，拿生成的 srt 作为字幕时间轴，文本再用原稿覆盖（sherpa-onnx 不需要独立强制对齐模型）。

## 快速使用

```bash
cd "<skill 目录>"    # 即 skills/lecture-to-md/local-asr

# 中文（默认，纯文本 txt + md）
python3 scripts/transcribe.py "/path/to/课程录像.mp4"

# 英文
python3 scripts/transcribe.py "/path/to/lecture.mp4" --lang en

# 指定输出目录 + 只出 txt
python3 scripts/transcribe.py "lecture.mov" -o ./out --formats txt

# 转写 + 出 srt/vtt 字幕（带 token 级时间戳）
python3 scripts/transcribe.py "lecture.mov" --lang en --timestamps

# 输出 JSON（含 token + 时间戳，便于二次处理）
python3 scripts/transcribe.py "lecture.mov" --timestamps --formats json
```

首次使用先装环境（约下载 sherpa-onnx 包 + X-ASR 模型 ~200 MB，耐心等）：

```bash
bash scripts/setup.sh
```

## Windows 设置

`setup.sh` 是 bash 脚本，**Git Bash / WSL** 下可直接跑。原生 PowerShell 用户：

```powershell
# 安装 sherpa-onnx
py -m pip install -U sherpa-onnx

# 下载 X-ASR 模型（解压到 %USERPROFILE%\.cache\sherpa-onnx\...）
$dir = "$env:USERPROFILE\.cache\sherpa-onnx-models"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$url = "https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2"
$tar = "$dir\x-asr.tar.bz2"
Invoke-WebRequest -Uri $url -OutFile $tar
tar -xjvf $tar -C $dir
Remove-Item $tar
```

随后跑同样的 `python3 scripts/transcribe.py ...` 命令。

## 参数

### transcribe.py（转写，可选补时间戳）

| 参数 | 默认 | 说明 |
|---|---|---|
| `input` | — | 视频或音频路径（位置参数） |
| `--lang` | `zh` | `zh` / `en` / `auto`；也接受 `中文`/`英文`/`chinese`/`english` |
| `--output-dir`, `-o` | 源文件所在目录 | 输出目录 |
| `--model` | `~/.cache/sherpa-onnx-models/sherpa-onnx-x-asr-...-2026-06-03/` | 模型目录 |
| `--formats` | `txt,md` | 逗号分隔，可选 `txt,md,json,srt,vtt`（后两个要配 `--timestamps`） |
| `--timestamps` | 关 | 保留 token 时间戳，产出 srt/vtt（**X-ASR 默认产出 token 时间戳**，此开关只是把时间戳写入字幕） |
| `--provider` | 平台自动 | `cpu` / `coreml`（macOS）/ `cuda`（NVIDIA）。**默认 macOS Apple Silicon 用 coreml；其他平台用 cpu** |
| `--num-threads` | `3` | sherpa-onnx 推理线程数；CPU 时一般与物理核数接近 |
| `--context` | — | 术语/热词提示，可传 `.txt` 路径 |
| `--max-chunk-sec` | `600` | 单次解码最大音频秒数；超大文件可调小以省内存 |
| `--overwrite` | 关 | 允许覆盖已有输出 |
| `--keep-audio` | 关 | 保留中间 16k wav（调试用） |

环境变量：`ASR_PROVIDER`（覆盖 `--provider`）、`ASR_MODEL_DIR`（覆盖 `--model`）。

## 平台与加速（"对核显支持较友好"）

| 平台       | 默认 provider | 加速原理                                                | 备注                          |
| -------- | ----------- | ------------------------------------------------ | --------------------------- |
| macOS Apple Silicon（M1+） | `coreml`    | X-ASR Zipformer 走 Apple Neural Engine / 统一 GPU    | 强烈推荐；M 系列实测 ~3× 实时       |
| macOS Intel          | `cpu`       | int8 + 多线程                                       | ~1× 实时                     |
| Linux NVIDIA GPU     | `cuda`（检测到时）| ONNX Runtime CUDA EP                            | 需 `pip install onnxruntime-gpu` |
| Linux 其它            | `cpu`       | int8 + 多线程                                       | ~0.5–1× 实时                  |
| Windows              | `cpu`       | int8 + 多线程                                       | WSL / Git Bash 下脚本可用        |

**核显**指 Apple Silicon（M1/M2/M3/M4）的统一 GPU/ANE —— 这是 X-ASR 在 macOS 上跑得最快、最省电的路径。NVIDIA 独显上也可走 CUDA，但需要装 `onnxruntime-gpu`（pip 装 sherpa-onnx 自带的是 CPU 路径）。

## 模型选择

X-ASR 系列 sherpa-onnx 官方推出的中文/英文双语 Zipformer transducer 模型，**默认使用 int8 量化版本**（约 200 MB，准确率与 float 几乎一致，CPU 上更快）。

| 场景 | 模型 | URL |
|---|---|---|
| **默认（int8，中英双语带标点）** | `sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03` | https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2 |
| Float 版（更大、稍慢） | `sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-fp16-...` | 同一 release 页面 |

`--model` 可指向任意 sherpa-onnx Zipformer transducer 目录（只要里面有 `encoder-*.onnx` / `decoder-*.onnx` / `joiner-*.onnx` / `tokens.txt`）。

## 与 lecture-to-md 的衔接

本 skill 是 `lecture-to-md` 的**默认 ASR 后端**，对应 issue #14 提出的 Markdown 笔记流。产出 `.txt` / `.md` / `.srt` 后交给 `lecture-to-md` 父 skill 走常规笔记生成流程；带 srt 时配图可做时间溯源（帧 ↔ 字幕 ↔ 画面三方校验）。

## 实现笔记

`scripts/` 下的 Python 文件是有意的分层：

- **`transcribe.py`** —— 转写入口，只依赖标准库 + ffmpeg。负责 CLI 参数、音频预处理、调度、写出 txt/md/json/srt/vtt。
- **`asr_x.py`** —— sherpa-onnx X-ASR 推理后端，纯 Python（依赖 `sherpa-onnx`）。通过 `--out` 指定的 JSON 文件与 orchestrator 通信；只产文本也可带 token + 时间戳。
- **`common.py`** —— 共用工具（ffprobe/ffmpeg 探测、抽音频、写出文本、跨平台 PATH 兜底）。`transcribe.py` 直接 `import`，不传 subprocess。

换模型/换 provider 时只需替换 `asr_x.py` 内的加载逻辑（`load_model`、`run_inference`），`transcribe.py` 和 `common.py` 不动。

## 常见故障

| 现象 | 原因 / 处理 |
|---|---|
| `ModuleNotFoundError: sherpa_onnx` | 先跑 `bash scripts/setup.sh`（Windows 用 PowerShell 段） |
| `Model directory not found` | 模型未下载，重跑 `setup.sh` 或 `--model <dir>` 指向已有目录 |
| HuggingFace 报 401（**不会发生**） | sherpa-onnx 模型从 GitHub release 下，不走 HF |
| 对齐权重下载中断 | 国内直连 GitHub release 偶发断，用镜像：`GITHUB_PROXY=https://gh-proxy.com` 重跑 `setup.sh`（脚本识别此变量） |
| macOS 上 `coreml` provider 报 not found | X-ASR 当前 int8 量化版官方未带 CoreML EP —— 在 Apple Silicon 上脚本自动 fallback 到 `cpu`；后续 release 会带上 CoreML |
| 内存不足 | `--num-threads` 调小（如 `2`）；或换更小模型（找同系列更早日期的 release） |
| 术语错（同音字） | 加 `--context` 传入领域词表（每行一个词，限制 200 字内） |
| 口语词多（嗯/呃/这个） | X-ASR 输出偏书面，无明显口语化残留 |
| 时间戳整体偏早或偏晚 | X-ASR 自带 token 对齐，偏移通常 < 0.5s；若明显偏，检查音频轨是否与输入一致 |

## Operating rules

- X-ASR int8 在 M3 / M4 上约 **3× 实时**（CoreML），纯 CPU 约 1× 实时。
  **长音频务必后台运行**并给用户进度提示，不要干等。
- 输出完成后，报告产出的 `.txt` / `.md` / `.srt` 绝对路径。
- 不要主动切到 Qwen / Whisper 等其它后端 —— 用户在本 skill 上明确要求 X-ASR，且实测准确率较高。
- 要字幕才加 `--timestamps`（X-ASR 默认就产 token 时间戳；不额外加载权重、不显著增加耗时）。
- 不要硬编码 GitHub release URL —— 升级模型时统一改 `setup.sh` 顶部的 `X_ASR_RELEASE_URL`。