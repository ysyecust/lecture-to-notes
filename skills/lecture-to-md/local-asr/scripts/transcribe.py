#!/usr/bin/env python3
"""本地音视频转写统一入口（sherpa-onnx X-ASR，中英双语）。

只依赖标准库 + ffmpeg；真正的推理在 sherpa-onnx 包里跑（首次需执行 setup.sh）。
X-ASR 输出文本 + token 级时间戳，因此 --timestamps 不引入额外权重。

用法:
    python3 transcribe.py <视频或音频> [--lang zh|en] [--output-dir DIR] [选项]

默认输出到源文件所在目录，文件名与源文件同干名。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (  # noqa: E402
    cleanup_dir,
    fmt_ts_short,
    fmt_ts_srt,
    prepare_audio,
    probe,
    require,
    write_plain_md,
    write_plain_txt,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LANG_ALIASES = {
    "zh": "zh", "chinese": "zh", "中文": "zh",
    "en": "en", "english": "en", "英文": "en",
    "auto": "auto",
}

DEFAULT_FORMATS = "txt,md"

# 字幕条合并阈值
MAX_CUE_SEC = 8.0       # 单条字幕最长时长
HARD_CUE_SEC = 12.0      # 超过就强制切断
MAX_CUE_CJK = 40         # 中文单条最长字符
MAX_CUE_WORD = 90        # 非中文单条最长字符

SENT_END = "。！？!?；;…"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="本地转写：sherpa-onnx X-ASR（中英双语），跨平台")
    ap.add_argument("input", help="视频或音频文件路径")
    ap.add_argument("--lang", "-l", default="zh",
                    help="语言：zh（默认）| en | auto")
    ap.add_argument("--output-dir", "-o", default=None,
                    help="输出目录，默认与源文件同目录")
    ap.add_argument("--model-dir", default=None,
                    help="X-ASR 模型目录（覆盖 ASR_MODEL_DIR 与默认缓存位置）")
    ap.add_argument("--provider", default=None,
                    help="cpu / coreml / cuda；默认 macOS Apple Silicon=coreml，其它=cpu")
    ap.add_argument("--num-threads", type=int, default=3, help="CPU 线程数")
    ap.add_argument("--formats", default=DEFAULT_FORMATS,
                    help="输出格式组合，逗号分隔：txt,md,json,srt,vtt（默认 txt,md）")
    ap.add_argument("--context", default=None,
                    help="术语/热词提示（当前 sherpa-onnx 版本忽略，留兼容）")
    ap.add_argument("--max-chunk-sec", type=float, default=600.0,
                    help="单次解码音频秒数（默认 600）")
    ap.add_argument("--keep-audio", action="store_true", help="保留中间 16k wav")
    ap.add_argument("--timestamps", action="store_true",
                    help="保留 token 时间戳，产出 srt/vtt 字幕")
    ap.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的输出文件")
    return ap.parse_args(argv)


def normalize_lang(value: str) -> str:
    key = (value or "zh").strip().lower()
    return LANG_ALIASES.get(key, key if key in ("zh", "en", "auto") else "zh")


def is_cjk_heavy(text: str) -> bool:
    """粗判：CJK 字符占比 > 20% 视为中文。"""
    sample = text[:2000]
    if not sample:
        return False
    cjk = sum(1 for ch in sample if "一" <= ch <= "鿿")
    return cjk / len(sample) > 0.2


def tokens_to_cues(tokens: list[str], timestamps: list[float],
                   text: str, cjk: bool) -> list[dict]:
    """把 X-ASR 输出的 (token, 起始秒) 列表合并成字幕条。

    X-ASR tokens 列表去掉 BPE 标记后会比原文细；这里用一个简单启发：
    - 把 tokens 按自然停顿（句末标点、逗号）合并；
    - 若一整段无标点（如纯中文识别结果），按「N 字符/段」与「最大时长」切。
    时间戳：每条字幕 start = 第一个 token 的时间戳，end = 最后一个 token 的时间戳 + 词时长估值。
    """
    if not tokens or not timestamps or len(tokens) != len(timestamps):
        return []

    # X-ASR token 里可能含 <blk> / ▁/ BPE 边界符；粗略清理
    clean_pairs: list[tuple[str, float]] = []
    for tok, ts in zip(tokens, timestamps):
        # sherpa-onnx X-ASR PUNCT 模型：标点是独立 token；保留
        if not tok:
            continue
        clean_pairs.append((tok, float(ts)))

    if not clean_pairs:
        return []

    max_chars = MAX_CUE_CJK if cjk else MAX_CUE_WORD

    cues: list[dict] = []
    buf_tokens: list[str] = []
    buf_start: float | None = None
    buf_end: float | None = None

    def flush(reason_end_ts: float | None = None):
        nonlocal buf_tokens, buf_start, buf_end
        if not buf_tokens:
            return
        text_seg = "".join(buf_tokens).strip()
        if not text_seg:
            buf_tokens, buf_start, buf_end = [], None, None
            return
        start = buf_start or 0.0
        if reason_end_ts is not None:
            end = reason_end_ts
        elif buf_end is not None:
            end = buf_end
        else:
            end = start + 0.5  # 兜底
        # 单条最长时长限制：超过就强制切
        if end - start > HARD_CUE_SEC:
            end = start + HARD_CUE_SEC
        cues.append({"start": round(start, 3), "end": round(end, 3), "text": text_seg})
        buf_tokens, buf_start, buf_end = [], None, None

    # 提前算好「下一 token 的起始时间」作为本条字幕的 end（更贴近真实语音尾）。
    # 末 token 没有后继，给个默认兜底（用自身时间 + 0.3s），避免 end == start。
    n = len(clean_pairs)
    next_ts: list[float] = [
        clean_pairs[i + 1][1] if i + 1 < n else clean_pairs[i][1] + 0.3
        for i in range(n)
    ]

    for i, (tok, ts) in enumerate(clean_pairs):
        if buf_start is None:
            buf_start = ts
        buf_tokens.append(tok)
        buf_end = ts

        # 触发切分的条件（命中任一即 flush 当前 buf）：
        seg_so_far = "".join(buf_tokens)
        end_sentence = tok[-1] in SENT_END if tok else False
        too_long = len(seg_so_far) >= max_chars
        too_long_time = (buf_end - buf_start) >= MAX_CUE_SEC if buf_end is not None and buf_start is not None else False

        if end_sentence or too_long or too_long_time:
            # 用下一 token 的时间戳作为本条结束（更贴近真实语音尾）
            flush(next_ts[i])

    # 收尾
    flush()

    return cues


def write_srt(cues: list[dict], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for i, c in enumerate(cues, 1):
            f.write(f"{i}\n{fmt_ts_srt(c['start'])} --> {fmt_ts_srt(c['end'])}\n{c['text']}\n\n")


def write_vtt(cues: list[dict], path: str) -> None:
    """srt → vtt：把逗号换成点。"""
    with open(path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for c in cues:
            f.write(f"{fmt_ts_srt(c['start']).replace(',', '.')} --> "
                    f"{fmt_ts_srt(c['end']).replace(',', '.')}\n{c['text']}\n\n")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    src = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.isfile(src):
        sys.exit(f"[asr] 文件不存在: {src}")

    lang = normalize_lang(args.lang)

    info = probe(src)
    print(f"[asr] 源文件: {src}")
    print(f"[asr] 时长: {fmt_ts_short(info['duration'])} | 音频轨: {info['has_audio']} "
          f"| 语言: {lang}")

    out_dir = os.path.abspath(os.path.expanduser(
        args.output_dir if args.output_dir else os.path.dirname(src)))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    if args.timestamps and args.formats == DEFAULT_FORMATS:
        formats = ["txt", "md", "srt"]  # 没显式指定时，开 timestamps 就顺带出 srt
    if any(f in ("srt", "vtt") for f in formats) and not args.timestamps:
        sys.exit("[asr] 输出 srt/vtt 需要加 --timestamps（时间戳由 X-ASR 解码时给出）")

    targets = {f: os.path.join(out_dir, f"{stem}.{f}") for f in formats}
    if not args.overwrite:
        clash = [p for p in targets.values() if os.path.exists(p)]
        if clash:
            sys.exit("[asr] 已存在输出文件（加 --overwrite 覆盖）:\n  " + "\n  ".join(clash))

    keep = args.keep_audio
    wav, workdir = prepare_audio(src)
    print(f"[asr] 音频: {wav}")

    with tempfile.TemporaryDirectory(prefix="asr-result-") as tmp:
        result_json = os.path.join(tmp, "result.json")
        cmd = [
            sys.executable, os.path.join(SCRIPT_DIR, "asr_x.py"), wav,
            "--out", result_json,
            "--language", lang,
            "--num-threads", str(args.num_threads),
        ]
        if args.model_dir:
            cmd += ["--model-dir", args.model_dir]
        if args.provider:
            cmd += ["--provider", args.provider]
        if args.context:
            cmd += ["--context", args.context]

        print("[asr] 开始转写（长音频请耐心等待）...", flush=True)
        proc = subprocess.run(cmd, cwd=tmp)
        if proc.returncode != 0:
            sys.exit(f"[asr] 转写失败，退出码 {proc.returncode}")
        with open(result_json, encoding="utf-8") as f:
            payload = json.load(f)

    if not keep and workdir:
        cleanup_dir(workdir)

    text = (payload.get("text") or "").strip()
    if not text:
        sys.exit("[asr] 没有识别出任何内容，请检查音频轨是否存在。")

    tokens = payload.get("tokens") or []
    timestamps = payload.get("timestamps") or []
    has_timestamps = bool(tokens) and bool(timestamps) and len(tokens) == len(timestamps)

    written = []
    for fmt in formats:
        path = targets[fmt]
        if fmt == "txt":
            write_plain_txt(text, path)
        elif fmt == "md":
            write_plain_md(text, path, title=stem, source=src)
        elif fmt == "json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "meta": {
                        "source": src,
                        "language": payload.get("language", lang),
                        "backend": payload.get("backend"),
                        "model": payload.get("model"),
                        "provider": payload.get("provider"),
                        "duration": payload.get("duration", info["duration"]),
                    },
                    "text": text,
                    "tokens": tokens,
                    "timestamps": timestamps,
                }, f, ensure_ascii=False, indent=2)
        elif fmt in ("srt", "vtt"):
            if not has_timestamps:
                sys.exit("[asr] 当前 sherpa-onnx 版本未返回 token 时间戳，无法写字幕。"
                         "升级 sherpa-onnx 或换用 cloud ASR。")
            cjk = is_cjk_heavy(text)
            cues = tokens_to_cues(tokens, timestamps, text, cjk)
            (write_srt if fmt == "srt" else write_vtt)(cues, path)
        else:
            continue
        written.append(path)

    print(f"[asr] 完成：{len(text)} 字 / 模型 {payload.get('model', '?')}"
          f" / provider {payload.get('provider', '?')}"
          + (" / coreml 回退 cpu" if payload.get("tried_coreml_fallback") else ""))
    for path in written:
        print(f"  - {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())