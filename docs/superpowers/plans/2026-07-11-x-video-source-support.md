# X/Twitter Video Source Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class X/Twitter lecture-video detection, metadata probing, subtitle-health validation, documentation, and regression coverage without changing the existing YouTube/Bilibili acquisition architecture.

**Architecture:** Keep `lecture-to-notes` instruction-driven. Add one offline/network source helper and one structural SRT validator, each backed by standard-library `unittest`; wire them into README and the skill instead of introducing a monolithic downloader.

**Tech Stack:** Python 3 standard library (`argparse`, `json`, `subprocess`, `urllib.parse`, `unittest`), `yt-dlp`, Markdown skill instructions.

---

## File map

- Create `scripts/video_source.py`: URL classification plus metadata-only `yt-dlp` probe.
- Create `scripts/check_srt_health.py`: structural subtitle parsing and health report.
- Create `tests/test_video_source.py`: offline URL and mocked probe tests.
- Create `tests/test_check_srt_health.py`: deterministic subtitle fixtures and CLI-independent checks.
- Create `tests/test_x_support_docs.py`: keeps README and skill source-support claims synchronized.
- Modify `README.md`: public feature, quick-start, workflow, and tool documentation.
- Modify `skills/lecture-to-notes/SKILL.md`: X acquisition, subtitle validation, and fallback contract.

### Task 1: Offline source detection

**Files:**
- Create: `scripts/video_source.py`
- Create: `tests/test_video_source.py`

- [ ] **Step 1: Write failing URL-classification tests**

Create `tests/test_video_source.py` with imports and a table-driven detector test:

```python
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import video_source


class DetectPlatformTests(unittest.TestCase):
    def test_supported_urls(self):
        cases = {
            "https://www.youtube.com/watch?v=abc": "youtube",
            "https://youtu.be/abc": "youtube",
            "https://www.bilibili.com/video/BV1xx411c7mD": "bilibili",
            "https://b23.tv/abcdef": "bilibili",
            "https://x.com/person/status/2075594420163092606": "x",
            "https://x.com/person/status/2075594420163092606/video/1": "x",
            "https://mobile.twitter.com/person/status/2075594420163092606?x=1#fragment": "x",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(video_source.detect_platform(url), expected)

    def test_unsupported_urls(self):
        for url in (
            "https://x.com/",
            "https://x.com/person",
            "https://t.co/abc",
            "not-a-url",
            "ftp://x.com/person/status/123",
        ):
            with self.subTest(url=url):
                with self.assertRaises(video_source.UnsupportedSourceError):
                    video_source.detect_platform(url)
```

- [ ] **Step 2: Run the test and verify the expected import failure**

Run:

```bash
python3 -m unittest tests.test_video_source.DetectPlatformTests -v
```

Expected: `ModuleNotFoundError: No module named 'video_source'`.

- [ ] **Step 3: Implement minimal URL detection**

Create `scripts/video_source.py` with this public detector:

```python
#!/usr/bin/env python3
"""Detect and metadata-probe lecture video sources."""

import argparse
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit


class UnsupportedSourceError(ValueError):
    """Raised when a URL is not a supported lecture-video source."""


def _normalized_host(host: str) -> str:
    host = host.lower().rstrip(".")
    for prefix in ("www.", "mobile.", "m."):
        if host.startswith(prefix):
            return host[len(prefix):]
    return host


def detect_platform(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsupportedSourceError(f"Unsupported video URL: {url}")

    host = _normalized_host(parsed.hostname)
    path = parsed.path.rstrip("/")
    if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        return "youtube"
    if host == "b23.tv":
        if path:
            return "bilibili"
    if host == "bilibili.com" or host.endswith(".bilibili.com"):
        if re.fullmatch(r"/video/BV[0-9A-Za-z]+", path, re.IGNORECASE):
            return "bilibili"
    if host in {"x.com", "twitter.com"}:
        if re.fullmatch(r"/[^/]+/status/\d+(?:/video/\d+)?", path):
            return "x"
    raise UnsupportedSourceError(f"Unsupported video URL: {url}")
```

- [ ] **Step 4: Run detector tests**

Run:

```bash
python3 -m unittest tests.test_video_source.DetectPlatformTests -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit detector and tests**

```bash
git add scripts/video_source.py tests/test_video_source.py
git commit -m "feat: detect X lecture video URLs"
```

### Task 2: Metadata-only source probe

**Files:**
- Modify: `scripts/video_source.py`
- Modify: `tests/test_video_source.py`

- [ ] **Step 1: Add failing probe tests**

Append tests that mock `subprocess.run` and verify the compact contract:

```python
class ProbeTests(unittest.TestCase):
    @mock.patch("video_source.subprocess.run")
    def test_probe_returns_compact_metadata(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=json.dumps({
                "id": "2075594420163092606",
                "title": "Lecture",
                "uploader": "Teacher",
                "duration": 120.5,
                "webpage_url": "https://x.com/person/status/2075594420163092606/video/1",
                "thumbnail": "https://example.test/thumb.jpg",
                "subtitles": {"en": [{}]},
                "automatic_captions": {"zh": [{}]},
            }),
            stderr="",
        )
        result = video_source.probe_source(
            "https://x.com/person/status/2075594420163092606/video/1")
        self.assertEqual(result["platform"], "x")
        self.assertEqual(result["id"], "2075594420163092606")
        self.assertEqual(result["subtitle_languages"], ["en", "zh"])
        self.assertTrue(result["has_thumbnail"])
        self.assertIn("--no-playlist", run.call_args.args[0])

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_extractor_failure(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="private post")
        with self.assertRaisesRegex(video_source.ProbeError, "private post"):
            video_source.probe_source("https://x.com/person/status/123")

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_missing_or_zero_duration(self, run):
        for payload in ({"duration": 1}, {"id": "123", "duration": 0}):
            run.return_value = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr="")
            with self.subTest(payload=payload):
                with self.assertRaises(video_source.ProbeError):
                    video_source.probe_source("https://x.com/person/status/123")

    @mock.patch("video_source.subprocess.run", side_effect=FileNotFoundError)
    def test_probe_reports_missing_ytdlp(self, run):
        with self.assertRaisesRegex(video_source.ProbeError, "yt-dlp"):
            video_source.probe_source("https://x.com/person/status/123")
```

- [ ] **Step 2: Run probe tests and verify missing symbols**

Run:

```bash
python3 -m unittest tests.test_video_source.ProbeTests -v
```

Expected: failures for missing `ProbeError` and `probe_source`.

- [ ] **Step 3: Implement the probe and CLI**

Append to `scripts/video_source.py`:

```python
class ProbeError(RuntimeError):
    """Raised when yt-dlp cannot validate a playable source."""


def _subtitle_languages(payload: dict) -> list[str]:
    languages = set((payload.get("subtitles") or {}).keys())
    languages.update((payload.get("automatic_captions") or {}).keys())
    return sorted(languages)


def _compact_metadata(platform: str, payload: dict) -> dict:
    source_id = str(payload.get("id") or "").strip()
    duration = payload.get("duration")
    if not source_id:
        raise ProbeError("yt-dlp metadata has no playable video ID")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise ProbeError("yt-dlp metadata has no positive video duration")
    return {
        "platform": platform,
        "id": source_id,
        "title": payload.get("title") or "",
        "uploader": payload.get("uploader") or "",
        "duration": float(duration),
        "webpage_url": payload.get("webpage_url") or "",
        "has_thumbnail": bool(payload.get("thumbnail")),
        "subtitle_languages": _subtitle_languages(payload),
    }


def probe_source(url: str) -> dict:
    platform = detect_platform(url)
    command = [
        "yt-dlp", "--dump-single-json", "--no-playlist",
        "--skip-download", url,
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise ProbeError("yt-dlp executable was not found") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown extractor failure"
        raise ProbeError(f"yt-dlp probe failed: {detail}")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("yt-dlp returned invalid JSON metadata") from exc
    return _compact_metadata(platform, payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("detect", "probe"):
        child = subparsers.add_parser(name)
        child.add_argument("url")
    args = parser.parse_args()
    try:
        if args.command == "detect":
            print(detect_platform(args.url))
        else:
            print(json.dumps(probe_source(args.url), ensure_ascii=False, indent=2))
    except UnsupportedSourceError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ProbeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run all source-helper tests**

Run:

```bash
python3 -m unittest tests.test_video_source -v
```

Expected: all detector and probe tests pass.

- [ ] **Step 5: Commit the probe**

```bash
git add scripts/video_source.py tests/test_video_source.py
git commit -m "feat: probe lecture video metadata"
```

### Task 3: Structural SRT health check

**Files:**
- Create: `scripts/check_srt_health.py`
- Create: `tests/test_check_srt_health.py`

- [ ] **Step 1: Write failing health-report tests**

Create fixtures in code so the suite does not depend on repository media:

```python
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_srt_health


def block(index, start, end, text):
    return f"{index}\n{start} --> {end}\n{text}\n"


class SrtHealthTests(unittest.TestCase):
    def test_healthy_track(self):
        text = "\n".join([
            block(1, "00:00:05,000", "00:00:12,000", "opening"),
            block(2, "00:00:47,000", "00:00:53,000", "middle"),
            block(3, "00:01:32,000", "00:01:38,000", "ending"),
        ])
        report = check_srt_health.assess_srt(text, duration=100)
        self.assertTrue(report["healthy"])
        self.assertEqual(report["entry_count"], 3)
        self.assertGreaterEqual(report["coverage"], 0.9)

    def test_rejects_truncated_track(self):
        text = block(1, "00:00:01,000", "00:00:10,000", "only opening")
        report = check_srt_health.assess_srt(text, duration=100)
        self.assertFalse(report["healthy"])
        self.assertIn("coverage_below_threshold", report["reasons"])

    def test_rejects_non_monotonic_track(self):
        text = "\n".join([
            block(1, "00:00:20,000", "00:00:25,000", "later"),
            block(2, "00:00:10,000", "00:00:15,000", "earlier"),
        ])
        with self.assertRaises(check_srt_health.SrtParseError):
            check_srt_health.assess_srt(text, duration=30)

    def test_rejects_repetition(self):
        text = "\n".join([
            block(1, "00:00:05,000", "00:00:10,000", "same"),
            block(2, "00:00:45,000", "00:00:55,000", "same"),
            block(3, "00:01:30,000", "00:01:40,000", "same"),
        ])
        report = check_srt_health.assess_srt(text, duration=100)
        self.assertFalse(report["healthy"])
        self.assertIn("repetition_above_threshold", report["reasons"])

    def test_rejects_empty_runtime_window(self):
        text = "\n".join([
            block(1, "00:00:05,000", "00:00:10,000", "opening"),
            block(2, "00:01:32,000", "00:01:38,000", "ending"),
        ])
        report = check_srt_health.assess_srt(text, duration=100)
        self.assertFalse(report["healthy"])
        self.assertIn("empty_runtime_window", report["reasons"])
```

- [ ] **Step 2: Run tests and verify the expected import failure**

Run:

```bash
python3 -m unittest tests.test_check_srt_health -v
```

Expected: `ModuleNotFoundError: No module named 'check_srt_health'`.

- [ ] **Step 3: Implement parser, report, and CLI**

Create `scripts/check_srt_health.py` with public `assess_srt` behavior:

```python
#!/usr/bin/env python3
"""Assess structural health of an SRT subtitle track."""

import argparse
import json
import re
import sys
from pathlib import Path


class SrtParseError(ValueError):
    """Raised when an SRT cannot be parsed safely."""


TIMESTAMP = re.compile(
    r"^(\d+):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d+):(\d{2}):(\d{2})[,.](\d{3})$")


def _seconds(parts) -> float:
    hours, minutes, seconds, millis = map(int, parts)
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_srt(text: str) -> list[dict]:
    entries = []
    for raw_block in re.split(r"\n\s*\n", text.strip()):
        lines = [line.rstrip() for line in raw_block.splitlines()]
        if len(lines) < 3:
            raise SrtParseError("subtitle block has fewer than three lines")
        match = TIMESTAMP.match(lines[1].strip())
        if not match:
            raise SrtParseError(f"invalid timestamp line: {lines[1]}")
        start = _seconds(match.groups()[:4])
        end = _seconds(match.groups()[4:])
        content = " ".join(line.strip() for line in lines[2:]).strip()
        if end < start:
            raise SrtParseError("subtitle end precedes start")
        if entries and start < entries[-1]["start"]:
            raise SrtParseError("subtitle timestamps are not monotonic")
        entries.append({"start": start, "end": end, "text": content})
    if not entries:
        raise SrtParseError("no subtitle entries found")
    return entries


def assess_srt(text: str, duration: float, min_coverage: float = 0.90,
               max_repetition: float = 0.50,
               window_ratio: float = 0.10) -> dict:
    if duration <= 0:
        raise SrtParseError("duration must be positive")
    entries = parse_srt(text)
    nonempty = [entry for entry in entries if entry["text"]]
    coverage = entries[-1]["end"] / duration
    unique = {entry["text"] for entry in nonempty}
    repetition = 1 - len(unique) / len(nonempty) if nonempty else 1.0
    window_status = {}
    for label, center in (("start", 0.10), ("middle", 0.50), ("end", 0.90)):
        radius = duration * window_ratio
        target = duration * center
        window_status[label] = any(
            entry["text"] and entry["start"] <= target + radius
            and entry["end"] >= target - radius for entry in entries)
    reasons = []
    if coverage < min_coverage:
        reasons.append("coverage_below_threshold")
    if repetition > max_repetition:
        reasons.append("repetition_above_threshold")
    if not all(window_status.values()):
        reasons.append("empty_runtime_window")
    return {
        "healthy": not reasons,
        "entry_count": len(entries),
        "first_timestamp": entries[0]["start"],
        "last_timestamp": entries[-1]["end"],
        "coverage": coverage,
        "repetition_ratio": repetition,
        "windows": window_status,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("srt", type=Path)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--min-coverage", type=float, default=0.90)
    parser.add_argument("--max-repetition", type=float, default=0.50)
    parser.add_argument("--window-ratio", type=float, default=0.10)
    args = parser.parse_args()
    try:
        report = assess_srt(
            args.srt.read_text(encoding="utf-8-sig"), args.duration,
            args.min_coverage, args.max_repetition, args.window_ratio)
    except (OSError, SrtParseError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run SRT tests**

Run:

```bash
python3 -m unittest tests.test_check_srt_health -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit the SRT helper**

```bash
git add scripts/check_srt_health.py tests/test_check_srt_health.py
git commit -m "feat: validate subtitle track health"
```

### Task 4: Skill and README integration

**Files:**
- Create: `tests/test_x_support_docs.py`
- Modify: `README.md`
- Modify: `skills/lecture-to-notes/SKILL.md`

- [ ] **Step 1: Add a failing documentation contract test**

Create `tests/test_x_support_docs.py`:

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class XSupportDocumentationTests(unittest.TestCase):
    def test_readme_and_skill_document_x_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills/lecture-to-notes/SKILL.md").read_text(
            encoding="utf-8")
        for text in (readme, skill):
            self.assertIn("X/Twitter", text)
            self.assertIn("scripts/video_source.py", text)
            self.assertIn("scripts/check_srt_health.py", text)
            self.assertIn("x.com/", text)
        self.assertIn("/video/<n>", skill)
        self.assertIn("90%", skill)
        self.assertIn("Whisper", skill)
```

- [ ] **Step 2: Run the contract test and verify failure**

Run:

```bash
python3 -m unittest tests.test_x_support_docs -v
```

Expected: FAIL because README and skill do not yet claim X/Twitter support.

- [ ] **Step 3: Update README**

Make these concrete changes:

```markdown
- Change the opening description to “YouTube / Bilibili / X(Twitter)”.
- Change “多平台支持” to list all three platforms.
- Add `video_source.py` and `check_srt_health.py` to the repository tree and tool table.
- Add quick-start examples:
  `python3 scripts/video_source.py detect "<URL>"`
  `python3 scripts/video_source.py probe "<URL>"`
- State that X subtitles must pass structural health and 10/50/90-percent semantic samples.
- Add X/Twitter to the workflow and supported-use-case list.
- Add an “X/Twitter 支持” row to the comparison table.
```

- [ ] **Step 4: Update the skill acquisition contract**

Apply these exact behavioral changes to `skills/lecture-to-notes/SKILL.md`:

```markdown
- Frontmatter and opening goal list YouTube, Bilibili, and X/Twitter.
- Platform table adds:
  `x.com/<user>/status/<id>[/video/<n>]`,
  `twitter.com/<user>/status/<id>[/video/<n>]` → X/Twitter.
- Phase 1 begins with:
  `python3 scripts/video_source.py probe "<URL>" > metadata.json`
- X subtitle commands include `--no-playlist` and both manual/automatic tracks.
- Downloaded X SRT runs through:
  `python3 scripts/check_srt_health.py subs.srt --duration <seconds>`.
- A failed health check falls back to X audio → Whisper → existing correction passes.
- The skill requires audio/visual samples at 10%, 50%, and 90% before accepting X captions.
- External official captions require identity proof, constant-offset alignment, three-point validation, and provenance disclosure.
- All X metadata, thumbnail, audio, and video commands retain `/video/<n>` and use `--no-playlist`.
```

- [ ] **Step 5: Run documentation and full offline tests**

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all tests pass without network access.

- [ ] **Step 6: Commit docs and contract test**

```bash
git add README.md skills/lecture-to-notes/SKILL.md tests/test_x_support_docs.py
git commit -m "docs: add X lecture acquisition workflow"
```

### Task 5: Live smoke probe and final verification

**Files:**
- Modify only if verification exposes a defect: files introduced in Tasks 1-4.

- [ ] **Step 1: Run syntax and unit verification**

```bash
python3 -m py_compile scripts/video_source.py scripts/check_srt_health.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
git diff --check HEAD~3..HEAD
```

Expected: compilation succeeds, all tests pass, and diff check prints nothing.

- [ ] **Step 2: Run supported-source CLI checks**

```bash
python3 scripts/video_source.py detect \
  "https://x.com/vicky_grok/status/2075594420163092606/video/1"
python3 scripts/video_source.py detect \
  "https://www.youtube.com/watch?v=lVynu4bo1rY"
```

Expected output: `x`, then `youtube`.

- [ ] **Step 3: Run the live metadata-only X smoke probe**

```bash
python3 scripts/video_source.py probe \
  "https://x.com/vicky_grok/status/2075594420163092606/video/1"
```

Expected: exit 0 and JSON with `"platform": "x"`, a non-empty `id`, and positive
`duration`; no media file is created.

- [ ] **Step 4: Validate against the completed lecture subtitle**

```bash
python3 scripts/check_srt_health.py \
  /Users/shaoyiyang/Code/auto_study/stanford_llm_architecture_from_scratch/audio_corrected.srt \
  --duration 5342.848
```

Expected: JSON with `"healthy": true`, coverage at least 0.90, and all three
runtime windows set to `true`.

- [ ] **Step 5: Inspect scope and preserve user artifacts**

```bash
git status --short
git log --oneline -5
```

Expected: the pre-existing untracked `docs/diagrams/`,
`docs/pdfs/cpp_low_latency_p1_timur_cppnow.pdf`, and `work/` remain untracked;
feature commits contain only planned files.

- [ ] **Step 6: Update the code knowledge graph**

Run an incremental `codebase-memory-mcp index_repository` for
`/Users/shaoyiyang/Code/lecture-to-notes`, then use `search_graph` to confirm the
two new scripts and test modules are discoverable.
