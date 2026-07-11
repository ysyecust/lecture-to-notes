#!/usr/bin/env python3
"""Assess structural health of an SRT subtitle track."""

import argparse
import json
import math
import re
import sys
from pathlib import Path


class SrtParseError(ValueError):
    """Raised when an SRT track cannot be parsed safely."""


INDEX = re.compile(r"^[0-9]+$")
TIMESTAMP = re.compile(
    r"^([0-9]+):([0-9]{2}):([0-9]{2})[,.]([0-9]{3})\s*-->\s*"
    r"([0-9]+):([0-9]{2}):([0-9]{2})[,.]([0-9]{3})$"
)


def _seconds(parts) -> float:
    try:
        hours, minutes, seconds, milliseconds = (int(part) for part in parts)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SrtParseError("invalid numeric timestamp component") from exc

    if not 0 <= minutes <= 59 or not 0 <= seconds <= 59:
        raise SrtParseError("timestamp minutes and seconds must be between 0 and 59")
    try:
        total_seconds = (
            hours * 3600
            + minutes * 60
            + seconds
            + milliseconds / 1000
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise SrtParseError("timestamp cannot be represented as seconds") from exc
    if not math.isfinite(total_seconds):
        raise SrtParseError("timestamp seconds must be finite")
    return total_seconds


def _is_finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def parse_srt(text: str) -> list[dict]:
    """Parse SRT entries and reject structurally unsafe timelines."""
    stripped = text.removeprefix("\ufeff").strip()
    if not stripped:
        raise SrtParseError("SRT contains no entries")

    entries = []
    previous_start = None
    for raw_block in re.split(r"\r?\n\s*\r?\n", stripped):
        lines = raw_block.strip().splitlines()
        if len(lines) < 3:
            raise SrtParseError("SRT entry must contain at least three lines")
        if INDEX.fullmatch(lines[0].strip()) is None:
            raise SrtParseError("SRT entry index must be an ASCII decimal number")

        match = TIMESTAMP.fullmatch(lines[1].strip())
        if match is None:
            raise SrtParseError(f"invalid timestamp: {lines[1]}")

        for line_index in range(2, len(lines) - 1):
            if INDEX.fullmatch(lines[line_index].strip()) and TIMESTAMP.fullmatch(
                lines[line_index + 1].strip()
            ):
                raise SrtParseError("SRT entries must be separated by a blank line")

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
    if not _is_finite_number(duration) or duration <= 0:
        raise SrtParseError("duration must be positive")
    if not _is_finite_number(min_coverage) or not 0 <= min_coverage <= 1:
        raise SrtParseError("min_coverage must be between 0 and 1")
    if not _is_finite_number(max_repetition) or not 0 <= max_repetition <= 1:
        raise SrtParseError("max_repetition must be between 0 and 1")
    if not _is_finite_number(window_ratio) or not 0 < window_ratio <= 0.20:
        raise SrtParseError("window_ratio must be greater than 0 and at most 0.20")

    entries = parse_srt(text)
    nonempty = [
        (entry_index, entry)
        for entry_index, entry in enumerate(entries)
        if entry["text"].strip()
    ]
    # Permit small subtitle/container rounding disagreements: at least one second,
    # or 0.1% of the media duration for long recordings.
    overrun_tolerance = max(1.0, duration * 0.001)
    timeline_out_of_bounds = any(
        entry["end"] > duration + overrun_tolerance for entry in entries
    )
    coverage = min(entries[-1]["end"] / duration, 1.0)
    repetition_ratio = (
        1 - len({entry["text"] for _, entry in nonempty}) / len(nonempty)
        if nonempty
        else 1.0
    )

    half_width = duration * window_ratio
    windows = {}
    window_candidates = {}
    for name, center_ratio in (("start", 0.10), ("middle", 0.50), ("end", 0.90)):
        center = duration * center_ratio
        lower = center - half_width
        upper = center + half_width
        candidates = [
            entry_index
            for entry_index, entry in nonempty
            if entry["end"] >= lower and entry["start"] <= upper
        ]
        window_candidates[name] = candidates
        windows[name] = bool(candidates)

    distinct_runtime_evidence = any(
        len({start_index, middle_index, end_index}) == 3
        for start_index in window_candidates["start"]
        for middle_index in window_candidates["middle"]
        for end_index in window_candidates["end"]
    )

    reasons = []
    if coverage < min_coverage:
        reasons.append("coverage_below_threshold")
    if repetition_ratio > max_repetition:
        reasons.append("repetition_above_threshold")
    if not all(windows.values()):
        reasons.append("empty_runtime_window")
    if timeline_out_of_bounds:
        reasons.append("timestamp_exceeds_duration")
    if not distinct_runtime_evidence:
        reasons.append("insufficient_distinct_runtime_evidence")

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
    except (OSError, UnicodeError, SrtParseError) as exc:
        print(exc, file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
