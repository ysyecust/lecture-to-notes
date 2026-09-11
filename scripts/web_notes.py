"""Trusted TeX -> checked web documents. TeX is parsed, never executed.

Pandoc supplies the general AST. This module adapts the repository's declared
callouts and paired figure notes, then rejects unsupported raw TeX or lost
components. Failure leaves the catalog's PDF-only entry intact.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

VERSION = "1"
BOXES = ("knowledgebox", "importantbox", "warningbox", "practicebox", "boundarybox")
TIME = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")
LAYOUT = re.compile(r"^(?:\\(?:centering|small|footnotesize|large|Large|huge|Huge|normalsize|noindent|hfill|vfill|newpage|clearpage|tableofcontents|par)\s*)+$")
FORBIDDEN = re.compile(r"\\(?:input|include|openin|openout|read|write|immediate|catcode|csname|endcsname|directlua|special)(?![A-Za-z])")


class ConversionError(ValueError):
    pass


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ConversionError("source/resource path must be relative")
    root = root.resolve()
    if ".." in Path(name).parts:
        raise ConversionError("source/resource path is unsafe")
    candidate = root
    for part in Path(name).parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ConversionError("source/resource path is unsafe")
    path = candidate.resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ConversionError(f"missing source/resource: {name}")
    return path


def group(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        raise ConversionError("expected braced macro argument")
    depth, i = 1, start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "{": depth += 1
        if text[i] == "}": depth -= 1
        if depth == 0: return text[start + 1:i], i + 1
        i += 1
    raise ConversionError("unbalanced macro argument")


def without_comments(text: str) -> str:
    return re.sub(r"(?<!\\)%[^\n]*", "", text)


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from walk(child)
    elif isinstance(value, list):
        for child in value: yield from walk(child)


def prepare_tex(source: str):
    clean = without_comments(source)
    if FORBIDDEN.search(clean):
        raise ConversionError("file access or executable TeX command is unsupported")
    if "LTNWEB" in clean:
        raise ConversionError("reserved conversion marker in source")
    try:
        preamble, body = clean.split(r"\begin{document}", 1)
        body, _ = body.split(r"\end{document}", 1)
    except ValueError as exc:
        raise ConversionError("complete TeX document required") from exc
    # Cover and print-only TOC remain available in the original PDF. Never discard
    # ordinary article content in order to make a conversion pass.
    body = re.sub(r"\\begin\{titlepage\}.*?\\end\{titlepage\}", "", body, flags=re.S)
    notes, boxes = {}, {}
    srcnote_template = None
    definition = re.search(r"\\newcommand\{\\srcnote\}\[1\]", preamble)
    if definition:
        macro, _ = group(preamble, definition.end())
        inner = re.match(r"\\footnotetext", macro.strip())
        if inner:
            srcnote_template, tail = group(macro.strip(), inner.end())
            if macro.strip()[tail:].strip(): srcnote_template = None

    pattern = re.compile(r"\\(footnotetext|srcnote)\b|\\begin\{(" + "|".join(BOXES) + r")\}")
    output, end = [], 0
    for match in pattern.finditer(body):
        if match.start() < end: continue
        output.append(body[end:match.start()])
        argument, end = group(body, match.end())
        if match.group(1):
            if len(TIME.findall(argument)) != 2:
                raise ConversionError("figure source note must contain a time interval")
            key = f"LTNWEBNOTE{len(notes):04d}"
            if match.group(1) == "srcnote":
                if srcnote_template is None:
                    raise ConversionError("srcnote requires a supported, explicit footnote definition")
                notes[key] = srcnote_template.replace("#1", argument)
            else:
                notes[key] = argument
            output.append("\n\n" + key + "\n\n")
        else:
            key = f"LTNWEBBOX{len(boxes):04d}"
            boxes[key] = match.group(2)
            output.append("\\begin{quote}\n\n" + key + "\n\n\\textbf{" + argument + "}\n\n")
    output.append(body[end:])
    prepared = "".join(output)
    for name in BOXES:
        prepared = prepared.replace("\\end{" + name + "}", r"\end{quote}")
    marks = len(re.findall(r"\\(?:vtag|footnotemark)\b", body))
    if marks != len(notes):
        raise ConversionError("unpaired figure footnote markers")
    prepared = re.sub(r"\\(?:protect\s*)?\\footnotemark\b|\\vtag\b", "", prepared)
    return preamble + r"\begin{document}" + prepared + r"\end{document}", body, notes, boxes


def pandoc(args: list[str], text: str) -> str:
    # The TeX reader stays sandboxed. The HTML writer consumes the checked AST
    # (no filters or executable raw nodes) and needs its installed translations;
    # distro Pandoc packages do not embed these data files in sandbox mode.
    with tempfile.TemporaryDirectory() as tmp:
        try:
            sandbox = [] if args[args.index("-f") + 1] == "json" else ["--sandbox"]
            run = subprocess.run(["pandoc", *sandbox, *args], input=text,
                text=True, capture_output=True, check=True, timeout=90, cwd=tmp)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ConversionError("Pandoc conversion failed or unavailable") from exc
    if run.stderr.strip():
        raise ConversionError("Pandoc reported: " + run.stderr.strip()[:600])
    return run.stdout


def convert(source: Path, source_root: Path, output: Path, spec: dict, item: dict, *, review: bool = False) -> dict:
    from bs4 import BeautifulSoup
    prepared, body, notes, boxes = prepare_tex(source.read_text())
    ast = json.loads(pandoc(["-f", "latex+raw_tex", "-t", "json"], prepared))
    unknown = []
    for node in walk(ast):
        if node.get("t") in ("RawBlock", "RawInline"):
            fmt, value = node["c"]
            if fmt != "latex" or not LAYOUT.fullmatch(value.strip()): unknown.append(value[:120])
            else: node["c"] = ["html", ""]
    if unknown:
        raise ConversionError("unsupported raw TeX: " + repr(unknown[:8]))
    rendered = pandoc(["-f", "json", "-t", "html5", "--mathml", "--wrap=none"], json.dumps(ast))
    doc = BeautifulSoup(rendered, "html.parser")
    components, resources = [], []
    for key, kind in boxes.items():
        marker = doc.find(string=lambda s: s and s.strip() == key)
        if not marker or not marker.find_parent("blockquote"):
            raise ConversionError("lost callout marker")
        box = marker.find_parent("blockquote"); marker.parent.decompose()
        box.name = "aside"; box["class"] = ["note-callout", kind]
        title = box.find("p", recursive=False)
        if not title: raise ConversionError("callout title missing")
        title.name = "h3"
        components.append({"kind": "callout", "variant": kind, "title": title.get_text()})
    for key, note in notes.items():
        marker = doc.find(string=lambda s: s and s.strip() == key)
        if not marker: raise ConversionError("lost video time marker")
        figure = marker.find_previous("figure")
        if not figure or figure.select_one(".figure-source"):
            raise ConversionError("ambiguous figure/source pairing")
        caption = doc.new_tag("p", attrs={"class": "figure-source"})
        caption.string = note; figure.append(caption); marker.parent.decompose()
    figures = doc.find_all("figure")
    for index, figure in enumerate(figures, 1):
        figure["id"] = f"figure-{index}"
        caption = figure.find("figcaption")
        if not caption or not figure.img: raise ConversionError("incomplete figure")
        times = TIME.findall(figure.get_text(" "))
        if len(times) != 2: raise ConversionError("figure must retain one source interval")
        figure["data-start"] = times[0]; figure["data-end"] = times[1]
        components.append({"kind": "figure", "id": figure["id"], "caption": caption.get_text(), "start": times[0], "end": times[1]})
        url = item.get("source_url", "")
        if url.startswith("https://www.bilibili.com/video/"):
            h, m, s = map(int, times[0].split(":")); link = doc.new_tag("a", href=url + ("&" if "?" in url else "?") + f"t={h*3600+m*60+s}")
            link["class"] = ["video-link"]; link.string = "回看这段讲解 ↗"; figure.append(link)
    for image in doc.find_all("img"):
        name = re.sub(r"^\\detokenize\{(.*)\}$", r"\1", image.get("src", ""))
        asset = safe_file(source_root, name)
        hashed = digest(asset); target = "media/" + hashed[:16] + asset.suffix.lower()
        if asset.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise ConversionError("unsupported image format")
        dest = output / target; dest.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(asset, dest)
        size = subprocess.check_output(["identify", "-ping", "-format", "%w %h", str(asset)], text=True, timeout=15).split()
        image["width"], image["height"] = size[0], size[1]
        image["src"] = target; image["loading"] = "lazy"; image.attrs.pop("style", None)
        image["alt"] = image.find_parent("figure").figcaption.get_text() if image.find_parent("figure") else "讲义插图"
        resources.append({"path": name, "sha256": hashed, "output": target})
    if not review and {r["path"]: r["sha256"] for r in resources} != spec.get("resources"):
        raise ConversionError("image hashes differ from reviewed profile")
    # Reject unresolved references and active HTML rather than trying to repair it.
    for tag in doc.find_all(True):
        if tag.name in ("script", "iframe", "object", "embed", "style", "form", "input"):
            raise ConversionError("active HTML in converted document")
        for key in tag.attrs:
            if key.lower().startswith("on") or key.lower() == "style":
                if key.lower() == "style": continue  # Pandoc table widths only; removed below.
                raise ConversionError("event handler in converted document")
        tag.attrs.pop("style", None)
        if tag.name == "a":
            href = tag.get("href", "")
            if href.startswith("#"):
                if not doc.find(id=href[1:]): raise ConversionError("unresolved internal reference")
            elif urlparse(href).scheme not in ("https", "mailto"):
                raise ConversionError("unsafe or relative external link")
        if tag.name in ("math", "annotation") and "merror" in str(tag):
            raise ConversionError("invalid mathematical expression")
    chapters = doc.find_all("h1")
    sections = []
    for i, heading in enumerate(chapters, 1):
        old = heading.get("id")
        heading["id"] = f"chapter-{i}"
        if old:
            for link in doc.find_all("a", href="#" + old): link["href"] = "#" + heading["id"]
        heading.name = "h2"; heading["data-chapter"] = str(i)
        sections.append({"id": heading["id"], "title": heading.get_text()})
    for heading in doc.find_all("h2"):
        if not heading.has_attr("data-chapter"): heading.name = "h3"
    counts = {"chapters": len(chapters), "figures": len(figures), "images": len(resources),
        "callouts": len(boxes), "tables": len(doc.find_all("table")),
        "math": len(doc.find_all("math")), "time_tokens": len(TIME.findall(doc.get_text(" ")))}
    expected = spec.get("expected")
    if not review and counts != expected:
        raise ConversionError(f"component count mismatch: expected {expected}, found {counts}")
    # Full source-time and numeric-math preservation, not merely an exit-status check.
    source_times = TIME.findall(body)
    html_times = TIME.findall(doc.get_text(" "))
    if sorted(source_times) != sorted(html_times): raise ConversionError("source time intervals changed")
    if "LTNWEB" in doc.get_text(): raise ConversionError("unresolved conversion marker")
    math = [n["c"] for n in walk(ast) if n.get("t") == "Math"]
    for value in math: components.append({"kind": "math", "display": value[0]["t"], "tex": value[1]})
    components.extend({"kind": "table", "text": t.get_text(" ", strip=True)} for t in doc.find_all("table"))
    components.extend({"kind": "code", "text": t.get_text()} for t in doc.find_all("pre"))
    # Verify that AST text/code and the original math annotations survive rendering.
    text = re.sub(r"\s+", "", doc.get_text(" "))
    missing_text = []
    for node in walk(ast):
        token = node.get("c") if node.get("t") == "Str" else node.get("c", [None, ""])[1] if node.get("t") in ("Code", "CodeBlock") else ""
        if isinstance(token, str) and token and not token.startswith("LTNWEB"):
            if re.sub(r"\s+", "", token) not in text: missing_text.append(token[:50])
    if missing_text: raise ConversionError("rendered text lost AST content: " + repr(missing_text[:4]))
    annotations = [n.get_text() for n in doc.select('math annotation[encoding="application/x-tex"]')]
    if annotations != [m[1] for m in math]: raise ConversionError("math source annotations changed")
    article = doc.new_tag("article", attrs={"class": "web-document"})
    for child in list(doc.contents): article.append(child.extract())
    blocks = []
    for index, block in enumerate(article.find_all(recursive=False)):
        if not block.get("id"): block["id"] = f"block-{index + 1}"
        block["data-reading-block"] = "true"
        blocks.append({"id": block["id"], "kind": block.name})
    html = str(article)
    output.mkdir(parents=True, exist_ok=True)
    (output / "article.html").write_text(html)
    report = {"status": "needs_review" if review else "passed", "converter": "pandoc-project-profile", "version": VERSION,
        "pandoc": subprocess.check_output(["pandoc", "--version"], text=True).splitlines()[0],
        "source_sha256": digest(source), "pdf_sha256": item["sha256"],
        "html_sha256": hashlib.sha256(html.encode()).hexdigest(), "counts": counts, "resources": resources}
    model = {"schema_version": 1, "item_id": item["id"], "title": item["title"], "sections": sections,
        "components": components, "blocks": blocks, "provenance": report, "ast": ast}
    (output / "document.json").write_text(json.dumps(model, ensure_ascii=False))
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def build_web_notes(root: Path, output: Path, catalog: dict) -> dict:
    results = {}
    by_pdf = {item["pdf"].split("/")[-1]: item for item in catalog["items"]}
    for manifest in sorted((root / "content/courses").glob("*/course.json")):
        course = json.loads(manifest.read_text())
        for entry in course["items"]:
            if not entry.get("web_source"): continue
            item = by_pdf[entry["file"]]; spec = entry["web_source"]
            destination = output / "notes" / item["id"]
            item.pop("web", None)
            try:
                source = safe_file(manifest.parent, spec["tex"])
                if digest(source) != spec["sha256"] or item["sha256"] != spec["pdf_sha256"]:
                    raise ConversionError("source/PDF hash differs from reviewed profile")
                report = convert(source, source.parent, destination, spec, item)
                item["web"] = {"article": f"notes/{item['id']}/article.html", "document": f"notes/{item['id']}/document.json", "report": f"notes/{item['id']}/report.json", "sha256": report["html_sha256"]}
                results[item["id"]] = report
            except (ConversionError, KeyError, OSError, ValueError) as exc:
                shutil.rmtree(destination, ignore_errors=True)
                results[item["id"]] = {"status": "blocked", "reason": str(exc), "fallback": "pdf"}
    (output / "data").mkdir(exist_ok=True)
    (output / "data/web-notes-report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Prepare a source profile for human review; never edits the course manifest")
    parser.add_argument("--course", type=Path, required=True)
    parser.add_argument("--file", required=True, help="PDF filename in the course manifest")
    parser.add_argument("--tex", required=True, help="TeX path relative to the course directory")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.course.resolve():
        parser.error("review output must not overwrite the course manifest")
    course = json.loads(args.course.read_text())
    entry = next(e for e in course["items"] if e["file"] == args.file)
    source = safe_file(args.course.parent, args.tex)
    pdf = safe_file(args.course.parent, args.file)
    with tempfile.TemporaryDirectory() as tmp:
        report = convert(source, source.parent, Path(tmp), {}, {"id": "review", "title": entry["title"], "source_url": entry.get("source_url", ""), "sha256": digest(pdf)}, review=True)
    result = {"status": "needs_review", "web_source": {"tex": args.tex, "sha256": digest(source), "pdf_sha256": digest(pdf), "expected": report["counts"], "resources": {r["path"]: r["sha256"] for r in report["resources"]}}, "converter": report["pandoc"]}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("Profile candidate written for review; course manifest unchanged.")


if __name__ == "__main__":
    main()
