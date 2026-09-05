#!/usr/bin/env python3
"""
Numerical-claim ledger: extract every number the lecture states, then check the notes.

The model should not be the one deciding which numbers exist in the source. This
script builds `numerical_claims.tsv` from the subtitle track (and optional OCR
tracks of on-screen text) so the writer only has to discharge each row.

Subcommands:
    extract audio.srt [--ocr hardsubs.srt ...] --out numerical_claims.tsv
        Columns: claim \t value \t source_time \t in_notes (left empty).
    check numerical_claims.tsv notes.tex [--write]
        Fill `in_notes` with yes/no by loose matching against the LaTeX body
        (spacing macros, math delimiters, and unit macros are stripped first).
        Exit 1 when any row is `no`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

UNITS = (
    r"纳米|微米|毫米|厘米|英寸|英尺|公里|千米|埃|摄氏度|℃|度|倍|亿美元|亿元|万美元|万元|亿|万|千|百|美元|元|"
    r"年|个月|月|天|小时|分钟|秒|毫秒|层|步|种|片|吨|克|公斤|千克|米|寸|次|张|台|颗|位|条|款|家|人|"
    r"%|％|nm|μm|um|mm|cm|km|GHz|MHz|kHz|Hz|TB|GB|MB|KB|ms|K|W|kW|MW|V|A|mA|ppm|ppb|x|X|×"
)
NUMBER = r"\d+(?:[.,]\d+)*"
CLAIM_RE = re.compile(
    rf"({NUMBER}(?:\s*[-–~到至]\s*{NUMBER})?)\s*({UNITS})(?![A-Za-z])"
)
TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->")
HEADER = "claim\tvalue\tsource_time\tin_notes"


def parse_srt(text: str) -> list[tuple[float, str]]:
    entries = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        if len(lines) < 2:
            continue
        match = TIME_RE.search(lines[1]) or TIME_RE.search(lines[0])
        if not match:
            continue
        h, m, s, ms = (int(x) for x in match.groups())
        body_index = 2 if TIME_RE.search(lines[1]) else 1
        body = " ".join(lines[body_index:]).strip()
        if body:
            entries.append((h * 3600 + m * 60 + s + ms / 1000, body))
    return entries


def _mmss(seconds: float) -> str:
    total = int(seconds)
    if total >= 3600:
        return f"{total // 3600}:{total % 3600 // 60:02d}:{total % 60:02d}"
    return f"{total // 60:02d}:{total % 60:02d}"


def extract_claims(entries: list[tuple[float, str]]) -> list[dict]:
    """Return one row per distinct (value, unit) with the first context it appears in."""
    rows = []
    seen = set()
    for seconds, text in entries:
        for match in CLAIM_RE.finditer(text):
            value, unit = match.group(1), match.group(2)
            value = re.sub(r"\s+", "", value)
            key = (value, unit)
            if key in seen:
                continue
            # Bare small counts (1个, 2种…) are structure, not claims.
            if unit in {"个", "种", "步", "层", "片", "次", "张", "台", "颗", "位", "条", "款", "家", "人", "月", "天"} \
                    and re.fullmatch(r"\d", value):
                continue
            seen.add(key)
            start = max(0, match.start() - 14)
            end = min(len(text), match.end() + 14)
            context = text[start:end].strip()
            rows.append({"claim": context, "value": f"{value}{unit}", "source_time": _mmss(seconds), "in_notes": ""})
    return rows


def format_tsv(rows: list[dict]) -> str:
    lines = [HEADER]
    for row in rows:
        lines.append("\t".join(row.get(k, "") for k in ("claim", "value", "source_time", "in_notes")))
    return "\n".join(lines) + "\n"


def parse_tsv(text: str) -> list[dict]:
    rows = []
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        parts += [""] * (4 - len(parts))
        rows.append(dict(zip(("claim", "value", "source_time", "in_notes"), parts[:4])))
    return rows


def flatten_tex(tex: str) -> str:
    """Strip LaTeX spacing, math delimiters, and unit macros so numbers compare as text."""
    body = tex.split(r"\begin{document}", 1)[1] if r"\begin{document}" in tex else tex
    body = re.sub(r"%[^\n]*", "", body)
    body = re.sub(r"\\(?:,|;|!|quad|qquad|thinspace)", "", body)
    body = re.sub(r"\\(?:mathrm|text|textbf|textit|emph|mathbf|si|SI|num)\{([^{}]*)\}", r"\1", body)
    body = re.sub(r"\\(?:degC|celsius)", "℃", body)
    body = re.sub(r"\\(?:um|micro)", "μm", body)
    body = re.sub(r"\\%", "%", body)
    body = re.sub(r"[\$\{\}\^_~\\]", "", body)
    body = body.translate(str.maketrans("０１２３４５６７８９．", "0123456789."))
    return re.sub(r"\s+", "", body)


def numbers_in(value: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)*", value)


def claim_in_notes(value: str, flat: str) -> bool:
    """Every number of the claim must appear in the flattened notes text."""
    nums = numbers_in(value)
    if not nums:
        return False
    for num in nums:
        plain = num.replace(",", "")
        if plain not in flat and num not in flat:
            return False
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_extract = sub.add_parser("extract")
    p_extract.add_argument("srt")
    p_extract.add_argument("--ocr", nargs="*", default=[], help="additional SRT tracks (hard-sub OCR, slide OCR)")
    p_extract.add_argument("--out", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("tsv")
    p_check.add_argument("tex")
    p_check.add_argument("--write", action="store_true", help="rewrite the TSV with in_notes filled")
    args = parser.parse_args(argv)

    if args.command == "extract":
        entries = parse_srt(Path(args.srt).read_text(encoding="utf-8"))
        for extra in args.ocr:
            entries += parse_srt(Path(extra).read_text(encoding="utf-8"))
        entries.sort(key=lambda e: e[0])
        rows = extract_claims(entries)
        Path(args.out).write_text(format_tsv(rows), encoding="utf-8")
        print(f"claims={len(rows)} out={args.out}")
        return 0

    rows = parse_tsv(Path(args.tsv).read_text(encoding="utf-8"))
    flat = flatten_tex(Path(args.tex).read_text(encoding="utf-8"))
    missing = []
    for row in rows:
        ok = claim_in_notes(row["value"], flat)
        row["in_notes"] = "yes" if ok else "no"
        if not ok:
            missing.append(row)
    if args.write:
        Path(args.tsv).write_text(format_tsv(rows), encoding="utf-8")
    print(f"claims={len(rows)} in_notes={len(rows) - len(missing)} missing={len(missing)}")
    for row in missing:
        print(f"  MISSING [{row['source_time']}] {row['value']}  ← {row['claim']}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
