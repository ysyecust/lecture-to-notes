from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


GENERIC_TITLES = {
    "",
    "untitled",
    "document",
    "microsoft word",
    "powerpoint presentation",
}
ACTIVE_MARKER = re.compile(
    rb"/(?:JavaScript|JS|Launch|EmbeddedFiles|OpenAction|AA|RichMedia)\b"
)


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


@dataclass(frozen=True)
class PdfInspection:
    path: Path
    title: str
    title_source: str
    pages: int
    sha256: str
    thumbnail: Path


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def slugify(value: str) -> str:
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
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
        line
        for line in lines
        if line.y_min <= page_height * 0.55
        and 4 <= len(clean_text(line.text)) <= 180
        and not clean_text(line.text).isdigit()
    ]
    if candidates:
        best = max(
            candidates,
            key=lambda line: (
                line.height * 5.0,
                -line.y_min / max(page_height, 1.0),
                len(clean_text(line.text)),
            ),
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


def run_checked(
    args: list[str], timeout: int = 60
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            args,
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr.decode("utf-8", "replace").strip()
        message = f"PDF tool failed: {args[0]}"
        if detail:
            message += f": {detail[:500]}"
        raise PdfInspectionError(message) from error


def parse_pdfinfo(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in output.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


def parse_bbox(xml_bytes: bytes) -> tuple[list[TextLine], float]:
    root = ET.fromstring(xml_bytes)
    page = next(
        (element for element in root.iter() if element.tag.endswith("page")),
        None,
    )
    if page is None:
        return [], 792.0
    page_height = float(page.attrib.get("height", "792"))
    lines: list[TextLine] = []
    for line in (element for element in page.iter() if element.tag.endswith("line")):
        words = [element for element in line if element.tag.endswith("word")]
        text = clean_text(" ".join(element.text or "" for element in words))
        if not text or not words:
            continue
        y_min = min(float(element.attrib.get("yMin", "0")) for element in words)
        y_max = max(float(element.attrib.get("yMax", str(y_min))) for element in words)
        lines.append(TextLine(text, y_min, y_max, max(y_max - y_min, 1.0)))
    return lines, page_height


def reject_active_content(path: Path) -> None:
    with tempfile.TemporaryDirectory() as directory:
        qdf = Path(directory) / "expanded.pdf"
        run_checked(
            ["qpdf", "--qdf", "--object-streams=disable", str(path), str(qdf)]
        )
        found = sorted(
            {
                match.group().decode("ascii")
                for match in ACTIVE_MARKER.finditer(qdf.read_bytes())
            }
        )
        if found:
            raise PdfInspectionError("active PDF content: " + ", ".join(found))


def inspect_pdf(path: Path, thumbnail_dir: Path) -> PdfInspection:
    path = path.resolve()
    if not path.is_file():
        raise PdfInspectionError(f"PDF does not exist: {path}")
    with path.open("rb") as stream:
        signature = stream.read(5)
    if path.stat().st_size < 8 or signature != b"%PDF-":
        raise PdfInspectionError("invalid PDF signature")

    run_checked(["qpdf", "--check", str(path)])
    reject_active_content(path)
    info = parse_pdfinfo(
        run_checked(["pdfinfo", str(path)]).stdout.decode("utf-8", "replace")
    )
    try:
        pages = int(info["Pages"])
    except (KeyError, ValueError) as error:
        raise PdfInspectionError("PDF page count unavailable") from error
    if pages < 1:
        raise PdfInspectionError("PDF must contain at least one page")

    bbox = run_checked(
        [
            "pdftotext",
            "-f",
            "1",
            "-l",
            "1",
            "-bbox-layout",
            str(path),
            "-",
        ]
    ).stdout
    lines, page_height = parse_bbox(bbox)
    choice = choose_title(info.get("Title", ""), lines, path.name, page_height)
    digest = sha256_file(path)

    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    prefix = thumbnail_dir / digest[:16]
    run_checked(
        [
            "pdftoppm",
            "-f",
            "1",
            "-l",
            "1",
            "-singlefile",
            "-scale-to",
            "960",
            "-png",
            str(path),
            str(prefix),
        ]
    )
    png = prefix.with_suffix(".png")
    webp = prefix.with_suffix(".webp")
    run_checked(["magick", str(png), "-strip", "-quality", "82", str(webp)])
    png.unlink(missing_ok=True)
    return PdfInspection(path, choice.title, choice.source, pages, digest, webp)
