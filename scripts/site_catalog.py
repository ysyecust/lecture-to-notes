from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from scripts.pdf_inspector import PdfInspection, inspect_pdf, stable_item_id


CatalogError = ValueError
Inspector = Callable[[Path, Path], PdfInspection]
REPO_WARNING_BYTES = 750 * 1024 * 1024
REQUIRED_COURSE_FIELDS = ("id", "title", "institution", "term", "items")


def _https_or_empty(value: str, label: str) -> str:
    value = value.strip()
    if value and urlparse(value).scheme != "https":
        raise CatalogError(f"{label} must use HTTPS")
    return value


def load_course_manifest(path: Path) -> dict[str, object]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"invalid course manifest: {path}") from error
    if not isinstance(manifest, dict):
        raise CatalogError(f"course manifest must be an object: {path}")
    missing = [field for field in REQUIRED_COURSE_FIELDS if field not in manifest]
    if missing:
        raise CatalogError(f"course manifest missing {', '.join(missing)}: {path}")
    for field in ("id", "title", "institution", "term"):
        if not isinstance(manifest[field], str) or not manifest[field].strip():
            raise CatalogError(f"course field {field} must be a non-empty string")
    if not isinstance(manifest["items"], list):
        raise CatalogError("course items must be a list")
    _https_or_empty(str(manifest.get("source_url", "")), "course source_url")
    return manifest


def _safe_pdf(directory: Path, filename: object) -> Path:
    if not isinstance(filename, str) or not filename.endswith(".pdf"):
        raise CatalogError("course item file must be a lowercase .pdf filename")
    if Path(filename).name != filename:
        raise CatalogError("course item file must not contain a directory")
    path = directory / filename
    if path.is_symlink() or not path.is_file():
        raise CatalogError(f"course PDF missing or unsafe: {path}")
    return path


def _item_record(
    course_id: str,
    manifest_item: dict[str, object],
    inspected: PdfInspection,
    source_pdf: Path,
) -> dict[str, object]:
    title = str(manifest_item.get("title") or inspected.title).strip()
    expected_pages = manifest_item.get("expected_pages")
    if expected_pages is not None and int(expected_pages) != inspected.pages:
        raise CatalogError(
            f"page-count mismatch for {source_pdf.name}: "
            f"expected {expected_pages}, found {inspected.pages}"
        )
    source_url = _https_or_empty(
        str(manifest_item.get("source_url", "")), "item source_url"
    )
    return {
        "id": stable_item_id(course_id, title, inspected.sha256),
        "course_id": course_id,
        "title": title,
        "detected_title": inspected.title,
        "title_source": inspected.title_source,
        "kind": "bundle" if manifest_item.get("bundle") else "lecture",
        "order": int(manifest_item.get("order") or 0),
        "pages": inspected.pages,
        "bytes": source_pdf.stat().st_size,
        "sha256": inspected.sha256,
        "pdf": f"pdfs/{source_pdf.name}",
        "thumbnail": f"thumbnails/{inspected.thumbnail.name}",
        "instructor": str(manifest_item.get("instructor", "")),
        "duration_minutes": manifest_item.get("duration_minutes"),
        "source_url": source_url,
        "source_label": str(manifest_item.get("source_label", "")),
        "meta": str(manifest_item.get("meta", "")),
        "legacy_id": str(manifest_item.get("legacy_id", "")),
    }


def inspect_course(
    directory: Path,
    thumbnail_dir: Path,
    pdf_output_dir: Path,
    inspector: Inspector = inspect_pdf,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    manifest = load_course_manifest(directory / "course.json")
    course_id = str(manifest["id"])
    records: list[dict[str, object]] = []
    for raw_item in manifest["items"]:
        if not isinstance(raw_item, dict):
            raise CatalogError(f"course {course_id} contains a non-object item")
        source_pdf = _safe_pdf(directory, raw_item.get("file"))
        inspected = inspector(source_pdf, thumbnail_dir)
        shutil.copy2(source_pdf, pdf_output_dir / source_pdf.name)
        records.append(_item_record(course_id, raw_item, inspected, source_pdf))
    records.sort(
        key=lambda item: (
            item["kind"] == "bundle",
            int(item["order"]),
            str(item["title"]).casefold(),
        )
    )
    course_source = _https_or_empty(
        str(manifest.get("source_url", "")), "course source_url"
    )
    course = {
        "id": course_id,
        "title": str(manifest["title"]),
        "institution": str(manifest["institution"]),
        "term": str(manifest["term"]),
        "description": str(manifest.get("description", "")),
        "tags": [str(tag) for tag in manifest.get("tags", [])],
        "source_url": course_source,
        "featured": bool(manifest.get("featured", False)),
        "item_ids": [str(item["id"]) for item in records],
        "item_count": len(records),
        "page_count": sum(int(item["pages"]) for item in records),
    }
    return course, records


def inspect_inbox(
    directory: Path,
    thumbnail_dir: Path,
    pdf_output_dir: Path,
    inspector: Inspector = inspect_pdf,
) -> tuple[dict[str, object] | None, list[dict[str, object]]]:
    pdfs = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file() and not path.is_symlink() and path.suffix == ".pdf"
        ),
        key=lambda path: path.name.casefold(),
    )
    records: list[dict[str, object]] = []
    for order, source_pdf in enumerate(pdfs, start=1):
        inspected = inspector(source_pdf, thumbnail_dir)
        shutil.copy2(source_pdf, pdf_output_dir / source_pdf.name)
        records.append(
            _item_record(
                "community-contributions",
                {"title": inspected.title, "order": order},
                inspected,
                source_pdf,
            )
        )
    if not records:
        return None, []
    course = {
        "id": "community-contributions",
        "title": "社区贡献",
        "institution": "Community",
        "term": "持续更新",
        "description": "通过审核并合并的社区 PDF 学习资料。",
        "tags": ["community"],
        "source_url": "",
        "featured": False,
        "item_ids": [str(item["id"]) for item in records],
        "item_count": len(records),
        "page_count": sum(int(item["pages"]) for item in records),
    }
    return course, records


def load_papers(path: Path, docs_root: Path | None = None) -> list[dict[str, object]]:
    try:
        papers = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"invalid paper metadata: {path}") from error
    if not isinstance(papers, list):
        raise CatalogError("paper metadata must be a list")
    result: list[dict[str, object]] = []
    for paper in papers:
        if not isinstance(paper, dict) or not all(
            isinstance(paper.get(field), str) and paper[field]
            for field in ("id", "title", "url")
        ):
            raise CatalogError("paper entries require id, title, and url")
        relative = Path(str(paper["url"]))
        if relative.is_absolute() or ".." in relative.parts:
            raise CatalogError("paper URL must remain inside the static site")
        if docs_root is not None and not (docs_root / relative).is_file():
            raise CatalogError(f"paper HTML missing: {relative}")
        result.append({key: paper[key] for key in paper})
    return sorted(result, key=lambda paper: str(paper["title"]).casefold())


def _reject_duplicate_basenames(content_root: Path) -> None:
    names: dict[str, Path] = {}
    for path in sorted(content_root.rglob("*.pdf")):
        key = path.name.casefold()
        if key in names:
            raise CatalogError(
                f"duplicate PDF basename: {names[key].name} and {path.name}"
            )
        names[key] = path


def validate_catalog(catalog: dict[str, object], output_root: Path) -> None:
    courses = catalog["courses"]
    items = catalog["items"]
    assert isinstance(courses, list) and isinstance(items, list)
    course_ids = [str(course["id"]) for course in courses]
    item_ids = [str(item["id"]) for item in items]
    if len(course_ids) != len(set(course_ids)):
        raise CatalogError("duplicate course id")
    if len(item_ids) != len(set(item_ids)):
        raise CatalogError("duplicate item id")
    pdfs = [str(item["pdf"]) for item in items]
    if len([value.casefold() for value in pdfs]) != len(
        set(value.casefold() for value in pdfs)
    ):
        raise CatalogError("duplicate output PDF basename")
    for item in items:
        if not (output_root / str(item["pdf"])).is_file():
            raise CatalogError(f"missing built PDF: {item['pdf']}")
        if not (output_root / str(item["thumbnail"])).is_file():
            raise CatalogError(f"missing built thumbnail: {item['thumbnail']}")
        _https_or_empty(str(item.get("source_url", "")), "item source_url")


def build_catalog(
    content_root: Path,
    output_root: Path,
    generated_at: str,
    docs_root: Path | None = None,
    inspector: Inspector = inspect_pdf,
) -> dict[str, object]:
    content_root = content_root.resolve()
    output_root = output_root.resolve()
    thumbnail_dir = output_root / "thumbnails"
    pdf_output_dir = output_root / "pdfs"
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    pdf_output_dir.mkdir(parents=True, exist_ok=True)
    _reject_duplicate_basenames(content_root)

    courses: list[dict[str, object]] = []
    items: list[dict[str, object]] = []
    for directory in sorted((content_root / "courses").iterdir()):
        if not directory.is_dir():
            continue
        course, course_items = inspect_course(
            directory, thumbnail_dir, pdf_output_dir, inspector
        )
        courses.append(course)
        items.extend(course_items)
    inbox_course, inbox_items = inspect_inbox(
        content_root / "inbox", thumbnail_dir, pdf_output_dir, inspector
    )
    if inbox_course:
        courses.append(inbox_course)
        items.extend(inbox_items)
    courses.sort(
        key=lambda course: (
            not bool(course["featured"]),
            str(course["title"]).casefold(),
        )
    )
    course_rank = {str(course["id"]): index for index, course in enumerate(courses)}
    items.sort(
        key=lambda item: (
            course_rank[str(item["course_id"])],
            item["kind"] == "bundle",
            int(item["order"]),
            str(item["title"]).casefold(),
        )
    )
    papers = load_papers(content_root / "papers.json", docs_root)
    pdf_bytes = sum(int(item["bytes"]) for item in items)
    if pdf_bytes >= REPO_WARNING_BYTES:
        print(
            f"warning: source PDFs total {pdf_bytes} bytes; repository split review required",
            file=sys.stderr,
        )
    catalog: dict[str, object] = {
        "schema_version": 1,
        "generated_at": generated_at,
        "stats": {
            "lecture_count": len(items),
            "paper_count": len(papers),
            "page_count": sum(int(item["pages"]) for item in items),
            "course_count": len(courses),
            "pdf_bytes": pdf_bytes,
        },
        "courses": courses,
        "items": items,
        "papers": papers,
    }
    validate_catalog(catalog, output_root)
    return catalog
