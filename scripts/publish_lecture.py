#!/usr/bin/env python3
"""
One-step lecture publisher and README stats synchronizer.

Replaces the manual 6-step release routine after `verify_notes.py` passes:
  1. Copy `<workdir>/notes.pdf` -> `content/courses/<course>/<file>.pdf`
  2. Archive `<workdir>/notes.tex` + referenced `figures/*` -> `content/courses/<course>/source/<slug>/`
  3. Inspect PDF page count and read duration/URL from `<workdir>/metadata.json`
  4. Run `web_notes.convert(..., review=True)` to generate the verified `web_source` block
  5. Insert or update the item entry in `content/courses/<course>/course.json`
  6. Synchronize course/lecture/page counts in `README.md` and `README.en.md`

Usage:
    # Check or synchronize README.md / README.en.md stats from course manifests:
    python3 -m scripts.publish_lecture --root . --check-readme
    python3 -m scripts.publish_lecture --root . --sync-readme

    # Publish a verified workspace into a course:
    python3 -m scripts.publish_lecture --root . \\
        --workdir workspace/bili_BVxxx \\
        --course content/courses/technical-talks/course.json \\
        --file my_lecture_zh.pdf \\
        --slug my_lecture \\
        --title "讲座标题" \\
        --instructor "主讲人"
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.verify_notes import FIGURE_RE
from scripts.web_notes import convert, digest


ZH_STATS_RE = re.compile(
    r"(当前共\s*)(\d+)(\s*门课程与专题、)(\d+)(\s*讲、)([\d,]+)(\s*页正课讲义)"
)
EN_STATS_RE = re.compile(
    r"(currently\s+)(\d+)(\s+courses and collections,\s+)(\d+)(\s+lectures,\s+and\s+)([\d,]+)(\s+lecture pages)"
)


def pdf_page_count(pdf_path: Path) -> int:
    if shutil.which("pdfinfo"):
        out = subprocess.check_output(["pdfinfo", str(pdf_path)], text=True, timeout=30)
        for line in out.splitlines():
            key, sep, val = line.partition(":")
            if sep and key.strip() == "Pages":
                return int(val.strip())
    data = pdf_path.read_bytes()
    counts = [int(m) for m in re.findall(rb"/Type\s*/Pages\b[^>]*/Count\s+(\d+)", data)]
    if counts:
        return max(counts)
    raise ValueError(f"cannot determine page count for {pdf_path}")


def manifest_stats(root: Path) -> dict[str, int]:
    """Compute course_count, lecture_count, and page_count from course manifests."""
    root = root.resolve()
    courses_dir = root / "content/courses"
    course_count = 0
    lecture_count = 0
    page_count = 0
    for manifest_path in sorted(courses_dir.glob("*/course.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = manifest.get("items", [])
        non_bundle = [item for item in items if not item.get("bundle")] or items
        course_count += 1
        lecture_count += len(non_bundle)
        for item in non_bundle:
            pages = item.get("expected_pages")
            if pages is None:
                pages = pdf_page_count(manifest_path.parent / item["file"])
            page_count += int(pages)
    inbox_dir = root / "content/inbox"
    if inbox_dir.is_dir():
        inbox_pdfs = sorted(
            p for p in inbox_dir.iterdir()
            if p.is_file() and not p.is_symlink() and p.suffix == ".pdf"
        )
        if inbox_pdfs:
            course_count += 1
            lecture_count += len(inbox_pdfs)
            page_count += sum(pdf_page_count(p) for p in inbox_pdfs)
    return {
        "course_count": course_count,
        "lecture_count": lecture_count,
        "page_count": page_count,
    }


def sync_readme_stats(root: Path, check_only: bool = False) -> dict[str, int]:
    """Update or check course/lecture/page counts in README.md and README.en.md."""
    root = root.resolve()
    stats = manifest_stats(root)
    courses_s = str(stats["course_count"])
    lectures_s = str(stats["lecture_count"])
    pages_s = f"{stats['page_count']:,}"

    zh_path = root / "README.md"
    en_path = root / "README.en.md"
    if zh_path.is_file():
        zh_text = zh_path.read_text(encoding="utf-8")
        match = ZH_STATS_RE.search(zh_text)
        if not match:
            raise ValueError("README.md is missing the Chinese course-stats summary pattern")
        updated_zh = ZH_STATS_RE.sub(
            rf"\g<1>{courses_s}\g<3>{lectures_s}\g<5>{pages_s}\g<7>",
            zh_text,
            count=1,
        )
        if check_only and updated_zh != zh_text:
            raise ValueError(
                f"README.md stats out of sync: expected {courses_s} courses, {lectures_s} lectures, {pages_s} pages"
            )
        if not check_only and updated_zh != zh_text:
            zh_path.write_text(updated_zh, encoding="utf-8")

    if en_path.is_file():
        en_text = en_path.read_text(encoding="utf-8")
        match = EN_STATS_RE.search(en_text)
        if not match:
            raise ValueError("README.en.md is missing the English course-stats summary pattern")
        updated_en = EN_STATS_RE.sub(
            rf"\g<1>{courses_s}\g<3>{lectures_s}\g<5>{pages_s}\g<7>",
            en_text,
            count=1,
        )
        if check_only and updated_en != en_text:
            raise ValueError(
                f"README.en.md stats out of sync: expected {courses_s} courses, {lectures_s} lectures, {pages_s} pages"
            )
        if not check_only and updated_en != en_text:
            en_path.write_text(updated_en, encoding="utf-8")

    return stats


def publish_workdir(
    root: Path,
    workdir: Path,
    course_manifest: Path,
    pdf_filename: str,
    slug: str,
    title: str,
    *,
    instructor: str = "",
    order: int | None = None,
    duration_minutes: int | None = None,
    source_url: str = "",
    source_label: str = "",
    meta: str = "",
    include_web_source: bool = True,
) -> dict[str, object]:
    """Archive a verified workspace into a course directory and update manifests."""
    root = root.resolve()
    workdir = workdir.resolve()
    course_manifest = course_manifest.resolve()
    course_dir = course_manifest.parent

    if not pdf_filename.endswith(".pdf") or Path(pdf_filename).name != pdf_filename:
        raise ValueError("pdf_filename must be a flat .pdf filename")
    src_pdf = workdir / "notes.pdf"
    if not src_pdf.is_file():
        raise ValueError(f"missing compiled PDF: {src_pdf}")

    pages = pdf_page_count(src_pdf)
    meta_path = workdir / "metadata.json"
    if meta_path.is_file():
        raw_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if duration_minutes is None and raw_meta.get("duration"):
            duration_minutes = max(1, round(float(raw_meta["duration"]) / 60.0))
        if not source_url and raw_meta.get("webpage_url"):
            source_url = str(raw_meta["webpage_url"])
    if not source_label and source_url:
        if "bilibili.com" in source_url:
            source_label = "B站"
        elif "youtube.com" in source_url or "youtu.be" in source_url:
            source_label = "YouTube"
        elif "x.com" in source_url or "twitter.com" in source_url:
            source_label = "X"

    dest_pdf = course_dir / pdf_filename
    shutil.copy2(src_pdf, dest_pdf)

    web_source = None
    src_tex = workdir / "notes.tex"
    if include_web_source and src_tex.is_file():
        rel_tex = f"source/{slug}/notes.tex" if slug else "source/notes.tex"
        dest_tex = course_dir / rel_tex
        dest_source_dir = dest_tex.parent
        dest_source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_tex, dest_tex)

        tex_content = src_tex.read_text(encoding="utf-8")
        for match in FIGURE_RE.finditer(tex_content):
            fig_rel = match.group(1).strip()
            if not fig_rel or fig_rel.startswith("\\"):
                continue
            src_fig = workdir / fig_rel
            if src_fig.is_file():
                dst_fig = dest_source_dir / fig_rel
                dst_fig.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_fig, dst_fig)

        with tempfile.TemporaryDirectory() as tmp:
            report = convert(
                dest_tex,
                dest_source_dir,
                Path(tmp),
                {},
                {
                    "id": "review",
                    "title": title,
                    "source_url": source_url,
                    "sha256": digest(dest_pdf),
                },
                review=True,
            )
        web_source = {
            "tex": rel_tex,
            "sha256": digest(dest_tex),
            "pdf_sha256": digest(dest_pdf),
            "expected": report["counts"],
            "resources": {r["path"]: r["sha256"] for r in report["resources"]},
        }

    manifest = json.loads(course_manifest.read_text(encoding="utf-8"))
    items: list[dict[str, object]] = manifest.get("items", [])
    existing = next((item for item in items if item.get("file") == pdf_filename), None)
    if order is None:
        if existing and existing.get("order"):
            order = int(existing["order"])
        else:
            non_bundle_orders = [int(i.get("order") or 0) for i in items if not i.get("bundle")]
            order = (max(non_bundle_orders) if non_bundle_orders else 0) + 1

    if not meta:
        parts = [p for p in (instructor.split("(")[0].strip() if instructor else "", f"{duration_minutes}min" if duration_minutes else "", f"{pages}页") if p]
        meta = " · ".join(parts)

    entry: dict[str, object] = existing if existing is not None else {}
    entry["file"] = pdf_filename
    entry["title"] = title
    entry["order"] = order
    entry["expected_pages"] = pages
    if duration_minutes is not None:
        entry["duration_minutes"] = duration_minutes
    if instructor:
        entry["instructor"] = instructor
    if source_url:
        entry["source_url"] = source_url
    if source_label:
        entry["source_label"] = source_label
    if meta:
        entry["meta"] = meta
    if web_source is not None:
        entry["web_source"] = web_source

    if existing is None:
        items.append(entry)
    manifest["items"] = items
    course_manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    stats = sync_readme_stats(root, check_only=False)
    return {"entry": entry, "stats": stats}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--check-readme", action="store_true", help="verify README.md and README.en.md stats match manifests")
    parser.add_argument("--sync-readme", action="store_true", help="update README.md and README.en.md stats from manifests")
    parser.add_argument("--workdir", type=Path, help="workspace directory containing notes.pdf and notes.tex")
    parser.add_argument("--course", type=Path, help="target course.json path")
    parser.add_argument("--file", help="target PDF filename in course directory")
    parser.add_argument("--slug", default="", help="subfolder name under source/ for archived TeX")
    parser.add_argument("--title", help="lecture title")
    parser.add_argument("--instructor", default="")
    parser.add_argument("--order", type=int, default=None)
    parser.add_argument("--duration-minutes", type=int, default=None)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-label", default="")
    parser.add_argument("--meta", default="")
    parser.add_argument("--no-web", action="store_true", help="publish PDF only without web_source")
    args = parser.parse_args(argv)

    if args.check_readme:
        stats = sync_readme_stats(args.root, check_only=True)
        print(json.dumps(stats, sort_keys=True))
        return 0
    if args.sync_readme and not args.workdir:
        stats = sync_readme_stats(args.root, check_only=False)
        print(json.dumps(stats, sort_keys=True))
        return 0
    if not (args.workdir and args.course and args.file and args.title):
        parser.error("publishing a lecture requires --workdir, --course, --file, and --title (or use --sync-readme / --check-readme)")
    result = publish_workdir(
        args.root,
        args.workdir,
        args.course,
        args.file,
        args.slug,
        args.title,
        instructor=args.instructor,
        order=args.order,
        duration_minutes=args.duration_minutes,
        source_url=args.source_url,
        source_label=args.source_label,
        meta=args.meta,
        include_web_source=not args.no_web,
    )
    print(json.dumps(result["stats"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
