#!/usr/bin/env python3
"""
clean_subs.py — Clean and deduplicate SRT subtitle files.

YouTube auto-generated subtitles often repeat each line 2-3 times
with slightly different timestamps. This script deduplicates them
and outputs a clean SRT file.

Usage:
  python clean_subs.py <input.srt> <output.srt>
  python clean_subs.py <input.srt>  # overwrite in place
"""

import argparse
import re
import sys


def parse_srt(text: str) -> list:
    """Parse SRT into list of (index, start, end, text) tuples."""
    blocks = re.split(r'\n\n+', text.strip())
    entries = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        # Find timestamp line
        ts_line = None
        text_lines = []
        for line in lines:
            if '-->' in line:
                ts_line = line.strip()
            elif ts_line is not None:
                text_lines.append(line.strip())
        if ts_line and text_lines:
            content = ' '.join(text_lines).strip()
            if content:
                match = re.match(
                    r'(\d[\d:,.]+)\s*-->\s*(\d[\d:,.]+)', ts_line)
                if match:
                    entries.append({
                        'start': match.group(1),
                        'end': match.group(2),
                        'text': content,
                    })
    return entries


def deduplicate(entries: list) -> list:
    """Remove duplicate/overlapping subtitle entries."""
    if not entries:
        return entries

    clean = []
    seen_texts = set()

    for entry in entries:
        text = entry['text'].strip()
        # Skip empty
        if not text:
            continue
        # Skip exact duplicates
        if text in seen_texts:
            continue
        # Skip if this text is a substring of the previous entry
        if clean and text in clean[-1]['text']:
            continue
        # Skip if previous text is a substring of this one
        # (keep the longer/later version)
        if clean and clean[-1]['text'] in text:
            clean[-1] = entry
            seen_texts.add(text)
            continue

        seen_texts.add(text)
        clean.append(entry)

    return clean


def to_srt(entries: list) -> str:
    """Convert entries back to SRT format."""
    lines = []
    for i, entry in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{entry['start']} --> {entry['end']}")
        lines.append(entry['text'])
        lines.append('')
    return '\n'.join(lines)


def to_plain_text(entries: list) -> str:
    """Convert entries to plain text (one line per entry)."""
    return '\n'.join(e['text'] for e in entries)


def main():
    parser = argparse.ArgumentParser(
        description="Clean and deduplicate SRT subtitle files")
    parser.add_argument("input", help="Input SRT file")
    parser.add_argument("output", nargs='?', help="Output file (default: overwrite input)")
    parser.add_argument("--format", choices=["srt", "txt"], default="srt",
                        help="Output format: srt (default) or txt (plain text)")
    parser.add_argument("--stats", action="store_true",
                        help="Print deduplication statistics")
    args = parser.parse_args()

    with open(args.input, 'r', encoding='utf-8') as f:
        text = f.read()

    entries = parse_srt(text)
    clean = deduplicate(entries)

    if args.stats:
        removed = len(entries) - len(clean)
        pct = (removed / len(entries) * 100) if entries else 0
        print(f"Original: {len(entries)} entries", file=sys.stderr)
        print(f"Cleaned:  {len(clean)} entries", file=sys.stderr)
        print(f"Removed:  {removed} duplicates ({pct:.0f}%)", file=sys.stderr)

    if args.format == "txt":
        output = to_plain_text(clean)
    else:
        output = to_srt(clean)

    out_path = args.output or args.input
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(output)

    if args.stats:
        print(f"Written to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
