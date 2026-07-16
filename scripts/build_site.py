from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Callable
from pathlib import Path

from scripts.pdf_inspector import PdfInspection, inspect_pdf
from scripts.site_catalog import Inspector, build_catalog


def _safe_output(root: Path, output: Path) -> None:
    protected = {root, root / "docs", root / "content"}
    if output in protected or output == output.parent:
        raise ValueError(f"refusing unsafe output directory: {output}")


def build_site(
    root: Path,
    output: Path,
    generated_at: str,
    inspector: Inspector = inspect_pdf,
) -> dict[str, object]:
    root = root.resolve()
    output = output.resolve()
    _safe_output(root, output)
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(
        root / "docs",
        output,
        ignore=shutil.ignore_patterns("pdfs", "superpowers", ".DS_Store"),
    )
    catalog = build_catalog(
        root / "content",
        output,
        generated_at,
        docs_root=root / "docs",
        inspector=inspector,
    )
    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--generated-at", required=True)
    args = parser.parse_args(argv)
    catalog = build_site(args.root, args.output, args.generated_at)
    print(json.dumps(catalog["stats"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
