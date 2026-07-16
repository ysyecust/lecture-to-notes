from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.pdf_inspector import (
    PdfInspectionError,
    inspect_pdf,
    sha256_file,
    stable_item_id,
)


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
    if not root.is_dir():
        raise ContributionError(f"tree does not exist: {root}")
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if ".git" in path.relative_to(root).parts:
            continue
        if path.is_symlink():
            raise ContributionError(f"symlinks are not accepted: {path.relative_to(root)}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            result[relative] = sha256_file(path)
    return result


def validate_delta(base: Path, submission: Path, body: str) -> Delta:
    if RIGHTS_MARKER not in body:
        raise ContributionError("rights declaration must be checked")
    before = tree_map(base)
    after = tree_map(submission)
    changed = {
        path
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    }
    added = sorted(path for path in changed if path not in before)
    allowed = [
        path
        for path in added
        if Path(path).parent.as_posix() == "content/inbox"
        and Path(path).suffix == ".pdf"
    ]
    if set(changed) != set(allowed):
        raise ContributionError(
            "contribution PRs may only add PDFs directly under content/inbox/"
        )
    if not allowed or len(allowed) > MAX_FILES:
        raise ContributionError(f"PDF count must be between 1 and {MAX_FILES}")

    sizes = [(submission / path).stat().st_size for path in allowed]
    if any(size > MAX_FILE_BYTES for size in sizes):
        raise ContributionError("each PDF must be 25 MiB or smaller")
    if sum(sizes) > MAX_TOTAL_BYTES:
        raise ContributionError("PDF contribution total must be 100 MiB or smaller")

    existing_names = {
        Path(path).name.casefold()
        for path in before
        if Path(path).suffix.casefold() == ".pdf"
    }
    new_names = [Path(path).name.casefold() for path in allowed]
    if len(new_names) != len(set(new_names)) or existing_names.intersection(new_names):
        raise ContributionError("PDF basename conflicts with repository content")
    return Delta(allowed)


def build_report(
    submission: Path,
    delta: Delta,
    thumbnail_dir: Path,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    for relative in delta.added_pdfs:
        inspected = inspect_pdf(submission / relative, thumbnail_dir)
        records.append(
            {
                "path": relative,
                "title": inspected.title,
                "title_source": inspected.title_source,
                "pages": inspected.pages,
                "sha256": inspected.sha256,
                "id": stable_item_id(
                    "community", inspected.title, inspected.sha256
                ),
                "thumbnail": inspected.thumbnail.name,
                "bytes": (submission / relative).stat().st_size,
            }
        )
    return {"schema_version": 1, "items": records}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--submission", type=Path, required=True)
    parser.add_argument("--event", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--thumbnails", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        event = json.loads(args.event.read_text(encoding="utf-8"))
        body = event["pull_request"].get("body") or ""
        delta = validate_delta(args.base, args.submission, body)
        report = build_report(args.submission, delta, args.thumbnails)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (
        ContributionError,
        PdfInspectionError,
        KeyError,
        json.JSONDecodeError,
        OSError,
    ) as error:
        print(f"contribution rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
