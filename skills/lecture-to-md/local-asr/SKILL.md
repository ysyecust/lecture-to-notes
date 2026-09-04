---
name: local-asr
description: 把本地长视频/音频转写成文字稿 + 可选字幕，纯本地（不上传云端），用 sherpa-onnx X-ASR Zipformer transducer 模型（int8 量化、中英双语、自动标点）。已在 macOS Apple Silicon（int8 + AMX，~100× 实时）、Linux ARM64（CPU，~32× 实时）与 Windows（PowerShell 5.1，CPU）端到端验证。使用 `$lecture-to-md` 默认 ASR 后端；默认不要换成 Qwen。
---

# Local ASR Transcribe（`lecture-to-md` 子 skill，sherpa-onnx X-ASR）

在本地（macOS Apple Silicon、Linux ARM64、Windows 均已端到端验证）把**长课程视频/音频**转成文字稿，可选补时间戳出字幕。单一后端，中英文通用：

```text
中文/英文 ──→ sherpa-onnx OfflineRecognizer (X-ASR Zipformer transducer, int8) ──→ 文本 + token 级时间戳 ──→ txt / md / srt / vtt
```


前提只要：`ffmpeg` / `ffprobe`、`python3`、`sherpa-onnx` pip 包、X-ASR 模型权重。**首次使用按平台看对应的 reference**：macOS / Linux 跑 `bash scripts/setup.sh` 一键完成；Windows 原生 PowerShell 用户跑 `.\scripts\setup.ps1`。详细步骤与故障排查见「[平台环境配置](#平台环境配置)」一节。

## 关键约定

1. **语言由用户指定；没说就默认中文**（`--lang zh`），也支持 `en` / `auto`。
2. **输出目录默认与源文件同目录**，文件名取源文件同名干：
   `课程.mp4` → `课程.txt` / `课程.md`；加 `--timestamps` 后再生成 `课程.srt` 或 `课程.vtt`。
3. **模型不吃视频**。入口脚本统一先用 ffmpeg 抽成 16 kHz 单声道 wav 再送模型，
   视频、m4a、mp3、wav 都一样处理，不用手工转码。
4. 已存在同名输出时**不覆盖**，需显式加 `--overwrite`。
5. **sherpa-onnx X-ASR 默认产出 token 级时间戳**（Zipformer transducer 自带对齐能力，无需独立 ForcedAligner 模型），所以 `--timestamps` 不带来额外权重、也不多花一倍时间。CLI 要字幕就加 `--timestamps`；skill 调用默认会加。
6. **调用本 skill 时默认加 `--timestamps`**，确保产出带时间轴的字幕；只有用户明确只要纯文本时才省略。
7. **已有稿子想补时间戳**：直接对原音频跑一次 `transcribe.py --timestamps --formats srt,vtt`，拿生成的 srt 作为字幕时间轴，文本再用原稿覆盖（sherpa-onnx 不需要独立强制对齐模型）。

## 快速使用

```bash
cd "<skill 目录>"    # 即 skills/lecture-to-md/local-asr

# 中文（默认，txt + md + srt）
python3 scripts/transcribe.py "/path/to/课程录像.mp4" --timestamps

# 英文
python3 scripts/transcribe.py "/path/to/lecture.mp4" --lang en --timestamps

# 指定输出目录 + 只出 txt
python3 scripts/transcribe.py "lecture.mov" -o ./out --formats txt

# 标准调用：转写 + 出 srt 字幕
python3 scripts/transcribe.py "lecture.mov" --lang en --timestamps

# 输出 JSON（含 token + 时间戳，便于二次处理）
python3 scripts/transcribe.py "lecture.mov" --timestamps --formats json
```

## 平台环境配置

首次使用先装环境（约下载 sherpa-onnx 包 + X-ASR 模型 ~200 MB）。**按你的平台走对应的 reference**，里面含一键脚本 + 分步手工安装 + 故障排查：

| 平台 | Reference | 默认 provider |
|---|---|---|
| macOS（Apple Silicon / Intel） | [references/setup-macos.md](./references/setup-macos.md) | `cpu` |
| Linux（ARM64 / x86_64，可选 CUDA） | [references/setup-linux.md](./references/setup-linux.md) | `cpu`；NVIDIA GPU 可切 `cuda` |
| Windows（PowerShell 5.1+） | [references/setup-windows.md](./references/setup-windows.md) | `cpu` |

一键安装示例：

```bash
# macOS / Linux
bash scripts/setup.sh

# Windows（PowerShell）
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

## 参数

### transcribe.py（转写，可选补时间戳）

| 参数 | 默认 | 说明 |
|---|---|---|
| `input` | — | 视频或音频路径（位置参数） |
| `--lang` | `zh` | `zh` / `en` / `auto`；也接受 `中文`/`英文`/`chinese`/`english` |
| `--output-dir`, `-o` | 源文件所在目录 | 输出目录 |
| `--model-dir` | `~/.cache/sherpa-onnx-models/sherpa-onnx-x-asr-...-2026-06-03/` | 模型目录 |
| `--formats` | `txt,md` | 逗号分隔，可选 `txt,md,json,srt,vtt`（后两个要配 `--timestamps`） |
| `--timestamps` | CLI 默认关；skill 默认传入 | 写出 srt/vtt 字幕（**X-ASR 默认产出 token 时间戳**，此开关只是把时间戳写入字幕） |
| `--provider` | 平台自动 | `cpu` / `cuda`（NVIDIA）。macOS 默认 `cpu` |
| `--num-threads` | `4` | sherpa-onnx 推理线程数；CPU 时一般与物理核数接近 |
| `--overwrite` | 关 | 允许覆盖已有输出 |
| `--keep-audio` | 关 | 保留中间 16k wav（调试用） |

环境变量：`ASR_PROVIDER`（覆盖 `--provider`）、`ASR_MODEL_DIR`（覆盖 `--model-dir`）。

## 平台与加速（"对核显支持较友好"）

| 平台       | 默认 provider | 加速原理                                                | 备注                          | 配置 / 故障排查 |
| -------- | ----------- | ------------------------------------------------ | --------------------------- | --- |
| [macOS Apple Silicon（M1+）](./references/setup-macos.md#4-provider--加速) | `cpu` | int8 + Apple Silicon AMX 矩阵加速 + 多线程 | 实测 ~100× 实时（RTF ≈ 0.01） | [setup-macos.md](./references/setup-macos.md) |
| [macOS Intel](./references/setup-macos.md#4-provider--加速)          | `cpu`       | int8 + 多线程                                       | ~1× 实时                     | [setup-macos.md](./references/setup-macos.md) |
| [Linux NVIDIA GPU](./references/setup-linux.md#4-provider--加速)     | `cuda`（检测到时）| ONNX Runtime CUDA EP                            | 需 `pip install onnxruntime-gpu` | [setup-linux.md](./references/setup-linux.md) |
| [Linux 其它（ARM64 / x86_64 CPU）](./references/setup-linux.md#4-provider--加速)            | `cpu`       | int8 + 多线程                                       | ARM64 实测 ~32× 实时（RTF ≈ 0.03）；x86_64 约 1× 实时 | [setup-linux.md](./references/setup-linux.md) |
| [Windows](./references/setup-windows.md#4-provider--加速)              | `cpu`       | int8 + 多线程                                       | 原生 PowerShell 用 `setup.ps1`，已实测 | [setup-windows.md](./references/setup-windows.md) |

Apple Silicon 直接使用 `cpu` provider 即可，int8 + AMX 矩阵加速 + 多线程约 100× 实时。NVIDIA 独显上可走 CUDA EP，但需要装 `onnxruntime-gpu`（pip 装 sherpa-onnx 自带的是 CPU 路径）。

各平台**详细配置 / 故障排查**见对应 reference：
[setup-macos.md](./references/setup-macos.md) ·
[setup-linux.md](./references/setup-linux.md) ·
[setup-windows.md](./references/setup-windows.md)。

## 模型选择

X-ASR 系列 sherpa-onnx 官方推出的中文/英文双语 Zipformer transducer 模型，**默认使用 int8 量化版本**（约 200 MB，CPU 上更快）。

| 场景 | 模型 | URL |
|---|---|---|
| **默认（int8，中英双语带标点）** | `sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03` | https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2 |

`--model-dir` 可指向任意 sherpa-onnx Zipformer transducer 目录（只要里面有 `encoder-*.onnx` / `decoder-*.onnx` / `joiner-*.onnx` / `tokens.txt`）。

## 常见故障

| 现象 | 原因 / 处理 |
|---|---|
| `ModuleNotFoundError: sherpa_onnx` | 先跑 `bash scripts/setup.sh`（Windows 用 `.\scripts\setup.ps1`）；详见对应平台 reference |
| `Model directory not found` | 模型未下载，重跑 `setup.sh` 或 `--model-dir <dir>` 指向已有目录 |
| HuggingFace 报 401（**不会发生**） | sherpa-onnx 模型从 GitHub release 下，不走 HF |
| 对齐权重下载中断 | 国内直连 GitHub release 偶发断，用镜像：`GITHUB_PROXY=https://gh-proxy.com` 重跑 `setup.sh`（脚本识别此变量） |
| 内存不足 | `--num-threads` 调小（如 `2`）；或换更小模型（找同系列更早日期的 release） |
| 口语词多（嗯/呃/这个） | X-ASR 输出偏书面，无明显口语化残留 |
| 时间戳整体偏早或偏晚 | X-ASR 自带 token 对齐，偏移通常 < 0.5s；若明显偏，检查音频轨是否与输入一致 |

## Operating rules

- **长音频务必后台运行**并给用户进度提示，不要干等。
- 输出完成后，报告实际产出的 `.txt` / `.md` / `.srt` / `.vtt` 绝对路径。
- 默认加 `--timestamps`；只有用户明确只要纯文本时才省略。X-ASR 默认就产 token 时间戳，不额外加载权重。
- 不要硬编码 GitHub release URL —— 升级模型时统一改 `setup.sh` 顶部的 `X_ASR_RELEASE_URL`。
