# X-ASR 模型与下载

## 默认选择

| 语言 | 后端 | 模型 | 量化 | 备注 |
|---|---|---|---|---|
| 中文 / 英文（自动标点）| sherpa-onnx X-ASR Zipformer transducer | `sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03` | int8 | 默认；约 200 MB；中英双语带标点 |

X-ASR 是 sherpa-onnx 团队基于 Zipformer transducer 的中英双语 ASR，**自带标点**，模型自带 token 级时间戳（无需独立 ForcedAligner）。int8 量化版在 CPU 上接近实时、CoreML / CUDA 加速下数倍实时。

## 模型来源

```text
https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/
    sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2
```

`setup.sh` / `setup.ps1` 默认下载并解压到：

```text
~/.cache/sherpa-onnx-models/<release-name>/
  ├── encoder-epoch-XX-avg-XX.onnx
  ├── decoder-epoch-XX-avg-XX.onnx
  ├── joiner-epoch-XX-avg-XX.onnx
  └── tokens.txt
```

## 备选模型（升级 / 切换）

| 场景 | 模型 | 量化 | 大小 | 备注 |
|---|---|---|---|---|
| 默认（int8，中英标点） | `sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03` | int8 | ~200 MB | 本 skill 默认 |
| Float 版（更大、稍慢） | `sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-fp16-...` | fp16 | ~400 MB | 提升准确率边际收益；CPU 较慢 |
| 仅中文 | `sherpa-onnx-zipformer-ctc-zh-2025-...` | int8 | ~200 MB | 单语种模型 |
| 仅英文 | `sherpa-onnx-zipformer-en-2025-...` | int8 | ~200 MB | Whisper 风格大模型 |

切换模型只需下载新 release、解压后用 `--model-dir <dir>` 指向它即可。

## 模型自带能力

X-ASR Zipformer transducer **不需要独立 ForcedAligner**，因为：
- Transducer 解码天然给出 token 边界；
- sherpa-onnx `OfflineStreamResult` 提供 `tokens` + `timestamps`；
- `transcribe.py --timestamps` 直接据此合成字幕（按句末标点合并，长度上限 8 秒）。

如果 sherpa-onnx 版本较老没暴露 timestamps，输出 JSON 里的 `tokens` / `timestamps` 字段会为空，字幕生成会失败——升级到最新 sherpa-onnx 即可。

## 跨平台安装包

- `pip install sherpa-onnx`：CPU / macOS CoreML（X-ASR 当前 int8 release 不带 CoreML EP，会自动 fallback 到 CPU）
- `pip install sherpa-onnx-cuda` 或先 `pip install onnxruntime-gpu` 再 `pip install sherpa-onnx`：Linux/Windows CUDA
- macOS 12+（Apple Silicon）/ Linux x86_64 + glibc 2.28+ / Windows 10+ 均官方支持

## 调用库

- ASR 运行库：`sherpa-onnx`（`pip install sherpa-onnx`）。
- 依赖：`numpy`、`onnxruntime`（CPU 版）/ `onnxruntime-gpu`（CUDA 版）。
- 不需要 torch / transformers。

## 已知限制

- **CoreML provider**：当前 X-ASR int8 release 未带 CoreML EP。`transcribe.py` 检测 Apple Silicon 时仍选 `coreml`，但 `asr_x.py` 加载失败会自动 fallback `cpu` 并打印警告。要在 Apple Silicon 上跑 CoreML 加速，等 sherpa-onnx 后续 release（int8 模型出 CoreML EP）。
- **Linux 核显**：sherpa-onnx 对 Intel iGPU 的 OpenVINO EP 支持较弱。如果只有 Intel 集显，默认 CPU 已经够用（int8 模型 + 多线程一般 1× 实时）。
- **不在 HuggingFace**：sherpa-onnx 模型在 GitHub release / k2-fsa 自己的镜像上，**不走 HuggingFace**。所以 HF 401 / 国内直连 HF 卡顿之类的坑不会发生；偶发 GitHub release 下载失败可设 `GITHUB_PROXY=https://gh-proxy.com/` 重跑 `setup.sh`。

## 升级模型

```bash
# 设 REINSTALL_MODEL=1 强制重下
REINSTALL_MODEL=1 bash scripts/setup.sh
```

或者编辑 `setup.sh` 顶部的 `X_ASR_RELEASE_URL` / `X_ASR_RELEASE_NAME` 后重跑。