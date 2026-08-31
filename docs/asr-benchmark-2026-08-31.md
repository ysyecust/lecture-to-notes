# X ASR 本地转写基准（2026-08-31）

本次测试用于回应 [Issue #12](https://github.com/ysyecust/lecture-to-notes/issues/12)，
判断 X ASR 是否适合作为中英混合课程的本地字幕后端。结论是：可以作为可选首选后端，
但不能替代字幕健康检查、课程词典和人工语义抽检，也不应删除 Whisper 回退。

## 被测配置

- 音频：南京大学《生成式软件工程》2026 第 1 讲的四个区段，共 540 秒；覆盖课程开场、
  LLM 概念、浏览器操作和 qrgen/GLM-5.3 案例。
- X ASR：`sherpa-onnx` 1.13.6，8 线程，CPUExecutionProvider。
- 模型：`sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03`。
- 模型发布资产大小：136,396,739 bytes。
- 模型 SHA-256：`5d02c36d7b44e886b7c8f0d8e051f8713acab96c264bb6ef9e718be39a6a2224`。
- 对照：faster-whisper small，CPU INT8，16 线程，beam size 5，VAD 开启。
- 主机：Windows，Python 3.13；本次只测 CPU，没有验证核显、CUDA、DirectML 或 QNN。

模型来自 sherpa-onnx 的
[官方发布资产](https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03.tar.bz2)，
其文件说明指向 [X-ASR](https://github.com/Gilgamesh-J/X-ASR)。

## 速度结果

| 区段 | 音频 | X ASR | X ASR RTF | Whisper | Whisper RTF |
|---|---:|---:|---:|---:|---:|
| 课程开场 | 120 s | 1.379 s | 0.0115 | 28.765 s | 0.2398 |
| LLM/Agent | 120 s | 1.377 s | 0.0115 | 27.269 s | 0.2315 |
| Browser/教务系统 | 120 s | 1.413 s | 0.0118 | 23.582 s | 0.1959 |
| qrgen/GLM-5.3 | 180 s | 2.017 s | 0.0112 | 42.045 s | 0.2342 |
| **合计** | **540 s** | **6.186 s** | **0.0115** | **121.660 s** | **0.2253** |

仅计算模型解码，X ASR 在这组样本上约快 **19.7 倍**。它为每个 token 返回时间戳；
`scripts/transcribe_x_asr.py` 据此生成 SRT。离线模型不应直接接收整段长课，实测长输入会在
encoder reshape 处失败，因此脚本在 30 秒上限内寻找低能量切点。

## 识别质量观察

X ASR 的优势：

- 中英文切换和标点明显更自然，例如 `computer science`、`open/policy`、`next token`、
  `Android app`、`Chrome`、`corner case`、`specification` 和 `32K output token`。
- “教务系统”“隐私”“教学周历”“Excel 2019”等中文语义优于本次 Whisper 输出。
- 默认输出简体中文；本次 Whisper 在 qrgen 区段出现了大段繁体输出。

Whisper 的优势：

- 时间分段通常更细。
- 个别实体更准，例如 `1975`、`QQ`、`Base64`、`GPT-5.6` 和 `Deep Seek V4 Pro`。

两者共同的错误包括 Neovim、Altair 8800、Vibe Coding、GLM-5.3、Claude Code、
long-horizon task 和 AI slop。X ASR 的 `Neo Vim` 比 Whisper 的 `NeoWim` 更接近正确形式，
但依然需要课程词典。这里没有人工逐字真值，因此不报告 CER/WER，也不把主观样例观察
包装成全面准确率结论。

## 采用策略

1. 先取人工 CC 或平台自动字幕。
2. 字幕缺失时，中英混合课程可先运行 X ASR；其他语言或模型不可用时运行 Whisper。
3. 无论后端，都保留原始 SRT 和后端报告，运行 `check_srt_health.py`。
4. 在课程 10%、50%、90% 位置对照音频、画面和字幕；失败即更换后端或重新转写。
5. 最后运行课程词典与语义校正。后端速度不能越过证据门。

## 可复现命令

```bash
python -m pip install "numpy>=1.24" "sherpa-onnx>=1.13.6"
python scripts/transcribe_x_asr.py audio.wav \
  --model-dir /path/to/sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03 \
  --output audio.srt --report x_asr_report.json
python scripts/check_srt_health.py audio.srt --duration <seconds>
```
