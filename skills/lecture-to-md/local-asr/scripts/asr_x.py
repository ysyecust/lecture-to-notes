#!/usr/bin/env python3
"""sherpa-onnx X-ASR 后端（Zipformer transducer，中英双语带标点）。

本脚本被 transcribe.py 通过子进程调用，纯 Python 推理，跨平台：
- macOS Apple Silicon：默认 coreml provider（加速）；失败自动 fallback cpu
- Linux NVIDIA：cuda provider（需安装 onnxruntime-gpu）
- 其它：cpu provider，int8 量化 + 多线程

输入：16 kHz 单声道 wav。
输出：JSON（backend / model / language / duration / text / tokens / timestamps）。

默认模型：sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03
（约 200 MB，int8 量化，中英双语带标点）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# 把脚本所在目录加到 sys.path，方便 transcribe.py 用 `python3 asr_x.py ...` 启动时
# 我们也能 import common.py（虽然这里实际上用不到，但保持一致）。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", help="16 kHz 单声道 wav")
    ap.add_argument("--out", required=True, help="输出 JSON 路径")
    ap.add_argument("--model-dir", default=None,
                    help="sherpa-onnx X-ASR 模型目录；默认从 ASR_MODEL_DIR 或缓存默认位置推断")
    ap.add_argument("--encoder", default=None, help="encoder.onnx 路径（覆盖 model-dir 自动探测）")
    ap.add_argument("--decoder", default=None, help="decoder.onnx 路径")
    ap.add_argument("--joiner", default=None, help="joiner.onnx 路径")
    ap.add_argument("--tokens", default=None, help="tokens.txt 路径")
    ap.add_argument("--provider", default=None, help="cpu / coreml / cuda；默认从 ASR_PROVIDER 或自动探测")
    ap.add_argument("--num-threads", type=int, default=3, help="CPU 线程数")
    ap.add_argument("--language", default="auto",
                    help="zh / en / auto（X-ASR 是单语种模型，但 zh/en hint 影响输出语言）")
    ap.add_argument("--context", default="", help="术语/热词提示，限制 200 字以内")
    return ap.parse_args()


def _resolve_model_files(args: argparse.Namespace) -> tuple[str, str, str, str]:
    """解析出 (encoder, decoder, joiner, tokens) 四个路径。"""
    if args.encoder and args.decoder and args.joiner and args.tokens:
        return args.encoder, args.decoder, args.joiner, args.tokens

    # 否则从 model_dir 自动探测
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from common import find_model_files, resolve_model_dir  # noqa: E402

    model_dir = args.model_dir or resolve_model_dir()
    return find_model_files(model_dir)


def _resolve_provider(args: argparse.Namespace) -> str:
    """CLI 参数 > 环境变量 > 自动探测。"""
    if args.provider:
        return args.provider
    env = os.environ.get("ASR_PROVIDER")
    if env:
        return env
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from common import detect_default_provider  # noqa: E402

    return detect_default_provider()


def _load_audio(path: str, target_sr: int = 16000):
    """读 wav（不依赖 soundfile，sherpa-onnx 自带 read_wave）。"""
    import sherpa_onnx

    samples = sherpa_onnx.read_wave(path).samples
    if hasattr(samples, "numpy"):
        samples = samples.numpy()
    samples = list(samples)  # sherpa-onnx 接受 list[float]
    return samples, target_sr


def main() -> int:
    args = parse_args()
    encoder, decoder, joiner, tokens = _resolve_model_files(args)
    provider = _resolve_provider(args)

    import sherpa_onnx

    # sherpa-onnx 不同版本构造方式略有差异；优先 OfflineRecognizer.from_transducer，
    # 旧版若不支持则退到 OfflineRecognizer(...)
    print(f"[asr-x] 模型: {os.path.dirname(encoder)}", file=sys.stderr)
    print(f"[asr-x] provider: {provider}（若不可用会自动回退到 cpu）", file=sys.stderr)

    recognizer = None
    tried_coreml = provider == "coreml"
    try:
        recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=encoder,
            decoder=decoder,
            joiner=joiner,
            tokens=tokens,
            num_threads=args.num_threads,
            provider=provider,
            decoding_method="greedy_search",
            debug=False,
        )
    except Exception as exc:
        # coreml 模型不支持 / onnxruntime 没编进去：常见情况，安静地 fallback cpu
        if provider != "cpu":
            print(f"[asr-x] provider '{provider}' 加载失败 ({exc.__class__.__name__})，回退 cpu",
                  file=sys.stderr)
            provider = "cpu"
            tried_coreml = False
            recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=encoder,
                decoder=decoder,
                joiner=joiner,
                tokens=tokens,
                num_threads=args.num_threads,
                provider="cpu",
                decoding_method="greedy_search",
                debug=False,
            )
        else:
            raise

    samples, sr = _load_audio(args.audio)
    duration = len(samples) / sr

    # sherpa-onnx 0.1.x+ 用 accept_waveform；0.1.0 之前是 feed，但 X-ASR 是新模型，按新版 API 走
    stream = recognizer.create_stream()
    stream.accept_waveform(sr, samples)

    # 上下文（术语表）—— sherpa-onnx 1.10+ 的 OfflineRecognizer 不直接支持 context；
    # 留接口避免上层调用失败；如需强引导可用 --hotwords-file 替换（未来加）。
    # 当前实现：忽略 args.context，仅记录提示。
    if args.context:
        print("[asr-x] 注：当前 sherpa-onnx 版本不支持运行时热词；--context 已忽略",
              file=sys.stderr)

    print(f"[asr-x] 开始推理（音频 {duration:.1f}s）...", file=sys.stderr, flush=True)
    recognizer.decode_stream(stream)
    text = (stream.result.text or "").strip()

    # tokens / timestamps：sherpa-onnx 0.1.x+ 的 OfflineStreamResult 提供 tokens 与 timestamps
    # （按 token index → 起始秒）。逐 token 拼回去得到的就是带时间戳的字幕。
    tokens_out = []
    timestamps_out = []
    try:
        result_tokens = list(stream.result.tokens or [])
        result_timestamps = list(stream.result.timestamps or [])
        # sherpa-onnx 的 timestamps 单位是「秒」，与 tokens 一一对应
        for tok, ts in zip(result_tokens, result_timestamps):
            tokens_out.append(str(tok))
            timestamps_out.append(float(ts))
    except AttributeError:
        # 老版本 sherpa-onnx 没有 timestamps —— 仍能给出文本，但 srt/vtt 会失败。
        print("[asr-x] 当前 sherpa-onnx 版本不返回 token 时间戳；--timestamps 不可用",
              file=sys.stderr)

    payload = {
        "backend": "sherpa-onnx-x-asr",
        "model": os.path.dirname(encoder),
        "provider": provider,
        "language": args.language,
        "duration": duration,
        "text": text,
        "tokens": tokens_out,
        "timestamps": timestamps_out,
        "tried_coreml_fallback": tried_coreml and provider == "cpu",
    }

    Path = __import__("pathlib").Path
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[asr-x] 完成：{len(text)} 字 / {len(tokens_out)} token", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())