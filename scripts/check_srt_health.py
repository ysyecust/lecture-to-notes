#!/usr/bin/env python3
"""Assess structural health of an SRT subtitle track."""

import argparse
import json
import re
import sys
from pathlib import Path


class SrtParseError(ValueError):
    """Raised when an SRT track cannot be parsed safely."""


TIMESTAMP = re.compile(
    r"^(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d+):(\d{2}):(\d{2})[,.](\d{3})$"
)


def _seconds(parts) -> float:
    hours, minutes, seconds, milliseconds = parts
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(milliseconds) / 1000
    )


def parse_srt(text: str) -> list[dict]:
    """Parse SRT entries and reject structurally unsafe timelines."""
    stripped = text.strip()
    if not stripped:
        raise SrtParseError("SRT contains no entries")

    entries = []
    previous_start = None
    for raw_block in re.split(r"\r?\n\s*\r?\n", stripped):
        lines = raw_block.strip().splitlines()
        if len(lines) < 3:
            raise SrtParseError("SRT entry must contain at least three lines")

        match = TIMESTAMP.fullmatch(lines[1].strip())
        if match is None:
            raise SrtParseError(f"invalid timestamp: {lines[1]}")

        groups = match.groups()
        start = _seconds(groups[:4])
        end = _seconds(groups[4:])
        if end < start:
            raise SrtParseError("SRT entry ends before it starts")
        if previous_start is not None and start < previous_start:
            raise SrtParseError("SRT entry starts are not monotonic")

        entries.append(
            {
                "start": start,
                "end": end,
                "text": "\n".join(lines[2:]).strip(),
            }
        )
        previous_start = start

    if not entries:
        raise SrtParseError("SRT contains no entries")
    return entries


def assess_srt(
    text,
    duration,
    min_coverage=0.90,
    max_repetition=0.50,
    window_ratio=0.10,
):
    """Assess an SRT track against coverage, repetition, and runtime windows."""
    if duration <= 0:
        raise SrtParseError("duration must be positive")

    entries = parse_srt(text)
    nonempty = [entry for entry in entries if entry["text"].strip()]
    coverage = entries[-1]["end"] / duration
    repetition_ratio = (
        1 - len({entry["text"] for entry in nonempty}) / len(nonempty)
        if nonempty
        else 1.0
    )

    half_width = duration * window_ratio
    windows = {}
    for name, center_ratio in (("start", 0.10), ("middle", 0.50), ("end", 0.90)):
        center = duration * center_ratio
        lower = center - half_width
        upper = center + half_width
        windows[name] = any(
            entry["end"] >= lower and entry["start"] <= upper
            for entry in nonempty
        )

    reasons = []
    if coverage < min_coverage:
        reasons.append("coverage_below_threshold")
    if repetition_ratio > max_repetition:
        reasons.append("repetition_above_threshold")
    if not all(windows.values()):
        reasons.append("empty_runtime_window")

    return {
        "healthy": not reasons,
        "entry_count": len(entries),
        "first_timestamp": entries[0]["start"],
        "last_timestamp": entries[-1]["end"],
        "coverage": coverage,
        "repetition_ratio": repetition_ratio,
        "windows": windows,
        "reasons": reasons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("srt", type=Path)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--min-coverage", type=float, default=0.90)
    parser.add_argument("--max-repetition", type=float, default=0.50)
    parser.add_argument("--window-ratio", type=float, default=0.10)
    args = parser.parse_args()

    try:
        text = args.srt.read_text(encoding="utf-8-sig")
        result = assess_srt(
            text,
            duration=args.duration,
            min_coverage=args.min_coverage,
            max_repetition=args.max_repetition,
            window_ratio=args.window_ratio,
        )
    except (OSError, SrtParseError) as exc:
        print(exc, file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
