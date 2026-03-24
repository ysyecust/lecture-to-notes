#!/usr/bin/env python3
"""
verify_figures.py — Cross-reference figure timestamps with subtitle content.

Given a list of figure timestamps and an SRT file, outputs the subtitle text
around each timestamp to help verify figure-text alignment.

Usage:
  python verify_figures.py <srt_file> <timestamp1> [<timestamp2> ...]
  python verify_figures.py audio.srt 04:45 07:00 14:00 24:30

  # With frame filenames (extracts timestamp from chapter offset + frame number)
  python verify_figures.py audio.srt --frames frames/ch1_020.png frames/ch2_050.png \
    --chapters "0:00:00,0:18:23,0:38:10,0:58:30"
"""

import argparse
import re
import sys


def parse_srt(filepath: str) -> list:
    """Parse SRT file into list of (start_sec, end_sec, text) tuples."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    blocks = re.split(r'\n\n+', text.strip())
    entries = []
    for block in blocks:
        m = re.match(
            r'\d+\n(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)',
            block
        )
        if m:
            start = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            end = int(m.group(5)) * 3600 + int(m.group(6)) * 60 + int(m.group(7))
            lines = block.strip().split('\n')
            txt = ' '.join(lines[2:]).strip() if len(lines) > 2 else ''
            if txt:
                entries.append((start, end, txt))
    return entries


def ts_to_sec(ts: str) -> int:
    """Convert MM:SS or HH:MM:SS to seconds."""
    parts = ts.split(':')
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    else:
        raise ValueError(f"Invalid timestamp: {ts}")


def sec_to_ts(sec: int) -> str:
    """Convert seconds to MM:SS format."""
    return f"{sec // 60}:{sec % 60:02d}"


def frame_to_timestamp(frame_path: str, chapter_starts: list) -> int:
    """
    Convert frame filename to absolute timestamp.
    e.g., ch2_050.png with chapters [0, 1103, 2290, 3510]
    → chapter 2 starts at 1103s, frame 50 → 1103 + (50-1)*15 = 1838s
    """
    m = re.search(r'ch(\d+)_(\d+)', frame_path)
    if not m:
        return 0
    ch = int(m.group(1))
    frame_num = int(m.group(2))
    if ch <= len(chapter_starts):
        return chapter_starts[ch - 1] + (frame_num - 1) * 15
    return 0


def find_context(entries: list, target_sec: int, window: int = 20) -> list:
    """Find subtitle entries within 'window' seconds of target."""
    results = []
    for start, end, text in entries:
        if abs(start - target_sec) <= window:
            results.append((start, text))
    results.sort(key=lambda x: abs(x[0] - target_sec))
    return results[:5]


def main():
    parser = argparse.ArgumentParser(
        description="Cross-reference figure timestamps with subtitle content")
    parser.add_argument("srt", help="SRT subtitle file")
    parser.add_argument("timestamps", nargs='*',
                        help="Timestamps to check (MM:SS or HH:MM:SS)")
    parser.add_argument("--frames", nargs='*',
                        help="Frame filenames (ch1_020.png format)")
    parser.add_argument("--chapters", type=str,
                        help="Comma-separated chapter start times (H:MM:SS,...)")
    parser.add_argument("--window", type=int, default=20,
                        help="Search window in seconds (default: 20)")
    args = parser.parse_args()

    entries = parse_srt(args.srt)
    if not entries:
        print("Error: no subtitle entries found in SRT file", file=sys.stderr)
        sys.exit(1)

    targets = []

    # From explicit timestamps
    for ts in (args.timestamps or []):
        targets.append((ts, ts_to_sec(ts)))

    # From frame filenames
    if args.frames:
        chapter_starts = []
        if args.chapters:
            chapter_starts = [ts_to_sec(t) for t in args.chapters.split(',')]
        for frame in args.frames:
            sec = frame_to_timestamp(frame, chapter_starts)
            targets.append((frame, sec))

    if not targets:
        print("No timestamps or frames specified. Use positional args or --frames.")
        sys.exit(1)

    for label, target in targets:
        context = find_context(entries, target, args.window)
        print(f"=== {label} @ {sec_to_ts(target)} ({target}s) ===")
        if context:
            for t, text in context:
                marker = ">>>" if abs(t - target) < 5 else "   "
                print(f"  {marker} [{sec_to_ts(t)}] {text}")
        else:
            print("  (no subtitle found within window)")
        print()


if __name__ == "__main__":
    main()
