#!/usr/bin/env python3
"""
Version and release-notes checks for tagged releases.

`VERSION` holds the repository version (MAJOR.MINOR.PATCH). Each tagged release has a
section in RELEASE_NOTES.md headed `## vMAJOR.MINOR.PATCH — YYYY-MM-DD — Title`; dated
headings without a version predate tagged releases and are ignored.

Subcommands:
    check [--tag vX.Y.Z]
        VERSION is MAJOR.MINOR.PATCH; the newest versioned section matches it; versioned
        sections are unique, dated, non-empty, and ordered newest first; the tag, when
        given, is `v` + VERSION. Prints one FAIL line per problem and exits 1 if any.
    notes vX.Y.Z [--out FILE]
        The body of that version's section, used as the GitHub Release notes.
    title vX.Y.Z
        `vX.Y.Z — Title`, used as the GitHub Release name.

`--root DIR` (before the subcommand) points at another checkout; tests use it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# The date field is captured loosely so a malformed date is reported, not silently skipped.
HEADING = re.compile(r"^## v(\S+) — ([^—\n]+?) — (.+)$", re.MULTILINE)


def sections(text: str) -> list[dict]:
    """Versioned sections in file order; a body runs to the next `## ` heading of any kind."""
    found = []
    for match in HEADING.finditer(text):
        end = text.find("\n## ", match.end())
        body = text[match.end(): end if end != -1 else len(text)].strip()
        found.append({"version": match.group(1), "date": match.group(2),
                      "title": match.group(3).strip(), "body": body})
    return found


def read_version(root: Path) -> str:
    path = root / "VERSION"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def read_sections(root: Path) -> list[dict]:
    path = root / "RELEASE_NOTES.md"
    return sections(path.read_text(encoding="utf-8")) if path.exists() else []


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def check(root: Path, tag: str | None = None) -> list[str]:
    version = read_version(root)
    if not SEMVER.match(version):
        return [f"VERSION must hold MAJOR.MINOR.PATCH, found {version!r}"]
    problems = []
    found = read_sections(root)
    if not found:
        problems.append(f"RELEASE_NOTES.md has no `## v{version} — YYYY-MM-DD — Title` section")
    elif found[0]["version"] != version:
        problems.append(f"newest RELEASE_NOTES.md section is v{found[0]['version']}, but VERSION is {version}")
    seen: set[str] = set()
    previous = None
    for section in found:
        label = f"v{section['version']}"
        if not SEMVER.match(section["version"]):
            problems.append(f"{label}: heading version is not MAJOR.MINOR.PATCH")
            continue
        if section["version"] in seen:
            problems.append(f"{label}: duplicate section")
        seen.add(section["version"])
        try:
            dt.date.fromisoformat(section["date"])
        except ValueError:
            problems.append(f"{label}: date {section['date']!r} is not YYYY-MM-DD")
        if not section["body"]:
            problems.append(f"{label}: section is empty")
        if previous is not None and version_key(section["version"]) >= version_key(previous):
            problems.append(f"{label}: sections must run newest first, but it follows v{previous}")
        previous = section["version"]
    if tag is not None and tag != f"v{version}":
        problems.append(f"tag {tag} does not match VERSION {version}; expected v{version}")
    return problems


def find_section(root: Path, tag: str) -> dict | None:
    return next((s for s in read_sections(root) if f"v{s['version']}" == tag), None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check")
    p_check.add_argument("--tag", default=None)
    p_notes = sub.add_parser("notes")
    p_notes.add_argument("tag")
    p_notes.add_argument("--out", default=None)
    p_title = sub.add_parser("title")
    p_title.add_argument("tag")
    args = parser.parse_args(argv)

    if args.command == "check":
        problems = check(args.root, args.tag)
        for problem in problems:
            print(f"FAIL {problem}")
        if not problems:
            print(f"PASS VERSION {read_version(args.root)} matches RELEASE_NOTES.md" + (f" and tag {args.tag}" if args.tag else ""))
        return 1 if problems else 0

    section = find_section(args.root, args.tag)
    if section is None:
        print(f"RELEASE_NOTES.md has no section for {args.tag}", file=sys.stderr)
        return 1
    if args.command == "title":
        print(f"v{section['version']} — {section['title']}")
        return 0
    text = section["body"] + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
