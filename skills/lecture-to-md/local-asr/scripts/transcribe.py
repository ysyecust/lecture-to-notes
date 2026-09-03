#!/usr/bin/env python3
"""本地音视频转写统一入口（sherpa-onnx X-ASR，中英双语）。

**默认复用上游 `scripts/transcribe_x_asr.py`** 作为后端（它有 30s 分块 +
低能量切分 + 时间戳拼接 + 单测）。仅在子 skill 被单独拷贝到上游 repo 之外
（找不到上游脚本）时才走内置 `asr_x.py` 路径——内置路径只适合短音频，
长音频请确保用上游后端。

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
# 子 skill 在 lecture-to-md/ 之下；上游脚本在 lecture-to-notes/scripts/
# 即 SCRIPT_DIR = skills/lecture-to-md/local-asr/scripts/
#     ../../../../scripts/transcribe_x_asr.py
SKILL_DIR = os.path.dirname(SCRIPT_DIR)              # local-asr
SUBBUNDLE_DIR = os.path.dirname(SKILL_DIR)           # lecture-to-md
SKILLS_DIR = os.path.dirname(SUBBUNDLE_DIR)          # skills
REPO_ROOT = os.path.dirname(SKILLS_DIR)              # lecture-to-notes repo root
UPSTREAM_SCRIPT = os.path.join(REPO_ROOT, "scripts", "transcribe_x_asr.py")

LANG_ALIASES = {
    "zh": "zh", "chinese": "zh", "中文": "zh",
    "en": "en", "english": "en", "英文": "en",
    "auto": "auto",
}

DEFAULT_FORMATS = "txt,md"

# 字幕条合并阈值（仅内置后端路径用）
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
        description=(
            "本地转写：sherpa-onnx X-ASR（中英双语）。"
            "默认复用上游 scripts/transcribe_x_asr.py 后端（含 30s 分块、低能量切分、时间戳拼接）。"
        )
    )
    ap.add_argument("input", help="视频或音频文件路径")
    ap.add_argument("--lang", "-l", default="zh",
                    help="语言：zh（默认）| en | auto")
    ap.add_argument("--output-dir", "-o", default=None,
                    help="输出目录，默认与源文件同目录")
    ap.add_argument("--model-dir", default=None,
                    help="X-ASR 模型目录（覆盖 ASR_MODEL_DIR 与默认缓存位置）")
    ap.add_argument("--backend", choices=["auto", "upstream", "builtin"],
                    default="auto",
                    help="auto=优先上游 backend，找不到则 builtin；"
                         "upstream=强制上游（缺则报错）；"
                         "builtin=只用本 skill 自带的 asr_x.py（仅适合短音频）")
    ap.add_argument("--num-threads", type=int, default=4, help="推理线程数")
    ap.add_argument("--formats", default=DEFAULT_FORMATS,
                    help="输出格式组合，逗号分隔：txt,md,json,srt,vtt（默认 txt,md）")
    ap.add_argument("--keep-audio", action="store_true", help="保留中间 16k wav")
    ap.add_argument("--timestamps", action="store_true",
                    help="保留时间戳，产出 srt/vtt 字幕（上游 backend 默认就有，builtin 需要 token）")
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


def has_upstream_backend() -> bool:
    return os.path.isfile(UPSTREAM_SCRIPT)


def resolve_model_dir(explicit: str | None = None) -> str:
    """定位 X-ASR 模型目录：CLI 参数 > 环境变量 > 默认缓存目录。"""
    if explicit:
        if not os.path.isdir(explicit):
            sys.exit(f"[asr] 找不到模型目录: {explicit}\n先跑 bash scripts/setup.sh 下载。")
        return os.path.abspath(explicit)
    env_dir = os.environ.get("ASR_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)
    default = os.path.expanduser(
        "~/.cache/sherpa-onnx-models/"
        "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
    )
    if os.path.isdir(default):
        return default
    sys.exit(
        f"[asr] 模型未下载。先跑 bash scripts/setup.sh（Windows 见 SKILL.md 「Windows 设置」）。\n"
        f"或者 --model-dir <dir> 指向已解压好的 X-ASR 目录。"
    )


# -------------------- 上游 backend --------------------

def parse_srt(srt_text: str) -> list[dict]:
    """极简 SRT 解析：list of {index, start, end, text}。"""
    cues: list[dict] = []
    blocks = re.split(r"\n\s*\n", srt_text.strip())
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        m = re.match(r"(\S+)\s*-->\s*(\S+)", lines[1])
        if not m:
            continue
        start = _srt_ts_to_seconds(m.group(1))
        end = _srt_ts_to_seconds(m.group(2))
        text = "\n".join(lines[2:]).strip()
        if text and end > start:
            cues.append({"index": lines[0], "start": start, "end": end, "text": text})
    return cues


def _srt_ts_to_seconds(ts: str) -> float:
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        return 0.0
    return int(h) * 3600 + int(m) * 60 + float(s)


def run_upstream(args, src, info, out_dir, stem, formats, targets, model_dir):
    """调用上游 scripts/transcribe_x_asr.py，解析其 SRT，再产出多种格式。"""
    with tempfile.TemporaryDirectory(prefix="asr-upstream-") as tmp:
        srt_path = os.path.join(tmp, f"{stem}.srt")
        report_path = os.path.join(tmp, "report.json")
        cmd = [
            sys.executable, UPSTREAM_SCRIPT, src,
            "--output", srt_path,
            "--report", report_path,
            "--model-dir", model_dir,
            "--threads", str(args.num_threads),
            "--max-chunk-seconds", "30.0",
            "--chunk-seconds", "27.0",
            "--min-chunk-seconds", "20.0",
        ]
        print(f"[asr] 后端: upstream ({UPSTREAM_SCRIPT})", flush=True)
        print("[asr] 开始转写（长音频请耐心等待，分块上限 30s）...", flush=True)
        proc = subprocess.run(cmd, cwd=tmp)
        if proc.returncode != 0:
            sys.exit(f"[asr] 上游 backend 转写失败，退出码 {proc.returncode}")

        with open(srt_path, encoding="utf-8") as f:
            cues = parse_srt(f.read())
        report = {}
        if os.path.isfile(report_path):
            try:
                with open(report_path, encoding="utf-8") as f:
                    report = json.load(f)
            except Exception:
                report = {}

    if not cues:
        sys.exit("[asr] 没有识别出任何内容，请检查音频轨是否存在。")

    # 由 SRT 拼出完整文字
    text = "\n".join(c["text"] for c in cues).strip()
    # 归一化「汉字 汉字」中间的空格
    text = re.sub(rf"(?<=[{_CJK_RANGES}])\s+(?=[{_CJK_RANGES}])", "", text)

    written = []
    for fmt in formats:
        path = targets[fmt]
        if fmt == "txt":
            write_plain_txt(text, path)
        elif fmt == "md":
            write_plain_md(text, path, title=stem, source=src)
        elif fmt == "srt":
            # 直接把上游的 SRT 拷过去（保持一致）
            with open(path, "w", encoding="utf-8") as f:
                _write_cues_as_srt(cues, f)
        elif fmt == "vtt":
            with open(path, "w", encoding="utf-8") as f:
                f.write("WEBVTT\n\n")
                for c in cues:
                    f.write(f"{fmt_ts_srt(c['start']).replace(',', '.')} --> "
                            f"{fmt_ts_srt(c['end']).replace(',', '.')}\n{c['text']}\n\n")
        elif fmt == "json":
            meta = {
                "source": src,
                "language": args.lang,
                "backend": "sherpa-onnx-x-asr (upstream)",
                "model": model_dir,
                "duration": report.get("audio_seconds") or info["duration"],
                "chunks": report.get("chunks"),
                "cues": len(cues),
                "decode_seconds": report.get("decode_seconds"),
                "rtf": report.get("rtf"),
                "sherpa_onnx_version": report.get("sherpa_onnx_version"),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"meta": meta, "text": text, "cues": cues}, f,
                          ensure_ascii=False, indent=2)
        else:
            continue
        written.append(path)

    duration = report.get("audio_seconds") or info["duration"]
    chunks = report.get("chunks", "?")
    print(f"[asr] 完成：{len(text)} 字 / {len(cues)} cues / {chunks} chunks / "
          f"{duration:.1f}s audio (上游 backend)")
    for path in written:
        print(f"  - {path}")
    return 0


def _write_cues_as_srt(cues: list[dict], f) -> None:
    for i, c in enumerate(cues, 1):
        f.write(f"{i}\n{fmt_ts_srt(c['start'])} --> {fmt_ts_srt(c['end'])}\n"
                f"{c['text']}\n\n")


# -------------------- 内置 backend（fallback） --------------------

def tokens_to_cues(tokens, timestamps, text, cjk):
    """从 sherpa-onnx 输出的 token+timestamp 重构字幕条（内置后端路径）。"""
    if not tokens or not timestamps or len(tokens) != len(timestamps):
        return []

    sentences: list[str] = []
    buf: list[str] = []
    for i, ch in enumerate(text):
        buf.append(ch)
        end_sentence = ch in SENT_END
        if ch == ".":
            nxt = text[i + 1] if i + 1 < len(text) else ""
            end_sentence = (nxt == "" or nxt.isspace())
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

    char_to_token: list[int] = []
    for tok_idx, tok in enumerate(tokens):
        content = tok.lstrip(" \u2581")
        for _ in content:
            char_to_token.append(tok_idx)
    if not char_to_token:
        return []

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
        if end_idx == last_token_idx:
            end_ts = end_ts + 0.3
        cues.append({"start": round(start_ts, 3),
                     "end": round(end_ts, 3),
                     "text": sent})

    return cues


def run_builtin(args, src, info, out_dir, stem, formats, targets, model_dir):
    """走内置 asr_x.py：短音频 OK，长音频可能爆（受 30s 上限制约）。"""
    if info["duration"] > 60 and "upstream" not in args.backend:
        sys.exit(
            f"[asr] 内置 backend 不支持长音频（{info['duration']:.0f}s > 60s）。\n"
            f"  请确认 upstream backend 可用（默认情况下会自动走 upstream），\n"
            f"  或显式 --backend upstream 强制；找不到时检查 {UPSTREAM_SCRIPT}"
            )

    keep = args.keep_audio
    wav, workdir = prepare_audio(src)
    print(f"[asr] 后端: builtin (asr_x.py)", flush=True)
    print(f"[asr] 音频: {wav}")

    with tempfile.TemporaryDirectory(prefix="asr-result-") as tmp:
        result_json = os.path.join(tmp, "result.json")
        cmd = [
            sys.executable, os.path.join(SCRIPT_DIR, "asr_x.py"), wav,
            "--out", result_json,
            "--language", args.lang,
            "--num-threads", str(args.num_threads),
            "--model-dir", model_dir,
        ]
        print("[asr] 开始转写（内置后端单次推理）...", flush=True)
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
                        "language": payload.get("language", args.lang),
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
            with open(path, "w", encoding="utf-8") as f:
                if fmt == "srt":
                    _write_cues_as_srt(cues, f)
                else:
                    f.write("WEBVTT\n\n")
                    for c in cues:
                        f.write(f"{fmt_ts_srt(c['start']).replace(',', '.')} --> "
                                f"{fmt_ts_srt(c['end']).replace(',', '.')}\n{c['text']}\n\n")
        else:
            continue
        written.append(path)

    print(f"[asr] 完成：{len(text)} 字 / 模型 {payload.get('model', '?')}"
          f" / provider {payload.get('provider', '?')} (内置 backend)")
    for path in written:
        print(f"  - {path}")
    return 0


# -------------------- main --------------------

def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    src = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.isfile(src):
        sys.exit(f"[asr] 文件不存在: {src}")

    args.lang = normalize_lang(args.lang)

    info = probe(src)
    print(f"[asr] 源文件: {src}")
    print(f"[asr] 时长: {fmt_ts_short(info['duration'])} | 音频轨: {info['has_audio']} "
          f"| 语言: {args.lang}")

    out_dir = os.path.abspath(os.path.expanduser(
        args.output_dir if args.output_dir else os.path.dirname(src)))
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    # 没显式 --formats、只给了 --timestamps：顺带出 srt（vtt 保留为可选）
    if args.timestamps and args.formats == DEFAULT_FORMATS:
        formats = ["txt", "md", "srt"]
    if any(f in ("srt", "vtt") for f in formats) and not args.timestamps:
        sys.exit("[asr] 输出 srt/vtt 需要加 --timestamps")

    targets = {f: os.path.join(out_dir, f"{stem}.{f}") for f in formats}
    if not args.overwrite:
        clash = [p for p in targets.values() if os.path.exists(p)]
        if clash:
            sys.exit("[asr] 已存在输出文件（加 --overwrite 覆盖）:\n  " + "\n  ".join(clash))

    model_dir = resolve_model_dir(args.model_dir)

    # backend 选择
    if args.backend == "upstream":
        if not has_upstream_backend():
            sys.exit(f"[asr] --backend upstream 但找不到 {UPSTREAM_SCRIPT}")
        chosen = "upstream"
    elif args.backend == "builtin":
        chosen = "builtin"
    else:  # auto
        chosen = "upstream" if has_upstream_backend() else "builtin"
    print(f"[asr] backend: {chosen}")

    if chosen == "upstream":
        return run_upstream(args, src, info, out_dir, stem, formats, targets, model_dir)
    return run_builtin(args, src, info, out_dir, stem, formats, targets, model_dir)


if __name__ == "__main__":
    sys.exit(main())
