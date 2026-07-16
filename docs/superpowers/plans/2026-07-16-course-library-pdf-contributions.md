# Course Library and PDF Contributions Implementation Plan

> **Execution note:** Run this plan inline, task by task, unless the user explicitly authorizes delegated agents. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the existing library plus Stanford CS336 Spring 2026 in a course-first website, and let external contributors add safe PDFs through reviewed GitHub pull requests that are parsed and deployed automatically after merge.

**Architecture:** Keep code and every source PDF in this repository. Trusted Python modules inspect PDFs, build a generated catalog, and assemble `_site/`; static browser modules render the course library, reader, and contribution guide from that catalog. Fork PRs run a read-only validator from the base branch inside a restricted Docker container, while only trusted `main` builds receive Pages deployment permissions.

**Tech Stack:** Python 3.14 standard library, Poppler, qpdf, ImageMagick, Docker, semantic HTML/CSS/ES modules, Playwright 1.61.1, GitHub Actions, GitHub Pages

---

## File map

**Trusted content and build units**

- `content/courses/<course-id>/course.json`: curated course and lecture overrides.
- `content/courses/<course-id>/*.pdf`: curated PDF sources.
- `content/inbox/*.pdf`: contribution-only source lane.
- `content/papers.json`: existing paper-card metadata.
- `scripts/pdf_inspector.py`: PDF integrity, active-content, title, page, ID, and thumbnail logic.
- `scripts/site_catalog.py`: compose deterministic courses/items/papers catalog.
- `scripts/build_site.py`: copy the static shell, map PDFs, create thumbnails, and write `_site/data/catalog.json`.
- `scripts/build_site_container.sh`: reproduce the pinned, read-only build environment locally and in CI.
- `scripts/validate_contribution.py`: compare base/submission trees, enforce the PR allowlist and limits, and emit a report.
- `scripts/migrate_legacy_site.mjs`: one-time deterministic migration from the existing `DATA` array.
- `ci/pdf-sandbox.Dockerfile`: isolated Poppler/qpdf/ImageMagick runtime for validation and trusted site builds.

**Browser units**

- `docs/index.html`: semantic course-library shell.
- `docs/reader.html`: semantic PDF-reader shell.
- `docs/contribute.html`: GitHub PR contribution instructions.
- `docs/assets/styles.css`: Technical Study Desk tokens and responsive layout.
- `docs/assets/catalog.js`: catalog loading, lookup, search, and URL helpers.
- `docs/assets/components.js`: DOM-only course/item rendering; no `innerHTML` for catalog text.
- `docs/assets/home.js`: homepage search and hash routing.
- `docs/assets/reader.js`: item lookup, course navigation, and PDF fallback actions.

**Verification and automation**

- `tests/pdf_factory.py`: deterministic valid and active-content PDF fixtures.
- `tests/test_pdf_inspector.py`: parser and active-content unit tests.
- `tests/test_site_catalog.py`: catalog determinism and schema tests.
- `tests/test_build_site.py`: complete build and legacy URL tests.
- `tests/test_validate_contribution.py`: path, size, rights, and report tests.
- `tests/test_site_contract.py`: HTML/CSP/XSS-safe rendering contract tests.
- `package.json`, `package-lock.json`, `playwright.config.mjs`, `e2e/site.spec.mjs`: browser smoke and screenshot checks.
- `.github/workflows/contribution-check.yml`: unprivileged fork-PR validation.
- `.github/workflows/pages.yml`: trusted build and Pages deploy.

### Task 1: Define deterministic title and ID rules

**Files:**
- Create: `scripts/pdf_inspector.py`
- Create: `tests/__init__.py`
- Create: `tests/test_pdf_inspector.py`

- [ ] **Step 1: Write failing pure-function tests**

Create an empty `tests/__init__.py` so file-targeted `unittest` commands resolve the repository's tests package, then create `tests/test_pdf_inspector.py` with the initial tests:

```python
import tempfile
import unittest
from pathlib import Path

from scripts.pdf_inspector import TextLine, choose_title, stable_item_id


class TitleSelectionTests(unittest.TestCase):
    def test_prefers_meaningful_metadata_title(self):
        lines = [TextLine("First Page Heading", 48.0, 72.0, 36.0)]
        result = choose_title("Stanford CS336 Lecture 1", lines, "lecture01.pdf", 792.0)
        self.assertEqual("Stanford CS336 Lecture 1", result.title)
        self.assertEqual("metadata", result.source)

    def test_rejects_generic_metadata_and_scores_top_large_text(self):
        lines = [
            TextLine("1", 760.0, 770.0, 9.0),
            TextLine("Overview & Tokenization", 64.0, 92.0, 28.0),
            TextLine("Stanford CS336", 110.0, 125.0, 15.0),
        ]
        result = choose_title("Microsoft Word", lines, "notes.pdf", 792.0)
        self.assertEqual("Overview & Tokenization", result.title)
        self.assertEqual("first_page", result.source)

    def test_falls_back_to_clean_filename(self):
        result = choose_title("", [], "my_course-notes_zh.pdf", 792.0)
        self.assertEqual("My Course Notes Zh", result.title)
        self.assertEqual("filename", result.source)

    def test_stable_id_includes_course_slug_and_digest(self):
        self.assertEqual(
            "stanford-cs336-2026-overview-tokenization-a1b2c3d4",
            stable_item_id(
                "stanford-cs336-2026", "Overview & Tokenization", "a1b2c3d4ff"
            ),
        )
```

- [ ] **Step 2: Run the test and verify import failure**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_pdf_inspector.py -v
```

Expected: fail because `scripts.pdf_inspector` does not exist.

- [ ] **Step 3: Implement the pure title and ID module**

Create `scripts/pdf_inspector.py` with:

```python
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


GENERIC_TITLES = {
    "", "untitled", "document", "microsoft word", "powerpoint presentation"
}


class PdfInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TextLine:
    text: str
    y_min: float
    y_max: float
    height: float


@dataclass(frozen=True)
class TitleChoice:
    title: str
    source: str
    confidence: float


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def slugify(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return slug[:64] or "pdf"


def filename_title(path: str | Path) -> str:
    words = re.sub(r"[_-]+", " ", Path(path).stem)
    return clean_text(words).title()


def choose_title(
    metadata_title: str,
    lines: list[TextLine],
    filename: str | Path,
    page_height: float,
) -> TitleChoice:
    metadata = clean_text(metadata_title)
    if metadata.lower() not in GENERIC_TITLES and 4 <= len(metadata) <= 180:
        return TitleChoice(metadata, "metadata", 1.0)
    candidates = [
        line for line in lines
        if line.y_min <= page_height * 0.55
        and 4 <= len(clean_text(line.text)) <= 180
        and not clean_text(line.text).isdigit()
    ]
    if candidates:
        best = max(
            candidates,
            key=lambda line: (line.height * 5.0) - (line.y_min / max(page_height, 1.0)),
        )
        return TitleChoice(clean_text(best.text), "first_page", 0.8)
    return TitleChoice(filename_title(filename), "filename", 0.5)


def stable_item_id(course_id: str, title: str, digest: str) -> str:
    return f"{slugify(course_id)}-{slugify(title)}-{digest[:8].lower()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
```

- [ ] **Step 4: Run the tests and commit**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_pdf_inspector.py -v
git add scripts/pdf_inspector.py tests/__init__.py tests/test_pdf_inspector.py
git commit -m "feat: define deterministic PDF titles"
```

Expected: four tests pass and one focused commit is created.

### Task 2: Inspect real PDFs and reject active content

**Files:**
- Create: `tests/pdf_factory.py`
- Modify: `scripts/pdf_inspector.py`
- Modify: `tests/test_pdf_inspector.py`

- [ ] **Step 1: Add a deterministic PDF fixture factory**

Create `tests/pdf_factory.py` with a `write_pdf` function that writes a valid one-page PDF with Helvetica text, optional `/Title`, and an optional `/OpenAction`. Build the xref offsets from encoded object lengths so tests do not depend on a PDF-writing package:

```python
from pathlib import Path


def write_pdf(path: Path, title: str = "", heading: str = "Course Heading", active=False):
    escaped = heading.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 28 Tf 72 700 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R" + (b" /OpenAction 7 0 R" if active else b"") + b" >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        (f"<< /Title ({title}) >>".encode("latin-1") if title else b"<< >>"),
    ]
    if active:
        objects.append(b"<< /S /JavaScript /JS (app.alert('x')) >>")
    data = bytearray(b"%PDF-1.7\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode())
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R /Info 6 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(data)
```

- [ ] **Step 2: Add failing integration and active-content tests**

Append tests that create temporary PDFs and assert:

```python
from tests.pdf_factory import write_pdf
from scripts.pdf_inspector import inspect_pdf


class PdfInspectionIntegrationTests(unittest.TestCase):
    def test_extracts_metadata_pages_heading_and_thumbnail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "lecture.pdf"
            write_pdf(pdf, title="CS336 Tokenization", heading="Ignored Heading")
            result = inspect_pdf(pdf, root / "thumbs")
            self.assertEqual(1, result.pages)
            self.assertEqual("CS336 Tokenization", result.title)
            self.assertEqual("metadata", result.title_source)
            self.assertTrue(result.thumbnail.is_file())
            self.assertEqual(64, len(result.sha256))

    def test_rejects_open_action_and_javascript(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf = root / "active.pdf"
            write_pdf(pdf, active=True)
            with self.assertRaisesRegex(PdfInspectionError, "active PDF content"):
                inspect_pdf(pdf, root / "thumbs")
```

- [ ] **Step 3: Implement tool execution, bbox parsing, qdf scan, and thumbnailing**

Extend `scripts/pdf_inspector.py` with:

```python
import json
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ACTIVE_MARKER = re.compile(
    rb"/(?:JavaScript|JS|Launch|EmbeddedFiles|OpenAction|AA|RichMedia)\b"
)


@dataclass(frozen=True)
class PdfInspection:
    path: Path
    title: str
    title_source: str
    pages: int
    sha256: str
    thumbnail: Path


def run_checked(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, check=True, capture_output=True, timeout=timeout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        raise PdfInspectionError(f"PDF tool failed: {args[0]}") from error


def parse_pdfinfo(output: str) -> dict[str, str]:
    result = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


def parse_bbox(xml_bytes: bytes) -> tuple[list[TextLine], float]:
    root = ET.fromstring(xml_bytes)
    page = next(element for element in root.iter() if element.tag.endswith("page"))
    page_height = float(page.attrib.get("height", "792"))
    lines = []
    for line in (element for element in root.iter() if element.tag.endswith("line")):
        words = [element for element in line if element.tag.endswith("word")]
        text = clean_text(" ".join(element.text or "" for element in words))
        if text:
            y_min = min(float(element.attrib.get("yMin", "0")) for element in words)
            y_max = max(float(element.attrib.get("yMax", str(y_min))) for element in words)
            lines.append(TextLine(text, y_min, y_max, max(y_max - y_min, 1.0)))
    return lines, page_height


def reject_active_content(path: Path) -> None:
    with tempfile.TemporaryDirectory() as directory:
        qdf = Path(directory) / "expanded.pdf"
        run_checked(["qpdf", "--qdf", "--object-streams=disable", str(path), str(qdf)])
        data = qdf.read_bytes()
        found = sorted({match.group().decode("ascii") for match in ACTIVE_MARKER.finditer(data)})
        if found:
            raise PdfInspectionError("active PDF content: " + ", ".join(found))


def inspect_pdf(path: Path, thumbnail_dir: Path) -> PdfInspection:
    with path.open("rb") as stream:
        signature = stream.read(5)
    if path.stat().st_size < 8 or signature != b"%PDF-":
        raise PdfInspectionError("invalid PDF signature")
    run_checked(["qpdf", "--check", str(path)])
    reject_active_content(path)
    info = parse_pdfinfo(run_checked(["pdfinfo", str(path)]).stdout.decode("utf-8", "replace"))
    lines, page_height = parse_bbox(
        run_checked(["pdftotext", "-f", "1", "-l", "1", "-bbox-layout", str(path), "-"]).stdout
    )
    choice = choose_title(info.get("Title", ""), lines, path.name, page_height)
    pages = int(info["Pages"])
    digest = sha256_file(path)
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    prefix = thumbnail_dir / digest[:16]
    run_checked(["pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-scale-to", "960", "-png", str(path), str(prefix)])
    png = prefix.with_suffix(".png")
    webp = prefix.with_suffix(".webp")
    run_checked(["magick", str(png), "-strip", "-quality", "82", str(webp)])
    png.unlink()
    return PdfInspection(path, choice.title, choice.source, pages, digest, webp)
```

- [ ] **Step 4: Run the focused and full test suites, then commit**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_pdf_inspector.py -v
python3 -m unittest discover -s tests -v
git add scripts/pdf_inspector.py tests/pdf_factory.py tests/test_pdf_inspector.py
git commit -m "feat: inspect and sanitize PDF contributions"
```

Decorate this integration class with `@unittest.skipUnless(all(shutil.which(tool) for tool in ("qpdf", "pdfinfo", "pdftotext", "pdftoppm", "magick")), "PDF toolchain required")`. Expected locally: pure tests pass and integration tests skip if qpdf is unavailable. Task 4 runs the integration in the pinned container.

### Task 3: Enforce contribution-only tree changes

**Files:**
- Create: `scripts/validate_contribution.py`
- Create: `tests/test_validate_contribution.py`

- [ ] **Step 1: Write failing policy tests**

Create tests that build `base/` and `submission/` trees and call `validate_delta`:

```python
import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_contribution import ContributionError, validate_delta
from tests.pdf_factory import write_pdf


RIGHTS_BODY = "- [x] I have the right to share these PDFs for educational use."


class ContributionPolicyTests(unittest.TestCase):
    def roots(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        base = root / "base"
        submission = root / "submission"
        base.mkdir()
        submission.mkdir()
        return temporary, base, submission

    def test_accepts_pdf_only_addition_with_rights(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        inbox = submission / "content/inbox"
        inbox.mkdir(parents=True)
        write_pdf(inbox / "lecture.pdf")
        result = validate_delta(base, submission, RIGHTS_BODY)
        self.assertEqual(["content/inbox/lecture.pdf"], result.added_pdfs)

    def test_rejects_code_change_beside_pdf(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        (base / "scripts").mkdir()
        (submission / "scripts").mkdir()
        (base / "scripts/app.py").write_text("safe")
        (submission / "scripts/app.py").write_text("changed")
        inbox = submission / "content/inbox"
        inbox.mkdir(parents=True)
        write_pdf(inbox / "lecture.pdf")
        with self.assertRaisesRegex(ContributionError, "only add PDFs"):
            validate_delta(base, submission, RIGHTS_BODY)

    def test_rejects_missing_rights_checkbox(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        inbox = submission / "content/inbox"
        inbox.mkdir(parents=True)
        write_pdf(inbox / "lecture.pdf")
        with self.assertRaisesRegex(ContributionError, "rights declaration"):
            validate_delta(base, submission, "")
```

- [ ] **Step 2: Implement tree comparison and limits**

Create `scripts/validate_contribution.py` with:

```python
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.pdf_inspector import inspect_pdf, sha256_file, stable_item_id


MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 10
RIGHTS_MARKER = "- [x] I have the right to share these PDFs for educational use."


class ContributionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Delta:
    added_pdfs: list[str]


def tree_map(root: Path) -> dict[str, str]:
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            relative = path.relative_to(root).as_posix()
            result[relative] = sha256_file(path)
    return result


def validate_delta(base: Path, submission: Path, body: str) -> Delta:
    if RIGHTS_MARKER not in body:
        raise ContributionError("rights declaration must be checked")
    before, after = tree_map(base), tree_map(submission)
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    added = sorted(path for path in changed if path not in before)
    allowed = [
        path for path in added
        if Path(path).parent.as_posix() == "content/inbox"
        and Path(path).suffix == ".pdf"
    ]
    if set(changed) != set(allowed):
        raise ContributionError("contribution PRs may only add PDFs under content/inbox/")
    if not allowed or len(allowed) > MAX_FILES:
        raise ContributionError(f"PDF count must be between 1 and {MAX_FILES}")
    sizes = [(submission / path).stat().st_size for path in allowed]
    if any(size > MAX_FILE_BYTES for size in sizes) or sum(sizes) > MAX_TOTAL_BYTES:
        raise ContributionError("contribution exceeds PDF size limits")
    return Delta(allowed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--thumbnails", type=Path, required=True)
    args = parser.parse_args()
    event = json.loads(args.event.read_text(encoding="utf-8"))
    delta = validate_delta(args.base, args.submission, event["pull_request"].get("body") or "")
    records = []
    for relative in delta.added_pdfs:
        inspected = inspect_pdf(args.submission / relative, args.thumbnails)
        records.append({
            "path": relative,
            "title": inspected.title,
            "title_source": inspected.title_source,
            "pages": inspected.pages,
            "sha256": inspected.sha256,
            "id": stable_item_id("community", inspected.title, inspected.sha256),
            "thumbnail": inspected.thumbnail.name,
        })
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({"items": records}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"items": records}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Add limit, modification, deletion, duplicate-name, and extension tests**

Add explicit tests for 11 PDFs, one file above 25 MiB, total above 100 MiB, an edited existing PDF, a deleted file, `CONTENT/INBOX/a.PDF`, and nested `content/inbox/folder/a.pdf`. Expected policy: only lowercase `.pdf` files directly inside `content/inbox/` pass.

- [ ] **Step 4: Run and commit**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_validate_contribution.py -v
python3 -m unittest discover -s tests -v
git add scripts/validate_contribution.py tests/test_validate_contribution.py
git commit -m "feat: validate PDF-only contribution PRs"
```

Expected: all policy tests and the full suite pass.

### Task 4: Put PDF parsing inside a restricted container

**Files:**
- Create: `ci/pdf-sandbox.Dockerfile`
- Create: `.dockerignore`
- Modify: `tests/test_validate_contribution.py`

- [ ] **Step 1: Create the pinned sandbox image**

Create `ci/pdf-sandbox.Dockerfile`:

```dockerfile
FROM python:3.14-slim@sha256:d3400aa122fa42cf0af0dbe8ec3091b047eac5c8f7e3539f7135e86d855dc015
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      imagemagick poppler-utils qpdf \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /trusted
COPY scripts/pdf_inspector.py scripts/validate_contribution.py scripts/
ENV PYTHONPATH=/trusted
ENTRYPOINT ["python3", "-m", "scripts.validate_contribution"]
```

Create `.dockerignore`:

```text
*
!scripts/pdf_inspector.py
!scripts/validate_contribution.py
```

- [ ] **Step 2: Build and run a valid fixture through the exact container restrictions**

Generate a base/submission/event tree with `tests.pdf_factory.write_pdf`, then run:

```bash
docker build -f ci/pdf-sandbox.Dockerfile -t lecture-to-notes-pdf-sandbox .
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 512m --cpus 1 --pids-limit 128 \
  --tmpfs /tmp:rw,size=256m \
  -v "$PWD/.tmp/base:/input/base:ro" \
  -v "$PWD/.tmp/submission:/input/submission:ro" \
  -v "$PWD/.tmp/event.json:/input/event.json:ro" \
  -v "$PWD/.tmp/report:/output:rw" \
  lecture-to-notes-pdf-sandbox \
  --base /input/base --submission /input/submission \
  --event /input/event.json --report /output/report.json \
  --thumbnails /output/thumbnails
```

Expected: exit 0, `report.json`, and one WebP thumbnail. Repeat with the active-content fixture and expect nonzero exit.

- [ ] **Step 3: Add an integration test that executes Docker when available**

Use `@unittest.skipUnless(shutil.which("docker"), "docker required")` and assert the valid/active fixture exit codes. Mark the test with the class name `PdfSandboxIntegrationTests` so CI can run it explicitly.

- [ ] **Step 4: Run and commit**

Run:

```bash
PYTHONPATH=.:tests python3 -m unittest test_validate_contribution -v
python3 -m unittest discover -s tests -v
git add ci/pdf-sandbox.Dockerfile .dockerignore tests/test_validate_contribution.py
git commit -m "ci: sandbox untrusted PDF inspection"
```

Expected: all tests pass and the image contains only the two trusted validation modules.

### Task 5: Migrate existing PDFs and add CS336

**Files:**
- Create: `scripts/migrate_legacy_site.mjs`
- Create: `content/courses/*/course.json`
- Create: `content/papers.json`
- Move: `docs/pdfs/*.pdf` to `content/courses/*/`
- Add: four CS336 PDFs from `/Users/shaoyiyang/Code/auto_study/stanford_cs336_spring2026/output/pdf/`

- [ ] **Step 1: Write the deterministic migration script**

The script must extract the trusted `const DATA` array literal with `vm.runInNewContext`, map categories exactly, preserve existing IDs/titles/meta/source URLs, and use `fs.renameSync` for PDFs:

```javascript
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = process.cwd();
const html = fs.readFileSync(path.join(root, 'docs/index.html'), 'utf8');
const match = html.match(/const DATA = (\[[\s\S]*?\n\]);/);
if (!match) throw new Error('legacy DATA array not found');
const data = vm.runInNewContext(match[1], Object.create(null), {timeout: 1000});
const groups = {
  nju: {id: 'nju-os', title: '操作系统：设计与实现', institution: '南京大学', term: '公开课', description: '从抽象、并发到文件系统的系统课程笔记。', tags: ['操作系统', '系统编程']},
  yt: {id: 'technical-lectures', title: '技术公开课精选', institution: 'Multiple', term: '精选', description: '软件、硬件与工程实践公开课。', tags: ['工程', '公开课']},
  sci: {id: 'science-explainers', title: '工程与科学科普', institution: 'Multiple', term: '精选', description: '面向学习者的工程与科学主题讲解。', tags: ['科学', '工程']},
  llm: {id: 'large-model-systems', title: '大模型系统与注意力优化', institution: 'Multiple', term: '精选', description: '大模型训练、推理与注意力系统笔记。', tags: ['LLM', '系统']},
  talk: {id: 'technical-talks', title: '技术与研究分享', institution: 'Multiple', term: '精选', description: '研究者与工程师的主题分享。', tags: ['研究', '分享']},
};
for (const [category, group] of Object.entries(groups)) {
  const directory = path.join(root, 'content/courses', group.id);
  fs.mkdirSync(directory, {recursive: true});
  const items = data.filter(item => item.type === 'lecture' && item.cat === category);
  for (const item of items) {
    const source = path.join(root, 'docs', item.pdf);
    const file = path.basename(item.pdf);
    fs.renameSync(source, path.join(directory, file));
    item.file = file;
    item.order = /^\d+$/.test(item.num) ? Number(item.num) : null;
    item.source_url = item.link;
    delete item.pdf; delete item.link; delete item.linkLabel; delete item.cat; delete item.type;
  }
  fs.writeFileSync(
    path.join(directory, 'course.json'),
    JSON.stringify({...group, items}, null, 2) + '\n'
  );
}
const papers = data.filter(item => item.type === 'paper');
fs.mkdirSync(path.join(root, 'content'), {recursive: true});
fs.writeFileSync(path.join(root, 'content/papers.json'), JSON.stringify(papers, null, 2) + '\n');
```

- [ ] **Step 2: Run migration and verify losslessness**

Run:

```bash
node scripts/migrate_legacy_site.mjs
test "$(find content/courses -name '*.pdf' | wc -l | tr -d ' ')" = 30
test "$(find docs/pdfs -name '*.pdf' 2>/dev/null | wc -l | tr -d ' ')" = 0
python3 -m json.tool content/papers.json >/dev/null
find content/courses -name course.json -exec python3 -m json.tool {} \; >/dev/null
```

Expected: 30 PDFs moved with no binary-content changes, five legacy course manifests, and nine paper records.

- [ ] **Step 3: Copy the four CS336 deliverables**

Run:

```bash
mkdir -p content/courses/stanford-cs336-2026
cp /Users/shaoyiyang/Code/auto_study/stanford_cs336_spring2026/output/pdf/stanford_cs336_lecture01_overview_tokenization_zh.pdf \
  content/courses/stanford-cs336-2026/stanford_cs336_2026_01_overview_tokenization_zh.pdf
cp /Users/shaoyiyang/Code/auto_study/stanford_cs336_spring2026/output/pdf/stanford_cs336_lecture02_pytorch_resource_accounting_zh.pdf \
  content/courses/stanford-cs336-2026/stanford_cs336_2026_02_pytorch_resource_accounting_zh.pdf
cp /Users/shaoyiyang/Code/auto_study/stanford_cs336_spring2026/output/pdf/stanford_cs336_lecture03_architectures_zh.pdf \
  content/courses/stanford-cs336-2026/stanford_cs336_2026_03_architectures_zh.pdf
cp /Users/shaoyiyang/Code/auto_study/stanford_cs336_spring2026/output/pdf/stanford_cs336_lectures_01_03_zh.pdf \
  content/courses/stanford-cs336-2026/stanford_cs336_2026_01_03_bundle_zh.pdf
```

Expected SHA equality with the source files for all four copies.

- [ ] **Step 4: Create the trusted CS336 manifest**

Create `content/courses/stanford-cs336-2026/course.json` with this exact metadata and page assertions:

```json
{
  "id": "stanford-cs336-2026",
  "title": "Stanford CS336: Language Modeling from Scratch",
  "institution": "Stanford University",
  "term": "Spring 2026",
  "description": "从分词、PyTorch 资源核算到语言模型架构的前三讲中文学习笔记。",
  "tags": ["language modeling", "PyTorch", "transformers"],
  "source_url": "https://cs336.stanford.edu/",
  "featured": true,
  "items": [
    {"file": "stanford_cs336_2026_01_overview_tokenization_zh.pdf", "title": "Lecture 1: Overview & Tokenization", "order": 1, "expected_pages": 30},
    {"file": "stanford_cs336_2026_02_pytorch_resource_accounting_zh.pdf", "title": "Lecture 2: PyTorch & Resource Accounting", "order": 2, "expected_pages": 33},
    {"file": "stanford_cs336_2026_03_architectures_zh.pdf", "title": "Lecture 3: Architectures", "order": 3, "expected_pages": 31},
    {"file": "stanford_cs336_2026_01_03_bundle_zh.pdf", "title": "Lectures 1–3 Complete Notes", "order": 4, "expected_pages": 94, "bundle": true}
  ]
}
```

- [ ] **Step 5: Verify PDFs and commit the content-only migration**

Run:

```bash
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --memory 1g --cpus 2 --pids-limit 256 --tmpfs /tmp:rw,size=256m \
  -v "$PWD/content:/input:ro" --entrypoint sh lecture-to-notes-pdf-sandbox \
  -lc 'find /input/courses -name "*.pdf" -print0 | xargs -0 -n1 qpdf --check'
find content/courses/stanford-cs336-2026 -name '*.pdf' -print0 | xargs -0 -n1 pdfinfo | rg '^Pages:'
git diff --summary -- docs/pdfs content/courses
git add -A -- scripts/migrate_legacy_site.mjs content docs/pdfs
git commit -m "content: organize courses and add CS336 lectures"
```

Expected: qpdf accepts every PDF, CS336 pages are 30/33/31/94, and Git recognizes legacy PDF moves rather than replacements.

### Task 6: Build a deterministic catalog and `_site` artifact

**Files:**
- Create: `scripts/site_catalog.py`
- Create: `scripts/build_site.py`
- Create: `scripts/build_site_container.sh`
- Create: `tests/test_site_catalog.py`
- Create: `tests/test_build_site.py`
- Modify: `ci/pdf-sandbox.Dockerfile`
- Modify: `.dockerignore`
- Create generated directory during tests: `_site/`

- [ ] **Step 1: Write failing catalog tests**

Test exact schema version `1`, deterministic course/item ordering, unique IDs and output basenames, trusted title override, inbox fallback, page-count mismatch rejection, HTTPS source validation, and repo-size warning at 750 MiB.

Use this expected top-level shape:

```python
expected_keys = {"schema_version", "generated_at", "stats", "courses", "items", "papers"}
self.assertEqual(expected_keys, set(catalog))
self.assertEqual(1, catalog["schema_version"])
self.assertEqual(
    {"lecture_count", "paper_count", "page_count", "course_count", "pdf_bytes"},
    set(catalog["stats"]),
)
```

- [ ] **Step 2: Implement catalog composition**

Create typed helpers in `scripts/site_catalog.py`:

```python
def load_course_manifest(path: Path) -> dict:
    """Load JSON and reject missing course id, title, institution, term, or items."""

def inspect_course(directory: Path, thumbnail_dir: Path) -> tuple[dict, list[dict]]:
    """Inspect manifest PDFs, enforce expected page counts, and return course/items."""

def inspect_inbox(directory: Path, thumbnail_dir: Path) -> tuple[dict, list[dict]]:
    """Inspect direct child PDFs and return the deterministic community course/items."""

def load_papers(path: Path) -> list[dict]:
    """Load paper metadata and require each referenced local HTML file."""

def build_catalog(content_root: Path, output_root: Path, generated_at: str) -> dict:
    """Build, validate, and return the schema-version-1 catalog."""

def validate_catalog(catalog: dict, output_root: Path) -> None:
    """Reject duplicate ids/basenames, missing outputs, non-HTTPS sources, or bad stats."""
```

Rules: manifest item order first, then title; bundle last; community sorted by title; item IDs remain stable; trusted `title` wins while extracted title is kept as `detected_title`; output paths are `pdfs/<basename>` and `thumbnails/<digest16>.webp`; duplicate basenames fail before copying.

- [ ] **Step 3: Write failing build tests**

Build a temporary source tree containing one curated PDF, one inbox PDF, one paper HTML, and source shell files. Assert:

```python
self.assertTrue((output / "index.html").is_file())
self.assertTrue((output / "reader.html").is_file())
self.assertTrue((output / "contribute.html").is_file())
self.assertTrue((output / "data/catalog.json").is_file())
self.assertTrue((output / "pdfs/legacy-name.pdf").is_file())
self.assertFalse((output / "superpowers").exists())
self.assertFalse(any(output.rglob(".DS_Store")))
```

- [ ] **Step 4: Implement the site builder**

Create `scripts/build_site.py` with CLI flags `--root`, `--output`, and `--generated-at`. It must remove and recreate only the requested output directory, copy `docs/` while ignoring `pdfs`, `superpowers`, `.DS_Store`, copy papers, call `build_catalog`, write UTF-8 JSON with sorted keys, and never modify `content/` or `docs/`.

Then extend `ci/pdf-sandbox.Dockerfile` to copy `scripts/site_catalog.py` and `scripts/build_site.py`, and add both paths to `.dockerignore`. Rebuild `lecture-to-notes-pdf-sandbox` before the real build.

Create executable `scripts/build_site_container.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTPUT="${1:-$ROOT/_site}"
STAGING="$ROOT/.tmp/site-build"
rm -rf "$OUTPUT" "$STAGING"
mkdir -p "$STAGING"
docker build -f "$ROOT/ci/pdf-sandbox.Dockerfile" -t lecture-to-notes-pdf-sandbox "$ROOT"
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --memory 1g --cpus 2 --pids-limit 256 \
  --tmpfs /tmp:rw,size=256m \
  -v "$ROOT:/input:ro" -v "$STAGING:/output:rw" \
  --entrypoint python3 lecture-to-notes-pdf-sandbox -m scripts.build_site \
  --root /input --output /output/site --generated-at 2026-07-16T00:00:00Z
mv "$STAGING/site" "$OUTPUT"
```

- [ ] **Step 5: Run the real build and verify legacy paths**

Run:

```bash
scripts/build_site_container.sh
python3 -m json.tool _site/data/catalog.json >/dev/null
test -f _site/pdfs/nju_os_01_intro.pdf
test -f _site/pdfs/stanford_cs336_2026_01_03_bundle_zh.pdf
```

Expected: deterministic catalog, 34 PDFs, four CS336 assets, and all old PDF basenames.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_site_catalog.py tests/test_build_site.py -v
python3 -m unittest discover -s tests -v
git add scripts/site_catalog.py scripts/build_site.py scripts/build_site_container.sh tests/test_site_catalog.py tests/test_build_site.py ci/pdf-sandbox.Dockerfile .dockerignore
git commit -m "feat: build the course catalog site artifact"
```

Expected: all tests pass; `_site/` remains untracked.

### Task 7: Build the Technical Study Desk course library

**Files:**
- Replace: `docs/index.html`
- Create: `docs/assets/styles.css`
- Create: `docs/assets/catalog.js`
- Create: `docs/assets/components.js`
- Create: `docs/assets/home.js`
- Create: `tests/test_site_contract.py`

- [ ] **Step 1: Write the semantic and XSS-safety contract tests**

Assert that the homepage contains a skip link, real `<nav>`, search input with a label, course region, empty state, module script, no inline `onclick`, and no hard-coded `const DATA`. Assert browser components use `textContent`/`setAttribute` and do not assign catalog values through `innerHTML`.

- [ ] **Step 2: Implement catalog loading and search**

Create `docs/assets/catalog.js`:

```javascript
export async function loadCatalog() {
  const response = await fetch('./data/catalog.json', {credentials: 'same-origin'});
  if (!response.ok) throw new Error(`Catalog request failed: ${response.status}`);
  const catalog = await response.json();
  if (catalog.schema_version !== 1) throw new Error('Unsupported catalog schema');
  return catalog;
}

export function normalize(value) {
  return String(value ?? '').normalize('NFKC').toLocaleLowerCase('zh-CN');
}

export function searchCourses(catalog, query) {
  const needle = normalize(query).trim();
  if (!needle) return catalog.courses;
  const items = new Map(catalog.items.map(item => [item.id, item]));
  return catalog.courses.filter(course => {
    const lectures = course.item_ids.map(id => items.get(id)).filter(Boolean);
    return [course.title, course.institution, course.term, ...(course.tags || []),
      ...lectures.flatMap(item => [item.title, item.instructor])]
      .some(value => normalize(value).includes(needle));
  });
}
```

- [ ] **Step 3: Implement DOM-only components**

`createCourseCard(course, items)` must use `document.createElement`, `textContent`, and `href` built from `URLSearchParams`; render institution/term, title, description, lecture/page metrics, and one tick per item. `createItemRow(item)` must expose title, page count, source, and `reader.html?id=<encoded-id>`.

- [ ] **Step 4: Replace the homepage shell**

Use this exact landmark structure:

```html
<a class="skip-link" href="#main">跳到正文</a>
<header class="site-header"><nav aria-label="主导航"><a href="index.html">课程图书馆</a><a href="contribute.html">贡献 PDF</a></nav></header>
<main id="main">
  <section class="hero" aria-labelledby="hero-title"><p class="eyebrow">LECTURE ARCHIVE</p><h1 id="hero-title">把一门课，读成一张可探索的学习桌</h1><p>按课程浏览、搜索讲次，并在专用阅读页继续阅读。</p></section>
  <section class="library" aria-labelledby="library-title">
    <label for="course-search">搜索课程、讲次或主题</label>
    <input id="course-search" type="search" autocomplete="off">
    <p id="library-status" role="status" aria-live="polite"></p>
    <div id="course-grid" class="course-grid"></div>
    <div id="course-detail" hidden></div>
    <p id="empty-state" hidden>没有匹配内容，请尝试课程名、讲次或主题。</p>
  </section>
</main>
<script type="module" src="assets/home.js"></script>
```

- [ ] **Step 5: Implement homepage state and hash routing**

`home.js` must render courses on load, debounce search by 120 ms, update the live result count, open `#course=<id>` details, restore focus when returning, and render a clear catalog-error state with a retry button.

- [ ] **Step 6: Implement the approved visual system**

In `styles.css`, define the exact tokens `--lab-paper:#f7fafb`, `--blueprint:#173a50`, `--ink-blue:#2f6bff`, `--annotation:#ff6b5b`, `--grid-line:#ccd8e0`; use Sora/Noto Sans SC/IBM Plex Mono with system fallbacks. Implement course spine/ticks, visible focus, AA contrast, a single page-enter transition, `prefers-reduced-motion`, and mobile breakpoints at 820px and 560px.

- [ ] **Step 7: Run contracts and commit**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_site_contract.py -v
scripts/build_site_container.sh
python3 -m http.server 4173 --directory _site
```

Inspect desktop and mobile widths, stop the server, then:

```bash
git add docs/index.html docs/assets tests/test_site_contract.py
git commit -m "feat: redesign the course library"
```

Expected: semantic tests pass and CS336 is the featured course.

### Task 8: Add the shareable PDF reader

**Files:**
- Create: `docs/reader.html`
- Create: `docs/assets/reader.js`
- Modify: `docs/assets/styles.css`
- Modify: `tests/test_site_contract.py`

- [ ] **Step 1: Add failing reader contract tests**

Assert labeled course navigation, title/status regions, iframe title, direct-open and download links, source link, invalid-item state, mobile selector, no arbitrary `pdf` query parameter, and module script.

- [ ] **Step 2: Create the semantic reader shell**

Use `reader.html?id=<catalog-id>` only. Include `#course-nav`, `#mobile-item-select`, `#reader-title`, `#reader-meta`, `#pdf-frame`, `#open-pdf`, `#download-pdf`, `#source-link`, and `#reader-error`. Keep fallback links visible whenever a valid item is selected.

- [ ] **Step 3: Implement catalog-whitelisted navigation**

`reader.js` must read only `id`, find the item in the catalog, derive the PDF URL from `item.pdf`, set `iframe.src` to `${item.pdf}#view=FitH`, set link hrefs, render previous/next course items, and show a 404-like error for missing IDs. Never accept an external URL from query parameters.

- [ ] **Step 4: Add responsive reader styles**

Desktop uses a 240px course rail and full-height canvas; mobile hides the rail, shows the native `<select>`, and emphasizes direct-open/download because embedded PDFs are unreliable on iOS.

- [ ] **Step 5: Test, build, and commit**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_site_contract.py -v
scripts/build_site_container.sh
git add docs/reader.html docs/assets/reader.js docs/assets/styles.css tests/test_site_contract.py
git commit -m "feat: add shareable course PDF reader"
```

Expected: valid deep links work, invalid IDs provide recovery, and no query parameter can load a foreign PDF.

### Task 9: Add the GitHub contribution page and templates

**Files:**
- Create: `docs/contribute.html`
- Create: `.github/PULL_REQUEST_TEMPLATE/pdf-contribution.md`
- Create: `CONTRIBUTING.md`
- Modify: `docs/assets/styles.css`
- Modify: `tests/test_site_contract.py`

- [ ] **Step 1: Write failing contribution-page tests**

Assert the page says PDFs remain unpublished until merge, lists 25 MiB/10 file/100 MiB limits, links to `https://github.com/ysyecust/lecture-to-notes/upload/main/content/inbox`, and names the exact rights checkbox.

- [ ] **Step 2: Implement the contribution page**

Provide a three-step flow: fork/upload, automated check, maintainer merge. The primary CTA is “在 GitHub 上传 PDF”; the page must not claim the website receives files directly.

- [ ] **Step 3: Add the PR template**

Create:

```markdown
## PDF contribution

- [ ] I only added PDF files directly under `content/inbox/`.
- [ ] Every PDF is 25 MiB or smaller; this PR contains at most 10 PDFs and 100 MiB total.
- [ ] I have the right to share these PDFs for educational use.

## Context

Course or event name:

Original source URL:
```

- [ ] **Step 4: Document local and GitHub contribution paths**

`CONTRIBUTING.md` must show browser upload and command-line fork commands, explain automatic title/page/thumbnail extraction, state that maintainers may retitle or regroup content, and link the security policy.

- [ ] **Step 5: Test and commit**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_site_contract.py -v
git add docs/contribute.html docs/assets/styles.css .github/PULL_REQUEST_TEMPLATE/pdf-contribution.md CONTRIBUTING.md tests/test_site_contract.py
git commit -m "docs: add the PDF contribution flow"
```

Expected: contracts pass and the rights marker exactly matches `validate_contribution.py`.

### Task 10: Add browser-level verification

**Files:**
- Create: `package.json`
- Create: `package-lock.json`
- Create: `playwright.config.mjs`
- Create: `e2e/site.spec.mjs`
- Modify: `.gitignore`

- [ ] **Step 1: Add the pinned browser test dependency**

Create `package.json`:

```json
{
  "name": "lecture-to-notes-site",
  "private": true,
  "scripts": {"test:e2e": "playwright test"},
  "devDependencies": {"@playwright/test": "1.61.1"}
}
```

Run:

```bash
npm install
npx playwright install chromium
```

Expected: a lockfile pins the dependency tree and Chromium installs successfully.

- [ ] **Step 2: Configure the deterministic local server**

Create `playwright.config.mjs` with base URL `http://127.0.0.1:4173`, desktop Chromium and iPhone 14 projects, `webServer.command` equal to `python3 -m http.server 4173 --directory _site`, reuse disabled in CI, and trace retained on failure.

- [ ] **Step 3: Write end-to-end tests**

Cover:

```javascript
test('search finds CS336 and opens its lecture list', async ({page}) => {
  await page.goto('/');
  await page.getByLabel('搜索课程、讲次或主题').fill('Tokenization');
  await expect(page.getByRole('heading', {name: /Language Modeling from Scratch/})).toBeVisible();
  await page.getByRole('link', {name: /查看课程/}).click();
  await expect(page.getByRole('link', {name: /Overview & Tokenization/})).toBeVisible();
});

test('reader exposes direct PDF recovery actions', async ({page, request}) => {
  const catalog = await (await request.get('/data/catalog.json')).json();
  const item = catalog.items.find(entry => entry.course_id === 'stanford-cs336-2026' && entry.kind === 'lecture');
  await page.goto(`/reader.html?id=${encodeURIComponent(item.id)}`);
  await expect(page.getByRole('link', {name: '直接打开 PDF'})).toHaveAttribute('href', /pdfs\/.+\.pdf/);
  await expect(page.getByRole('link', {name: '下载 PDF'})).toHaveAttribute('download', /\.pdf$/);
});

test('contribution page routes uploads to GitHub', async ({page}) => {
  await page.goto('/contribute.html');
  await expect(page.getByRole('link', {name: '在 GitHub 上传 PDF'})).toHaveAttribute('href', /github\.com\/ysyecust\/lecture-to-notes\/upload\/main\/content\/inbox/);
});
```

The reader test resolves the generated ID from `_site/data/catalog.json`; it never hard-codes a digest suffix.

- [ ] **Step 4: Capture review screenshots**

Tests write desktop/mobile homepage and reader screenshots to `artifacts/site-review/`; `.gitignore` ignores `artifacts/`, `test-results/`, `playwright-report/`, `_site/`, and `.tmp/`.

- [ ] **Step 5: Run all verification and commit**

Run:

```bash
scripts/build_site_container.sh
npm run test:e2e
python3 -m unittest discover -s tests -v
git add package.json package-lock.json playwright.config.mjs e2e/site.spec.mjs .gitignore
git commit -m "test: cover course library browser flows"
```

Expected: desktop and iPhone projects pass; screenshots are reviewable but untracked.

### Task 11: Add unprivileged contribution CI and trusted Pages deployment

**Files:**
- Create: `.github/workflows/contribution-check.yml`
- Create: `.github/workflows/pages.yml`
- Create: `tests/test_workflow_security.py`

- [ ] **Step 1: Write workflow security tests before YAML**

Parse workflow text and assert no `pull_request_target`, `workflow_run`, self-hosted runner, unpinned `uses`, write token in contribution job, or checkout with persisted credentials. Assert only the Pages deploy job contains `pages: write` and `id-token: write`.

- [ ] **Step 2: Create the contribution workflow**

Use these immutable action SHAs:

- checkout: `df4cb1c069e1874edd31b4311f1884172cec0e10`
- upload-artifact: `ea165f8d65b6e75b540449e92b4886f43607fa02`

The workflow triggers on `pull_request` paths `content/inbox/**`, declares `permissions: contents: read`, checks out base to `trusted` and PR head to `submission` with `persist-credentials:false`, builds `trusted/ci/pdf-sandbox.Dockerfile`, runs the exact restricted container flags from Task 4, writes the event JSON from `$GITHUB_EVENT_PATH` into a read-only mount, and uploads only the JSON report and generated thumbnails.

- [ ] **Step 3: Create the Pages workflow**

Use immutable SHAs:

- checkout: `df4cb1c069e1874edd31b4311f1884172cec0e10`
- configure-pages: `983d7736d9b0ae728b81ab479565c72886d7745b`
- upload-pages-artifact: `7b1f4a764d45c48632c6b24a0339c27f5614fb0b`
- deploy-pages: `d6db90164ac5ed86f2b6aed7e0febac5b3c0c03e`

The `build` job has `contents: read`, runs Python and npm tests, builds `_site` with `docker run --entrypoint python3` against the pinned PDF sandbox and writable `/output`, and uploads `_site`. The `deploy` job needs `build`, uses environment `github-pages`, and alone has `pages: write` plus `id-token: write`.

- [ ] **Step 4: Run security tests and local workflow-equivalent commands**

Run:

```bash
PYTHONPATH=. python3 -m unittest tests/test_workflow_security.py -v
python3 -m unittest discover -s tests -v
scripts/build_site_container.sh
npm run test:e2e
```

Expected: all security, unit, and browser tests pass.

- [ ] **Step 5: Commit workflows**

Run:

```bash
git add .github/workflows tests/test_workflow_security.py
git commit -m "ci: validate contributions and deploy Pages"
```

Expected: workflow files contain only pinned actions and least-privilege permissions.

### Task 12: Update documentation, release notes, and repository guidance

**Files:**
- Modify: `README.md`
- Modify: `RELEASE_NOTES.md`
- Create: `.github/ISSUE_TEMPLATE/pdf-contribution.yml`
- Modify: `tests/test_release_notes.py`

- [ ] **Step 1: Add failing documentation tests**

Assert README names `content/inbox`, fork/PR review, 25 MiB, automatic title/pages/thumbnail, CS336 Spring 2026, course reader, and HTTPS site URL. Assert release notes name the course-library redesign and contribution security boundary.

- [ ] **Step 2: Update README and release notes**

Document the new source tree, local build command, contributor path, security model, Pages build, and CS336 assets. Add a dated 2026-07-16 release section crediting PR #4 separately from the website work.

- [ ] **Step 3: Add a structured contribution issue form**

The form asks for course/event name, source URL, approximate PDF count/size, and rights confirmation, then directs ready files to the PR upload path. It does not accept file contents or promise automatic publication.

- [ ] **Step 4: Run all tests and commit**

Run:

```bash
python3 -m unittest discover -s tests -v
scripts/build_site_container.sh
npm run test:e2e
git diff --check
git add README.md RELEASE_NOTES.md .github/ISSUE_TEMPLATE/pdf-contribution.yml tests/test_release_notes.py
git commit -m "docs: publish the course contribution workflow"
```

Expected: all suites pass and documentation matches live behavior.

### Task 13: Review, publish, and test the real contribution loop

**Files:**
- Review only: complete branch diff
- External state: feature PR, GitHub Pages source, Issues #3/#5

- [ ] **Step 1: Run the full local release gate**

Run:

```bash
python3 -m unittest discover -s tests -v
scripts/build_site_container.sh
npm ci
npx playwright install chromium
npm run test:e2e
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  -v "$PWD/_site:/site:ro" --entrypoint sh lecture-to-notes-pdf-sandbox \
  -lc 'find /site/pdfs -name "*.pdf" -print0 | xargs -0 -n1 qpdf --check'
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: green unit/E2E/PDF gates, clean worktree, and no unrelated files.

- [ ] **Step 2: Push and create the feature PR**

Run:

```bash
git push -u origin feat/course-library-pdf-contributions
gh pr create --repo ysyecust/lecture-to-notes \
  --base main --head feat/course-library-pdf-contributions \
  --title "feat: publish course library and PDF contribution workflow" \
  --body-file docs/superpowers/specs/2026-07-16-course-library-pdf-upload-design.md
```

Expected: one PR containing the approved design, implementation, tests, four CS336 PDFs, and no user-untracked artifacts.

- [ ] **Step 3: Review diff, checks, and screenshots before merge**

Run:

```bash
gh pr checks --watch --repo ysyecust/lecture-to-notes
gh pr diff --repo ysyecust/lecture-to-notes --name-only
```

Confirm the file allowlist, inspect desktop/mobile screenshots, verify CS336 PDF SHA/page counts, and confirm the contribution workflow has no secrets or privileged fork trigger.

- [ ] **Step 4: Merge and switch Pages to workflow deployment**

Run:

```bash
gh pr merge --repo ysyecust/lecture-to-notes --merge --delete-branch
gh api --method PUT repos/ysyecust/lecture-to-notes/pages -f build_type=workflow
gh run list --repo ysyecust/lecture-to-notes --workflow pages.yml --limit 3
```

Expected: PR merged, Pages source reports `workflow`, and the main deployment succeeds.

- [ ] **Step 5: Verify live HTTPS endpoints**

Run:

```bash
curl -fsSIL https://blog.simona.plus/lecture-to-notes/
curl -fsS https://blog.simona.plus/lecture-to-notes/data/catalog.json | jq '.stats'
curl -fsSIL https://blog.simona.plus/lecture-to-notes/reader.html
for pdf in \
  stanford_cs336_2026_01_overview_tokenization_zh.pdf \
  stanford_cs336_2026_02_pytorch_resource_accounting_zh.pdf \
  stanford_cs336_2026_03_architectures_zh.pdf \
  stanford_cs336_2026_01_03_bundle_zh.pdf; do
  curl -fsSIL "https://blog.simona.plus/lecture-to-notes/pdfs/$pdf"
done
gh api --method PUT repos/ysyecust/lecture-to-notes/pages -F https_enforced=true
```

Expected: every request returns 200, catalog stats include CS336, and HTTPS enforcement is enabled.

- [ ] **Step 6: Exercise a real fork-style contribution**

Create a disposable fork branch that adds one already-public small PDF to `content/inbox/`, uses the exact rights checkbox, and opens a PR. Confirm manual workflow approval, read-only validation, parsed title/pages/thumbnail artifact, and no Pages deployment before merge. Close the test PR without merging if it duplicates a published asset.

- [ ] **Step 7: Update contributor issues**

Verify Issue #3 is closed by PR #4. Comment on Issue #5 with the new contribution page and `content/inbox/` upload link, explain the 25 MiB limit, and keep it open until the 17 PDFs are actually submitted.

- [ ] **Step 8: Record final evidence**

Capture feature PR URL, merge commit, Pages run URL, live catalog stats, four PDF status results, real contribution-check run, and final local test counts in the handoff. Remove the feature worktree only after all evidence is recorded and the branch is merged.
