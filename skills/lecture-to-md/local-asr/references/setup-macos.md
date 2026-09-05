# macOS 环境配置（Apple Silicon / Intel）

> 本 skill 在 macOS Apple Silicon（M1/M2/M3/M4）与 Intel Mac 上均已端到端验证。
> Apple Silicon 与 Intel Mac 默认都走 `cpu` provider；Apple Silicon 上 int8 + AMX 矩阵加速 + 多线程约 100× 实时。

## 0. 环境要求

| 组件 | 最低 | 推荐 | 备注 |
|---|---|---|---|
| macOS | 11 Big Sur | 13 Ventura+（Apple Silicon 体验最好） | 12+ 已官方支持 |
| Python | 3.9 | 3.11 / 3.12 / 3.13（conda-forge 也可） | 不需要 Python 2 |
| ffmpeg / ffprobe | 4.x | 6.x / 7.x / 8.x | Homebrew 默认装最新 |
| 磁盘空间 | ~300 MB | ~500 MB（ffmpeg + 模型 + 缓存） | 模型约 200 MB |
| 内存 | 8 GB | 16 GB+ | 转写长视频峰值约 1–2 GB |

## 1. 一键安装（推荐）

```bash
cd "<skill 目录>"    # 即 skills/lecture-to-md/local-asr

# 首次：装依赖 + 下载模型（约 200 MB）
bash scripts/setup.sh

# 之后正常转写
python3 scripts/transcribe.py "/path/to/课程录像.mp4"
```

`setup.sh` 自动：

1. 检查 `ffmpeg` / `ffprobe`（没有则报错并提示 `brew install ffmpeg`）。
2. `python3 -m pip install -U sherpa-onnx`（含 onnxruntime CPU 版）。
3. 下载 X-ASR int8 Zipformer transducer（~200 MB），**SHA-256 校验**后解压到 `~/.cache/sherpa-onnx-models/`。
4. 检测到 NVIDIA？不会（macOS 不可能），跳过。

## 2. 分步手工安装

如果不想跑 setup.sh 或需要细粒度控制：

### 2.1 安装 Homebrew（如果还没有）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Apple Silicon 上 Homebrew 装在 `/opt/homebrew/`，Intel 上在 `/usr/local/`。脚本里 `transcribe.py` / `common.py` 已自动覆盖两条路径。

### 2.2 安装 ffmpeg

```bash
brew install ffmpeg
```

验证：

```bash
ffmpeg -version | head -1
ffprobe -version | head -1
```

### 2.3 安装 Python 3

推荐 [Miniforge3 / Miniconda](https://conda-forge.org/miniforge/) 或 Homebrew：

```bash
# Homebrew 路径
brew install python@3.12

# 验证
python3 --version
which python3
```

### 2.4 装 sherpa-onnx

```bash
python3 -m pip install -U sherpa-onnx
```

> macOS 不需要 `onnxruntime-gpu`（Apple Silicon 走 CPU EP + AMX 矩阵加速已 ~100× 实时，Intel 走 CPU）。
> 不要装 torch / transformers / whisper。

验证：

```bash
python3 -c "import sherpa_onnx; print(sherpa_onnx.__version__)"
```

### 2.5 下载并解压 X-ASR 模型

```bash
CACHE="$HOME/.cache/sherpa-onnx-models"
mkdir -p "$CACHE"
cd "$CACHE"

# 直连 GitHub release
curl -L --fail \
  -o sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2 \
  https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2

# 国内断流时走镜像
# GITHUB_PROXY="https://gh-proxy.com/" curl -L --fail -o ... URL

# 校验 SHA-256（与 setup.sh 顶部 X_ASR_SHA256 一致）
shasum -a 256 sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
# 期望：5d02c36d7b44e886b7c8f0d8e051f8713acab96c264bb6ef9e718be39a6a2224

tar -xjf sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
rm sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
```

目录应包含 `encoder-*.onnx` / `decoder-*.onnx` / `joiner-*.onnx` / `tokens.txt`。

## 3. 端到端自检

跑一个 3–5 分钟的视频：

```bash
cd "<skill 目录>"
python3 scripts/transcribe.py "/path/to/short-lecture.mp4" --timestamps
```

预期：

- Apple Silicon：~100× 实时（RTF ≈ 0.01；3 分钟视频约 2 秒跑完）。
- Intel Mac：~1× 实时。
- 输出 `.txt` / `.md` / `.srt` 在源文件同目录。

## 4. Provider / 加速

`transcribe.py` 按平台自动选 provider：

| Mac 机型 | 默认 provider | 实测速度 |
|---|---|---|
| Apple Silicon（M1/M2/M3/M4） | `cpu` | ~100× 实时（RTF ≈ 0.01，走 int8 + AMX 矩阵加速 + 多线程） |
| Intel x86_64 | `cpu` | ~1× 实时 |

强制切换：

```bash
# 显式指定 CPU（默认已是 CPU）
ASR_PROVIDER=cpu python3 scripts/transcribe.py input.mp4
```

## 5. 常见故障（macOS）

| 现象 | 处理 |
|---|---|
| `command not found: ffmpeg` | `brew install ffmpeg`；若是 Apple Silicon，确保 `which ffmpeg` 指向 `/opt/homebrew/bin/ffmpeg` |
| `command not found: python3` | `brew install python@3.12`；或装 Miniforge3 |
| `pip install sherpa-onnx` 报 externally-managed-environment | 用 venv：`python3 -m venv .venv && source .venv/bin/activate && pip install -U sherpa-onnx` |
| 模型下载失败 | 国内断流：`GITHUB_PROXY=https://gh-proxy.com/ bash scripts/setup.sh` |
| 转写中文出现「汉字 汉字」中间多空格 | 这是 X-ASR 输出偶发现象，`transcribe.py` 已经自动归一化（见 `_CJK_RANGES`）；若仍出现，升级到最新 sherpa-onnx |
| 输出 `.srt` 时间戳偏早/偏晚 > 0.5s | 检查源视频音轨是否被替换；X-ASR 自带 token 对齐，偏移通常 < 0.5s |

## 6. 升级

```bash
# 升级 sherpa-onnx
python3 -m pip install -U sherpa-onnx

# 强制重下模型
REINSTALL_MODEL=1 bash scripts/setup.sh

# 升级 ffmpeg
brew upgrade ffmpeg
```

## 7. 卸载

```bash
# 删模型缓存
rm -rf ~/.cache/sherpa-onnx-models/

# 卸 sherpa-onnx
python3 -m pip uninstall sherpa-onnx

# 卸 ffmpeg / python（按需）
brew uninstall ffmpeg
brew uninstall python@3.12
```

---

下一步：转写流程与参数详见 [SKILL.md](../SKILL.md)。
