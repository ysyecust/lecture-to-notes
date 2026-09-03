#!/usr/bin/env bash
# sherpa-onnx X-ASR 一键安装脚本（macOS / Linux）。
# Windows 用户请用 PowerShell 版（见 SKILL.md「Windows 设置」一节）。
#
# 步骤：
#   1) 检查 ffmpeg / ffprobe
#   2) pip 装 sherpa-onnx（含 numpy / onnxruntime）
#   3) 下载并解压 X-ASR int8 Zipformer transducer 模型
#   4) （可选）安装 onnxruntime-gpu（Linux CUDA）
#
# 进阶：以下环境变量可覆盖默认行为
#   X_ASR_RELEASE_URL   自定义 GitHub release URL
#   ASR_MODEL_DIR       模型解压目录（默认 ~/.cache/sherpa-onnx-models/<...>）
#   PIP                指定的 pip（默认 python3 -m pip）
#   GITHUB_PROXY       GitHub 镜像前缀（如 https://gh-proxy.com/）
#   SKIP_PIP            设为 1 跳过 pip install sherpa-onnx
#   SKIP_MODEL          设为 1 跳过模型下载（仅装包）

set -uo pipefail

X_ASR_RELEASE_NAME="sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
X_ASR_RELEASE_URL="${X_ASR_RELEASE_URL:-https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${X_ASR_RELEASE_NAME}.tar.bz2}"
# SHA-256 由上游 README/docs/asr-benchmark-2026-08-31.md 记录。解压前必校验，
# 不一致则丢弃并 exit，避免被替换的 ONNX 模型进入推理链。
X_ASR_SHA256="${X_ASR_SHA256:-5d02c36d7b44e886b7c8f0d8e051f8713acab96c264bb6ef9e718be39a6a2224}"
MODEL_DIR="${ASR_MODEL_DIR:-$HOME/.cache/sherpa-onnx-models/${X_ASR_RELEASE_NAME}}"
PIP_CMD="${PIP:-python3 -m pip}"

# ---- 1) ffmpeg 检查 ----
echo "==> 检查 ffmpeg / ffprobe"
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "✗ 没找到 ffmpeg。请先安装："
  echo "  macOS:   brew install ffmpeg"
  echo "  Linux:   sudo apt install ffmpeg"
  exit 1
fi
ffmpeg -version | head -1
ffprobe -version | head -1

# ---- 2) sherpa-onnx pip 包 ----
if [[ "${SKIP_PIP:-0}" == "1" ]]; then
  echo "==> 跳过 pip install（SKIP_PIP=1）"
else
  echo "==> 安装 sherpa-onnx（pip）"
  $PIP_CMD install -U sherpa-onnx
fi
  python3 -c "import sherpa_onnx; print('  ok: sherpa-onnx', getattr(sherpa_onnx, '__version__', 'unknown'))"

# ---- 3) 下载 + 解压 X-ASR 模型 ----
if [[ "${SKIP_MODEL:-0}" == "1" ]]; then
  echo "==> 跳过模型下载（SKIP_MODEL=1）"
else
  echo "==> 下载 X-ASR 模型（约 200 MB）：${X_ASR_RELEASE_URL}"
  CACHE_DIR="$HOME/.cache/sherpa-onnx-models"
  mkdir -p "$CACHE_DIR"
  TAR_FILE="$CACHE_DIR/${X_ASR_RELEASE_NAME}.tar.bz2"

  # 优先用 GitHub 镜像（如 GITHUB_PROXY=https://gh-proxy.com/）
  DOWNLOAD_URL="$X_ASR_RELEASE_URL"
  if [[ -n "${GITHUB_PROXY:-}" ]]; then
    DOWNLOAD_URL="${GITHUB_PROXY}${DOWNLOAD_URL}"
  fi

  if [[ -d "$MODEL_DIR" && -f "$MODEL_DIR/tokens.txt" && -z "${REINSTALL_MODEL:-}" ]]; then
    echo "  ✓ 模型已存在：$MODEL_DIR（设 REINSTALL_MODEL=1 强制重下）"
  else
    if command -v curl >/dev/null 2>&1; then
      curl -L --fail -o "$TAR_FILE" "$DOWNLOAD_URL" || {
        echo "✗ 下载失败：$DOWNLOAD_URL"
        echo "  试试 GITHUB_PROXY=https://gh-proxy.com/ 重新跑本脚本"
        exit 1
      }
    elif command -v wget >/dev/null 2>&1; then
      wget -O "$TAR_FILE" "$DOWNLOAD_URL" || {
        echo "✗ 下载失败：$DOWNLOAD_URL"
        exit 1
      }
    else
      echo "✗ 没找到 curl 或 wget"
      exit 1
    fi

    # ---- SHA-256 校验 ----
    # 不一致则删除并退出：避免被替换的 ONNX 模型进入推理链。
    if [[ -n "$X_ASR_SHA256" ]]; then
      echo "==> 校验 SHA-256"
      if command -v shasum >/dev/null 2>&1; then
        ACTUAL_SHA="$(shasum -a 256 "$TAR_FILE" | awk '{print $1}')"
      elif command -v sha256sum >/dev/null 2>&1; then
        ACTUAL_SHA="$(sha256sum "$TAR_FILE" | awk '{print $1}')"
      else
        echo "✗ 找不到 shasum / sha256sum，跳过校验（不推荐）"
        ACTUAL_SHA=""
      fi
      if [[ -n "$ACTUAL_SHA" ]]; then
        echo "    expected: $X_ASR_SHA256"
        echo "    actual:   $ACTUAL_SHA"
        if [[ "$ACTUAL_SHA" != "$X_ASR_SHA256" ]]; then
          echo "✗ SHA-256 不匹配，删除下载文件并退出"
          echo "  设为 X_ASR_SHA256= 可跳过校验（不推荐）"
          echo "  或者用 X_ASR_RELEASE_URL= 下载你信任的镜像，重跑本脚本"
          rm -f "$TAR_FILE"
          exit 1
        fi
        echo "  ✓ SHA-256 匹配"
      fi
    fi

    echo "==> 解压到 $CACHE_DIR"
    tar -xjf "$TAR_FILE" -C "$CACHE_DIR"
    rm -f "$TAR_FILE"

    if [[ ! -f "$MODEL_DIR/tokens.txt" ]]; then
      echo "✗ 解压后找不到 $MODEL_DIR/tokens.txt"
      echo "  目录内容："
      ls "$CACHE_DIR"
      exit 1
    fi
  fi
  echo "  ✓ 模型已就绪：$MODEL_DIR"
fi

# ---- 4) （可选）CUDA onnxruntime-gpu ----
if [[ "$(uname -s)" == "Linux" ]] && command -v nvidia-smi >/dev/null 2>&1; then
  echo "==> 检测到 NVIDIA GPU；推荐装 onnxruntime-gpu 以启用 --provider cuda"
  read -r -p "  装吗？[y/N] " ans
  if [[ "${ans:-N}" =~ ^[Yy]$ ]]; then
    $PIP_CMD install -U onnxruntime-gpu || echo "  ! onnxruntime-gpu 安装失败，可手动重试"
  fi
fi

cat <<TXT

==> 完成。下一步：

    python3 scripts/transcribe.py /path/to/课程.mp4 --timestamps

- macOS Apple Silicon 默认用 coreml provider；其它默认 cpu
- 加 --provider cuda 可强制 NVIDIA GPU（需先装 onnxruntime-gpu）
- 模型路径：$MODEL_DIR
- 升级模型：设 REINSTALL_MODEL=1 重跑本脚本，或编辑顶部 X_ASR_RELEASE_URL 后重跑

TXT
