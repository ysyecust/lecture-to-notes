# X-ASR 模型与下载

## 默认选择

| 语言 | 后端 | 模型 | 量化 | 备注 |
|---|---|---|---|---|
| 中文 / 英文（自动标点）| sherpa-onnx X-ASR Zipformer transducer | `sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03` | int8 | 默认；约 200 MB；中英双语带标点 |

X-ASR 是 sherpa-onnx 团队基于 Zipformer transducer 的中英双语 ASR，**自带标点**，模型自带 token 级时间戳（无需独立 ForcedAligner）。int8 量化版在 Apple Silicon（int8 + AMX 矩阵加速 + 多线程）上 ~100× 实时；Linux/Windows + CUDA EP（需装 `onnxruntime-gpu`）数倍实时。

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

## 模型自带能力

X-ASR Zipformer transducer **不需要独立 ForcedAligner**，因为：
- Transducer 解码天然给出 token 边界；
- sherpa-onnx `OfflineStreamResult` 提供 `tokens` + `timestamps`；
- `transcribe.py --timestamps` 直接据此合成字幕：强标点切分，弱标点在持续 3.5 秒后切分，最长 8 秒或 52 个归一化字符。

如果 sherpa-onnx 版本较老没暴露 timestamps，JSON 里的 token 时间戳会为空，字幕会退化为“整块音频一条 cue”，精度较低；升级到最新 sherpa-onnx 即可恢复 token 级时间轴。

## 跨平台安装包

- `pip install sherpa-onnx`：CPU（Apple Silicon 走 CPU EP + AMX 矩阵加速，约 100× 实时）
- `pip install sherpa-onnx-cuda` 或先 `pip install onnxruntime-gpu` 再 `pip install sherpa-onnx`：Linux/Windows CUDA
- macOS 12+（Apple Silicon）/ Linux x86_64 + glibc 2.28+ / Windows 10+ 均官方支持

## 调用库

- ASR 运行库：`sherpa-onnx`（`pip install sherpa-onnx`）。
- 依赖：`numpy`、`onnxruntime`（CPU 版）/ `onnxruntime-gpu`（CUDA 版）。
- 不需要 torch / transformers。

## 已知限制

- **Linux 核显**：sherpa-onnx 对 Intel iGPU 的 OpenVINO EP 支持较弱。如果只有 Intel 集显，默认 CPU 已经够用（int8 模型 + 多线程一般 1× 实时）。
- **不在 HuggingFace**：sherpa-onnx 模型在 GitHub release / k2-fsa 自己的镜像上，**不走 HuggingFace**。所以 HF 401 / 国内直连 HF 卡顿之类的坑不会发生；偶发 GitHub release 下载失败可设 `GITHUB_PROXY=https://gh-proxy.com/` 重跑 `setup.sh`。

## 升级模型

```bash
# 设 REINSTALL_MODEL=1 强制重下
REINSTALL_MODEL=1 bash scripts/setup.sh
```

或者编辑 `setup.sh` 顶部的 `X_ASR_RELEASE_URL` / `X_ASR_RELEASE_NAME` 后重跑。
