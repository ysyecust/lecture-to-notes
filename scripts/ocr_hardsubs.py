#!/usr/bin/env python3
"""
Burned-in (hard) subtitle OCR: detect, extract to SRT, and derive a Whisper glossary.

Many Bilibili lectures ship with subtitles burned into the picture. Reading that
band with OCR gives a transcript with the speaker's own spelling of every term,
which beats speech-to-text on homophones (刻蚀 vs 刻石, 光掩膜 vs 光眼膜).

Subcommands:
    detect   video.mp4 [--samples 12]
        Sample frames across the video, OCR the subtitle band, print JSON with
        `has_hardsubs` and `hit_ratio`. Exit 0 when hard subs are present, 1 otherwise.
    extract  video.mp4 --out hardsub_ocr.srt [--fps 1] [--band 0.80:0.97] [--workdir DIR]
        OCR the band at `fps`, merge consecutive frames with the same text, write SRT.
    glossary hardsub_ocr.srt audio.srt --out glossary_auto.json [--window 3] [--min-count 2]
        Align the OCR track with a Whisper track and emit `wrong → right` pairs for
        correct_srt.py.

OCR backend: rapidocr-onnxruntime (`pip install rapidocr-onnxruntime`). ffmpeg and
ffprobe must be on PATH for `detect` and `extract`.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

CJK = re.compile(r"[一-鿿]")
DEFAULT_IGNORE = r"bilibili|bilibil|blibili|^@|谈三圈"
TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


# ---------------------------------------------------------------- SRT helpers
def parse_srt(text: str) -> list[dict]:
    """Parse SRT text into [{start, end, text}] with float seconds."""
    entries = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue
        match = TIME_RE.search(lines[1]) or TIME_RE.search(lines[0])
        if not match:
            continue
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in match.groups())
        start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
        end = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
        body_index = 2 if TIME_RE.search(lines[1]) else 1
        body = " ".join(lines[body_index:]).strip()
        if body:
            entries.append({"start": start, "end": end, "text": body})
    return entries


def _stamp(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_srt(entries: list[dict]) -> str:
    out = []
    for i, entry in enumerate(entries, 1):
        out.append(f"{i}\n{_stamp(entry['start'])} --> {_stamp(entry['end'])}\n{entry['text']}\n")
    return "\n".join(out) + ("\n" if out else "")


# ---------------------------------------------------------------- OCR helpers
def normalize(text: str) -> str:
    """Strip whitespace and punctuation so OCR jitter does not split entries."""
    return re.sub(r"[\s，。、；：！？,.;:!?\"'“”‘’()（）\[\]【】—–\-_|‖·]+", "", text)


def clean_lines(lines: list[str], ignore: re.Pattern, min_chars: int = 2) -> list[str]:
    kept = []
    for line in lines:
        line = line.strip()
        if len(normalize(line)) < min_chars or ignore.search(line):
            continue
        kept.append(line)
    return kept


def load_ocr(with_boxes: bool = False):
    """
    Return an OCR callable backed by rapidocr-onnxruntime.

    Plain mode maps path -> list[str]; box mode maps path -> list[(text, y0, y1)]
    with pixel rows of each text box, used for band geometry.
    """
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore
    except ImportError as error:  # pragma: no cover - environment dependent
        raise SystemExit(
            "rapidocr-onnxruntime is required for OCR: pip install rapidocr-onnxruntime"
        ) from error
    engine = RapidOCR()

    def run(path: str):
        result, _ = engine(path)
        if not result:
            return []
        if not with_boxes:
            return [item[1] for item in result]
        boxes = []
        for box, text, _ in result:
            ys = [int(point[1]) for point in box]
            boxes.append((text, min(ys), max(ys)))
        return boxes

    return run


def probe_video(video: str, ffprobe: str = "ffprobe") -> tuple[float, int]:
    """Return (duration_seconds, height_pixels) of the first video stream."""
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries",
         "format=duration:stream=height", "-of", "json", video],
        capture_output=True, text=True, check=True,
    ).stdout
    data = json.loads(out)
    height = int(data["streams"][0]["height"]) if data.get("streams") else 0
    return float(data["format"]["duration"]), height


def probe_duration(video: str, ffprobe: str = "ffprobe") -> float:
    return probe_video(video, ffprobe)[0]


def band_geometry(
    frame_boxes: list[list[tuple[str, int, int]]],
    height: int,
    ignore: re.Pattern,
    bottom_frac: float = 0.35,
    static_share: float = 0.8,
    frame_share: float = 0.5,
) -> dict:
    """
    Derive overlay geometry from OCR boxes sampled across the video.

    Static text (same text, same rows, in >= `static_share` of frames) in the bottom
    of the picture is a navigation strip. Changing text in the bottom `bottom_frac`
    that appears in >= `frame_share` of frames is the burned-in subtitle band. The
    result is consumed by `frame_filter.py crop --bands`.
    """
    n = len(frame_boxes)
    if n == 0 or height <= 0:
        return {"height": height, "nav_strip": 0, "subtitle_band": None, "crop_bottom": 0, "frames": 0}
    lower = height * (1 - bottom_frac)
    static_counts: Counter = Counter()
    for boxes in frame_boxes:
        seen = set()
        for text, y0, y1 in boxes:
            key = (normalize(text), y0 // 8, y1 // 8)
            if key[0] and key not in seen and y0 >= height * 0.85:
                seen.add(key)
                static_counts[key] += 1
    static_keys = {key for key, count in static_counts.items() if count / n >= static_share}
    nav_top = height
    for key in static_keys:
        nav_top = min(nav_top, key[1] * 8)
    nav_strip = height - nav_top if nav_top < height else 0

    frames_with_subs = 0
    y0s: list[int] = []
    y1s: list[int] = []
    for boxes in frame_boxes:
        found = False
        for text, y0, y1 in boxes:
            key = (normalize(text), y0 // 8, y1 // 8)
            if key in static_keys or ignore.search(text) or len(normalize(text)) < 2:
                continue
            if y0 >= lower and y1 <= height - nav_strip + 2:
                y0s.append(y0)
                y1s.append(y1)
                found = True
        frames_with_subs += found
    band = None
    if y0s and frames_with_subs / n >= frame_share:
        y0s.sort()
        y1s.sort()
        lo = y0s[int(len(y0s) * 0.1)]
        hi = y1s[int(len(y1s) * 0.9) - 1] if len(y1s) > 1 else y1s[-1]
        pad = max(4, (hi - lo) // 8)
        band = [max(int(lower), lo - pad), min(height - nav_strip, hi + pad)]
    crop_bottom = height - band[0] if band else nav_strip
    return {"height": height, "nav_strip": int(nav_strip), "subtitle_band": band,
            "crop_bottom": int(crop_bottom), "frames": n,
            "subtitle_frame_share": round(frames_with_subs / n, 3)}


def sample_band_frames(
    video: str,
    out_dir: Path,
    fps: float,
    band: tuple[float, float],
    start: float | None = None,
    duration: float | None = None,
    ffmpeg: str = "ffmpeg",
) -> list[tuple[float, str]]:
    """Extract the subtitle band at `fps`; return [(time_seconds, frame_path)]."""
    out_dir.mkdir(parents=True, exist_ok=True)
    top, bottom = band
    crop = f"crop=iw:ih*{bottom - top:.4f}:0:ih*{top:.4f}"
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", video]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vf", f"fps={fps},{crop}", "-q:v", "3", str(out_dir / "%06d.jpg")]
    subprocess.run(cmd, check=True)
    frames = sorted(out_dir.glob("*.jpg"))
    offset = start or 0.0
    return [(offset + (i / fps), str(p)) for i, p in enumerate(frames)]


# ---------------------------------------------------------------- core logic
def assess_hits(results: list[list[str]], ignore: re.Pattern, min_chars: int = 2, threshold: float = 0.5) -> dict:
    """Decide whether sampled OCR results indicate burned-in subtitles."""
    hits = sum(1 for lines in results if clean_lines(lines, ignore, min_chars))
    ratio = hits / len(results) if results else 0.0
    return {"samples": len(results), "hits": hits, "hit_ratio": round(ratio, 3), "has_hardsubs": ratio >= threshold}


def extract_entries(
    frames: list[tuple[float, str]],
    ocr,
    fps: float,
    ignore: re.Pattern,
    min_chars: int = 2,
    similarity: float = 0.85,
) -> list[dict]:
    """OCR each band frame and merge runs of identical text into SRT entries."""
    entries: list[dict] = []
    current: dict | None = None
    step = 1.0 / fps
    for t, path in frames:
        lines = clean_lines(ocr(path), ignore, min_chars)
        text = " ".join(lines)
        key = normalize(text)
        if not key:
            if current is not None:
                entries.append(current)
                current = None
            continue
        if current is not None:
            ratio = difflib.SequenceMatcher(None, current["key"], key).ratio()
            if ratio >= similarity:
                current["end"] = t + step
                current["votes"][text] += 1
                continue
            entries.append(current)
        current = {"start": t, "end": t + step, "key": key, "votes": Counter({text: 1})}
    if current is not None:
        entries.append(current)
    out = []
    for entry in entries:
        # The most frequent OCR reading of the run is the most reliable one.
        text = entry["votes"].most_common(1)[0][0]
        out.append({"start": entry["start"], "end": entry["end"], "text": text})
    return out


def build_glossary(
    whisper_entries: list[dict],
    ocr_entries: list[dict],
    window: float = 3.0,
    min_count: int = 2,
    max_len: int = 4,
    min_ratio: float = 0.5,
) -> tuple[dict[str, str], dict]:
    """
    Align Whisper entries to the OCR track and collect `wrong → right` replacements.

    Only short, CJK-bearing substitutions are kept so the glossary corrects terms
    (刻石→刻蚀) without rewriting whole sentences.
    """
    counts: Counter = Counter()
    aligned = 0
    for w in whisper_entries:
        candidates = [
            o for o in ocr_entries
            if o["end"] >= w["start"] - window and o["start"] <= w["end"] + window
        ]
        if not candidates:
            continue
        w_key = normalize(w["text"])
        best = max(candidates, key=lambda o: difflib.SequenceMatcher(None, w_key, normalize(o["text"])).ratio())
        o_key = normalize(best["text"])
        matcher = difflib.SequenceMatcher(None, w_key, o_key)
        if matcher.ratio() < min_ratio:
            continue
        aligned += 1
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "replace":
                continue
            wrong, right = w_key[i1:i2], o_key[j1:j2]
            if not (0 < len(wrong) <= max_len and 0 < len(right) <= max_len):
                continue
            if not (CJK.search(wrong) or CJK.search(right)):
                continue
            counts[(wrong, right)] += 1
    # For each wrong string keep the majority right string.
    best_for: dict[str, tuple[str, int]] = {}
    for (wrong, right), n in counts.items():
        if n >= min_count and (wrong not in best_for or n > best_for[wrong][1]):
            best_for[wrong] = (right, n)
    glossary = {wrong: right for wrong, (right, _) in sorted(best_for.items(), key=lambda kv: -kv[1][1])}
    stats = {"whisper_entries": len(whisper_entries), "aligned": aligned, "pairs": len(glossary),
             "counts": {f"{w}→{r}": n for (w, r), n in counts.most_common(50)}}
    return glossary, stats


# ---------------------------------------------------------------- CLI
def _band(text: str) -> tuple[float, float]:
    top, bottom = (float(x) for x in text.split(":"))
    if not 0 <= top < bottom <= 1:
        raise argparse.ArgumentTypeError("band must be TOP:BOTTOM fractions with 0 <= TOP < BOTTOM <= 1")
    return top, bottom


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser("detect", help="check whether the video has burned-in subtitles")
    p_detect.add_argument("video")
    p_detect.add_argument("--samples", type=int, default=12)
    p_detect.add_argument("--band", type=_band, default=(0.80, 0.97))
    p_detect.add_argument("--ignore", default=DEFAULT_IGNORE, help="regex for watermark/logo lines to drop")
    p_detect.add_argument("--geometry", default=None, metavar="BANDS_JSON",
                          help="also OCR full frames and write overlay geometry for frame_filter.py crop --bands")

    p_extract = sub.add_parser("extract", help="OCR the subtitle band into an SRT")
    p_extract.add_argument("video")
    p_extract.add_argument("--out", required=True)
    p_extract.add_argument("--fps", type=float, default=1.0)
    p_extract.add_argument("--band", type=_band, default=(0.80, 0.97))
    p_extract.add_argument("--ignore", default=DEFAULT_IGNORE)
    p_extract.add_argument("--workdir", default=None, help="keep band frames here (default: temp dir)")
    p_extract.add_argument("--start", type=float, default=None)
    p_extract.add_argument("--duration", type=float, default=None)

    p_gloss = sub.add_parser("glossary", help="derive wrong→right pairs from OCR vs Whisper tracks")
    p_gloss.add_argument("ocr_srt")
    p_gloss.add_argument("whisper_srt")
    p_gloss.add_argument("--out", required=True)
    p_gloss.add_argument("--window", type=float, default=3.0)
    p_gloss.add_argument("--min-count", type=int, default=2)
    p_gloss.add_argument("--max-len", type=int, default=4)

    args = parser.parse_args(argv)

    if args.command == "glossary":
        ocr_entries = parse_srt(Path(args.ocr_srt).read_text(encoding="utf-8"))
        whisper_entries = parse_srt(Path(args.whisper_srt).read_text(encoding="utf-8"))
        glossary, stats = build_glossary(whisper_entries, ocr_entries, args.window, args.min_count, args.max_len)
        Path(args.out).write_text(json.dumps(glossary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in stats.items() if k != "counts"}, ensure_ascii=False))
        for pair, n in list(stats["counts"].items())[:20]:
            print(f"  {n:3d}  {pair}")
        print(f"wrote {len(glossary)} pairs to {args.out}")
        return 0

    ignore = re.compile(args.ignore)
    if args.command == "detect":
        duration, height = probe_video(args.video)
        ocr = load_ocr(with_boxes=bool(args.geometry))
        results = []
        frame_boxes = []
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(args.samples):
                t = duration * (i + 0.5) / args.samples
                band = (0.0, 1.0) if args.geometry else args.band
                frames = sample_band_frames(args.video, Path(tmp) / f"s{i}", 1.0, band, start=t, duration=0.5)
                raw = ocr(frames[0][1]) if frames else []
                if args.geometry:
                    frame_boxes.append(raw)
                    band_top = height * args.band[0]
                    results.append([text for text, y0, _ in raw if y0 >= band_top])
                else:
                    results.append(raw)
        verdict = assess_hits(results, ignore)
        if args.geometry:
            geometry = band_geometry(frame_boxes, height, ignore)
            verdict["geometry"] = geometry
            Path(args.geometry).write_text(json.dumps(geometry) + "\n", encoding="utf-8")
        print(json.dumps(verdict, ensure_ascii=False))
        return 0 if verdict["has_hardsubs"] else 1
    ocr = load_ocr()

    if args.command == "extract":
        keep = Path(args.workdir) if args.workdir else None
        with tempfile.TemporaryDirectory() as tmp:
            frame_dir = keep or Path(tmp) / "band"
            frames = sample_band_frames(args.video, frame_dir, args.fps, args.band, args.start, args.duration)
            entries = extract_entries(frames, ocr, args.fps, ignore)
        Path(args.out).write_text(format_srt(entries), encoding="utf-8")
        print(f"frames={len(frames)} entries={len(entries)} srt={args.out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
