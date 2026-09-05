#!/usr/bin/env python3
"""本地音视频转写统一入口（sherpa-onnx X-ASR，中英双语）。

转写、分块和字幕时间轴都由同目录的 transcribe_x_asr.py 完成；本文件只负责
CLI、模型/音频准备，以及把结果写成 txt / md / json / srt / vtt。
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
    child_env,
    configure_utf8,
    fmt_ts_short,
    fmt_ts_srt,
    prepare_audio,
    probe,
    resolve_model_dir,
    write_plain_md,
    write_plain_txt,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_SCRIPT = os.path.join(SCRIPT_DIR, "transcribe_x_asr.py")

LANG_ALIASES = {
    "zh": "zh", "chinese": "zh", "中文": "zh",
    "en": "en", "english": "en", "英文": "en",
    "auto": "auto",
}
DEFAULT_FORMATS = "txt,md"

# CJK 字符范围（用于去除「汉字 汉字」中的多余空格）
_CJK_RANGES = (
    "\u3000-\u303F"
    "\u4E00-\u9FFF"
    "\u3400-\u4DBF"
    "\U00020000-\U0002A6DF"
    "\uF900-\uFAFF"
    "\uFF00-\uFFEF"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=(
            "本地转写：sherpa-onnx X-ASR（中英双语，内置 30s 分块和 token 时间戳）。"
        )
    )
    ap.add_argument("input", help="视频或音频文件路径")
    ap.add_argument("--lang", "-l", default="zh", help="语言：zh（默认）| en | auto")
    ap.add_argument("--output-dir", "-o", default=None,
                    help="输出目录，默认与源文件同目录")
    ap.add_argument("--model-dir", default=None,
                    help="X-ASR 模型目录（覆盖 ASR_MODEL_DIR 与默认缓存位置）")
    ap.add_argument("--provider", choices=["cpu", "cuda"], default=None,
                    help="推理 provider；默认按平台自动选择")
    ap.add_argument("--num-threads", type=int, default=4, help="推理线程数")
    ap.add_argument("--formats", default=DEFAULT_FORMATS,
                    help="输出格式组合，逗号分隔：txt,md,json,srt,vtt（默认 txt,md）")
    ap.add_argument("--keep-audio", action="store_true", help="保留中间 16k wav")
    ap.add_argument("--timestamps", action="store_true",
                    help="写出 srt/vtt 字幕时间轴")
    ap.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的输出文件")
    return ap.parse_args(argv)


def normalize_lang(value: str) -> str:
    key = (value or "zh").strip().lower()
    return LANG_ALIASES.get(key, key if key in ("zh", "en", "auto") else "zh")


def _srt_ts_to_seconds(ts: str) -> float:
    parts = ts.replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        return 0.0
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_srt(srt_text: str) -> list[dict]:
    """解析本地 X-ASR backend 产出的 SRT。"""
    cues: list[dict] = []
    blocks = re.split(r"\n\s*\n", srt_text.strip())
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = re.match(r"(\S+)\s*-->\s*(\S+)", lines[1])
        if not match:
            continue
        start = _srt_ts_to_seconds(match.group(1))
        end = _srt_ts_to_seconds(match.group(2))
        text = "\n".join(lines[2:]).strip()
        if text and end > start:
            cues.append({"index": lines[0], "start": start, "end": end, "text": text})
    return cues


def _write_cues_as_srt(cues: list[dict], stream) -> None:
    for index, cue in enumerate(cues, 1):
        stream.write(
            f"{index}\n{fmt_ts_srt(cue['start'])} --> {fmt_ts_srt(cue['end'])}\n"
            f"{cue['text']}\n\n"
        )


def run_transcriber(args, src, info, stem, formats, targets, model_dir):
    model_dir = resolve_model_dir(model_dir)
    backend_input = src
    if args.keep_audio:
        backend_input, _ = prepare_audio(src)

    with tempfile.TemporaryDirectory(prefix="asr-result-") as tmp:
        srt_path = os.path.join(tmp, f"{stem}.srt")
        report_path = os.path.join(tmp, "report.json")
        cmd = [
            sys.executable, BACKEND_SCRIPT, backend_input,
            "--output", srt_path,
            "--report", report_path,
            "--model-dir", model_dir,
            "--threads", str(args.num_threads),
            "--lang", args.lang,
        ]
        if args.provider:
            cmd += ["--provider", args.provider]
        print(f"[asr] backend: {BACKEND_SCRIPT}", flush=True)
        print("[asr] 开始转写（每块不超过 30s）...", flush=True)
        proc = subprocess.run(cmd, cwd=tmp, env=child_env())
        if proc.returncode != 0:
            sys.exit(f"[asr] X-ASR 转写失败，退出码 {proc.returncode}")

        with open(srt_path, encoding="utf-8") as stream:
            cues = parse_srt(stream.read())
        report = {}
        if os.path.isfile(report_path):
            with open(report_path, encoding="utf-8") as stream:
                report = json.load(stream)

    if not cues:
        sys.exit("[asr] 没有识别出任何内容，请检查音频轨是否存在。")

    text = "\n".join(cue["text"] for cue in cues).strip()
    text = re.sub(rf"(?<=[{_CJK_RANGES}])\s+(?=[{_CJK_RANGES}])", "", text)

    written = []
    for fmt in formats:
        path = targets[fmt]
        if fmt == "txt":
            write_plain_txt(text, path)
        elif fmt == "md":
            write_plain_md(text, path, title=stem, source=src)
        elif fmt == "srt":
            with open(path, "w", encoding="utf-8") as stream:
                _write_cues_as_srt(cues, stream)
        elif fmt == "vtt":
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("WEBVTT\n\n")
                for cue in cues:
                    stream.write(
                        f"{fmt_ts_srt(cue['start']).replace(',', '.')} --> "
                        f"{fmt_ts_srt(cue['end']).replace(',', '.')}\n"
                        f"{cue['text']}\n\n"
                    )
        elif fmt == "json":
            meta = {
                "source": src,
                "language": args.lang,
                "backend": report.get("backend", "sherpa-onnx-x-asr"),
                "model": report.get("model", model_dir),
                "provider": report.get("provider"),
                "duration": report.get("audio_seconds") or info["duration"],
                "chunks": report.get("chunks"),
                "cues": len(cues),
                "decode_seconds": report.get("decode_seconds"),
                "rtf": report.get("rtf"),
                "sherpa_onnx_version": report.get("sherpa_onnx_version"),
            }
            with open(path, "w", encoding="utf-8") as stream:
                json.dump({
                    "meta": meta,
                    "text": text,
                    "cues": cues,
                    "tokens": report.get("tokens", []),
                    "timestamps": report.get("timestamps", []),
                },
                          stream, ensure_ascii=False, indent=2)
        else:
            continue
        written.append(path)

    duration = report.get("audio_seconds") or info["duration"]
    print(f"[asr] 完成：{len(text)} 字 / {len(cues)} cues / "
          f"{report.get('chunks', '?')} chunks / {duration:.1f}s audio")
    for path in written:
        print(f"  - {path}")
    return 0


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
    if args.timestamps and args.formats == DEFAULT_FORMATS:
        formats = ["txt", "md", "srt"]
    if any(fmt in ("srt", "vtt") for fmt in formats) and not args.timestamps:
        sys.exit("[asr] 输出 srt/vtt 需要加 --timestamps")

    targets = {fmt: os.path.join(out_dir, f"{stem}.{fmt}") for fmt in formats}
    if not args.overwrite:
        clash = [path for path in targets.values() if os.path.exists(path)]
        if clash:
            sys.exit("[asr] 已存在输出文件（加 --overwrite 覆盖）：\n  " +
                     "\n  ".join(clash))

    return run_transcriber(
        args, src, info, stem, formats, targets, args.model_dir
    )


if __name__ == "__main__":
    configure_utf8()
    sys.exit(main())
