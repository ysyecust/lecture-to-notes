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

# CJK 字符范围（用于去除「汉字 汉字」中的多余空格）
_CJK_RANGES = (
    "\u3000-\u303F"   # CJK Symbols and Punctuation
    "\u4E00-\u9FFF"   # CJK Unified Ideographs
    "\u3400-\u4DBF"   # CJK Extension A
    "\U00020000-\U0002A6DF"   # CJK Extension B
    "\uF900-\uFAFF"   # CJK Compatibility Ideographs
    "\uFF00-\uFFEF"   # 全角 ASCII
)


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
    """把 X-ASR 的 token 时间戳转成字幕条。

    不从 token 重构文本（X-ASR int8 的英文 BPE 切得太碎，"quality" 会变成
    [" q", "u", "al", "ity"]；从 token 拼回去总会有乱七八糟的间隙）。
    改为：直接信任 sherpa-onnx 已产生的 text，按标点切句，每句时间区间由该句
    对应 token 的首/尾时间戳决定。

    token → text 字符映射：每条 token (去前导空格后) 的内容挨个平铺到文本上，
    生成一个 char_idx → token_idx 的表。切句后从表里查句首/末字符对应的 token。
    """
    if not tokens or not timestamps or len(tokens) != len(timestamps):
        return []

    # 1) 切句：按 SENT_END 标点切，保留末尾标点
    sentences: list[str] = []
    buf: list[str] = []
    for i, ch in enumerate(text):
        buf.append(ch)
        end_sentence = ch in SENT_END
        if ch == ".":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            end_sentence = (nxt == "" or nxt.isspace())  # 英文句号避免切在 3.14
        if end_sentence:
            sentences.append("".join(buf).strip())
            buf = []
    if buf:
        tail = "".join(buf).strip()
        if tail:
            sentences.append(tail)

    sentences = [s for s in sentences if s]
    if not sentences:
        return []

    # 2) char_idx → token_idx 映射
    char_to_token: list[int] = []
    for tok_idx, tok in enumerate(tokens):
        content = tok.lstrip(" \u2581")
        for _ in content:
            char_to_token.append(tok_idx)
    if not char_to_token:
        return []

    # 3) 为每句查找起止 token 时间戳
    cues: list[dict] = []
    char_pos = 0
    text_len = len(text)
    last_token_idx = char_to_token[-1]

    for sent in sentences:
        sent_len = len(sent)
        sent_start = min(char_pos, len(char_to_token) - 1)
        sent_end = min(char_pos + sent_len - 1, len(char_to_token) - 1)
        char_pos += sent_len

        if sent_start < 0 or sent_end < sent_start:
            continue

        start_idx = char_to_token[sent_start]
        end_idx = char_to_token[sent_end]
        start_ts = float(timestamps[start_idx])
        end_ts = float(timestamps[end_idx])

        # 末句末尾加一点塞住，避免与下一句重叠
        if end_idx == last_token_idx:
            end_ts = end_ts + 0.3

        cues.append({"start": round(start_ts, 3),
                     "end": round(end_ts, 3),
                     "text": sent})

    # 4) 超长句再细分（按 char 数线性插值时间）
    max_chars = MAX_CUE_CJK if cjk else MAX_CUE_WORD
    final: list[dict] = []
    for c in cues:
        text_seg = c["text"]
        n = len(text_seg)
        dur = c["end"] - c["start"]
        if n <= max_chars and dur <= HARD_CUE_SEC:
            final.append(c)
            continue
        # 超长：按 max_chars 切，时间按字符线性分
        pos = 0
        seg_start = c["start"]
        while pos < n:
            cut = min(n, pos + max_chars)
            seg_text = text_seg[pos:cut].strip()
            if seg_text:
                seg_end = seg_start + dur * (cut - 0) / n
                final.append({
                    "start": round(seg_start, 3),
                    "end": round(min(c["end"], seg_end), 3),
                    "text": seg_text,
                })
            seg_start = c["start"] + dur * cut / n
            pos = cut

    return final


def _is_cjk(ch: str) -> bool:
    """单字 CJK 判定。含 CJK 统一表意、CJK Extension A/B、全角 ASCII 标点。"""
    if not ch:
        return False
    o = ord(ch)
    return (
        0x3000 <= o <= 0x303F   # CJK Symbols and Punctuation（含 ， 。 、 「 」 ！ ？ ： ；）
        or 0x4E00 <= o <= 0x9FFF
        or 0x3400 <= o <= 0x4DBF
        or 0x20000 <= o <= 0x2A6DF
        or 0x2A700 <= o <= 0x2B73F
        or 0x2B740 <= o <= 0x2B81F
        or 0x2B820 <= o <= 0x2CEAF
        or 0xF900 <= o <= 0xFAFF
        or 0xFF00 <= o <= 0xFFEF  # 全角 ASCII
    )


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

    # sherpa-onnx X-ASR raw text 有时候会留下「汉字 汉字」中的多余空格
    # （不像 token 那样有 lstrip）。按 CJK 边界扫一遍，归一化为「汉字汉字」。
    text = re.sub(rf"(?<=[{_CJK_RANGES}])\s+(?=[{_CJK_RANGES}])", "", text)

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