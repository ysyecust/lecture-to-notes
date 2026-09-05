#!/usr/bin/env python3
"""
Post-compile gate for lecture notes: density, compile log, figures, and provenance.

One call replaces the ad-hoc regex checks an agent otherwise improvises after
`xelatex`. Every check prints one `PASS`/`FAIL`/`SKIP` line; the final line is
`OVERALL PASS` or `OVERALL FAIL` and the exit code follows it.

Checks:
  density     lecture_profile.json + metadata.json duration → CJK, figure, section,
              box, and display-math floors; teaching_atoms.tsv and numerical_claims.tsv
  artifacts   figure_manifest.tsv, figure_verification.txt, audio.srt non-empty
  log         `!` errors, Missing character, undefined references, `invalid in math
              mode`, Overfull \\hbox above --overfull-pt
  figures     every \\includegraphics file exists
  provenance  every figure's time footnote (\\footnotetext{视频画面时间区间：…} or
              \\srcnote{…}) lands on the same PDF page as its caption

Usage:
    python3 verify_notes.py [--workdir .] [--tex notes.tex] [--log notes.log]
        [--pdf notes.pdf | --pdf-text rendered.txt] [--overfull-pt 10] [--skip-pdf]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

CJK = re.compile(r"[一-鿿]")
MODES = {"technical-slide", "conceptual-talk", "mixed"}
PROFILE_FIELDS = ("audience", "central_question", "reader_outcome", "visual_teaching_atoms", "formula_teaching_atoms")


class Report:
    def __init__(self):
        self.ok = True
        self.lines: list[str] = []

    def emit(self, status: str, message: str):
        if status == "FAIL":
            self.ok = False
        line = f"{status} {message}"
        self.lines.append(line)
        print(line)


# ---------------------------------------------------------------- density
def density_gate(workdir: Path, report: Report) -> None:
    tex_path = workdir / "notes.tex"
    if not tex_path.exists():
        report.emit("FAIL", "notes.tex missing")
        return
    tex = tex_path.read_text(encoding="utf-8")
    cn = len(CJK.findall(tex))
    figures_dir = workdir / "figures"
    figs = len([p for p in figures_dir.glob("*") if p.is_file()]) if figures_dir.exists() else 0
    secs = len(re.findall(r"\\section\{", tex))
    boxes = len(re.findall(r"\\begin\{(important|knowledge|warning|practice)box\}", tex))
    maths = len(re.findall(r"\\\[|\\begin\{equation", tex))
    codes = len(re.findall(r"\\begin\{lstlisting\}", tex))
    tables = len(re.findall(r"\\begin\{tabular", tex))
    print(f"CJK_chars={cn} figures={figs} sections={secs} boxes={boxes} display_math={maths} code={codes} tables={tables}")

    meta_path = workdir / "metadata.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    duration = float(meta.get("duration") or 0) / 60.0

    profile_path = workdir / "lecture_profile.json"
    if not profile_path.exists():
        report.emit("FAIL", "lecture_profile.json missing")
        return
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    mode = profile.get("mode")
    if mode not in MODES:
        report.emit("FAIL", f"invalid lecture mode: {mode!r}")
        return
    for key in PROFILE_FIELDS:
        if key not in profile:
            report.emit("FAIL", f"lecture_profile.json missing field: {key}")
            return
    visual_atoms = int(profile["visual_teaching_atoms"])
    formula_atoms = int(profile["formula_teaching_atoms"])
    if visual_atoms < 0 or formula_atoms < 0:
        report.emit("FAIL", "teaching atom counts must be non-negative")
        return
    if mode == "technical-slide":
        need_cn = max(5000, round(70 * duration)) if duration else 5000
        need_sec = 8 if duration >= 60 else 1
        need_box = 12 if duration >= 60 else 6
    elif mode == "mixed":
        need_cn = max(3500, round(55 * duration)) if duration else 3500
        need_sec = 6 if duration >= 60 else 1
        need_box = 0
    else:
        need_cn = max(2500, round(45 * duration)) if duration else 2500
        need_sec = 5 if duration >= 60 else 1
        need_box = 0
    figure_target = max(20, round(duration / 3.5)) if duration else 20
    need_fig = min(visual_atoms, figure_target)
    math_target = max(10, round(duration / 4)) if duration else 10
    need_math = min(formula_atoms, math_target)
    print(f"mode={mode} duration_min={duration:.1f} need_CJK>={need_cn} need_figures>={need_fig} "
          f"need_sections>={need_sec} need_boxes>={need_box} need_math>={need_math}")
    ok = cn >= need_cn and figs >= need_fig and secs >= need_sec and boxes >= need_box and maths >= need_math
    report.emit("PASS" if ok else "FAIL",
                "density gates" if ok else "density — fill source-backed teaching gaps; never pad prose, formulas, boxes, or figures")

    atoms = workdir / "teaching_atoms.tsv"
    if atoms.exists():
        rows = [r for r in atoms.read_text(encoding="utf-8").splitlines()[1:] if r.strip()]
        missing = [r for r in rows if len(r.split("\t")) < 2 or r.split("\t")[1] != "ok"]
        print(f"teaching_atoms total={len(rows)} missing={len(missing)}")
        report.emit("PASS" if not missing else "FAIL", "teaching atoms" if not missing else "teaching atom gaps remain")
    else:
        report.emit("FAIL", "teaching_atoms.tsv missing")

    claims = workdir / "numerical_claims.tsv"
    if claims.exists():
        rows = [r for r in claims.read_text(encoding="utf-8").splitlines()[1:] if r.strip()]
        miss = [r for r in rows if "yes" not in r.split("\t")[-1].lower()]
        print(f"numerical_claims total={len(rows)} missing_in_notes={len(miss)}")
        if miss:
            report.emit("FAIL", "numerical claims not discharged:")
            for r in miss[:12]:
                print("  ", r)
        else:
            report.emit("PASS", "numerical claims")
    else:
        report.emit("FAIL", "numerical_claims.tsv missing")


# ---------------------------------------------------------------- artifacts
def artifact_gate(workdir: Path, report: Report) -> None:
    for name in ("figure_manifest.tsv", "figure_verification.txt", "audio.srt"):
        path = workdir / name
        if path.exists() and path.stat().st_size > 0:
            report.emit("PASS", f"{name} present")
        else:
            report.emit("FAIL", f"{name} missing or empty")


# ---------------------------------------------------------------- compile log
def parse_log(text: str, overfull_pt: float) -> dict:
    errors = [line for line in text.splitlines() if line.startswith("! ")]
    missing_chars = len(re.findall(r"Missing character", text))
    undefined = len(re.findall(r"(?:Reference|Citation) `[^']*' on page \d+ undefined|There were undefined references", text))
    math_invalid = len(re.findall(r"invalid in math mode", text))
    overfull = [float(m) for m in re.findall(r"Overfull \\hbox \(([0-9.]+)pt", text)]
    worst = max(overfull) if overfull else 0.0
    bad_overfull = [o for o in overfull if o > overfull_pt]
    return {"errors": errors, "missing_chars": missing_chars, "undefined": undefined,
            "math_invalid": math_invalid, "overfull": len(overfull), "overfull_bad": len(bad_overfull), "overfull_worst": worst}


def log_gate(log_path: Path, overfull_pt: float, report: Report) -> None:
    if not log_path.exists():
        report.emit("FAIL", f"{log_path.name} missing (compile first)")
        return
    stats = parse_log(log_path.read_text(encoding="utf-8", errors="replace"), overfull_pt)
    print(f"log errors={len(stats['errors'])} missing_chars={stats['missing_chars']} undefined={stats['undefined']} "
          f"math_invalid={stats['math_invalid']} overfull={stats['overfull']} (worst {stats['overfull_worst']:.1f}pt, "
          f">{overfull_pt:g}pt: {stats['overfull_bad']})")
    report.emit("PASS" if not stats["errors"] else "FAIL", "no compile errors" if not stats["errors"] else f"compile errors: {stats['errors'][0]}")
    report.emit("PASS" if not stats["missing_chars"] else "FAIL", "no missing glyphs" if not stats["missing_chars"] else f"{stats['missing_chars']} Missing character warnings")
    report.emit("PASS" if not stats["undefined"] else "FAIL", "no undefined references" if not stats["undefined"] else f"{stats['undefined']} undefined references")
    report.emit("PASS" if not stats["math_invalid"] else "FAIL", "no invalid math-mode commands" if not stats["math_invalid"] else f"{stats['math_invalid']} 'invalid in math mode' warnings (use \\angstrom/\\text{{}} macros)")
    report.emit("PASS" if not stats["overfull_bad"] else "FAIL", f"overfull boxes within {overfull_pt:g}pt" if not stats["overfull_bad"] else f"{stats['overfull_bad']} overfull boxes exceed {overfull_pt:g}pt")


# ---------------------------------------------------------------- figures + provenance
FIGURE_RE = re.compile(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]*)\}")
CAPTION_RE = re.compile(r"\\caption\{(.*?)(?:\\vtag|\\protect\\footnotemark|\})", re.S)
TIME_RE = re.compile(r"(?:\\srcnote\{|\\footnotetext\{视频画面时间区间：)\s*([0-9:]+(?:\s*[–—-]+\s*[0-9:]+)?(?:\s*[与和、,]\s*[0-9:]+\s*[–—-]+\s*[0-9:]+)*)")


def strip_macros(text: str) -> str:
    text = re.sub(r"\\[A-Za-z]+\*?(?:\[[^\]]*\])?", " ", text)
    return re.sub(r"[{}$\\]", "", text)


def caption_key(caption: str, length: int = 8) -> str:
    return "".join(CJK.findall(strip_macros(caption)))[:length]


def figure_blocks(tex: str) -> list[dict]:
    """Return one record per \\includegraphics with its caption key and time footnote."""
    blocks = []
    for match in FIGURE_RE.finditer(tex):
        window = tex[match.end(): match.end() + 1200]
        cap = CAPTION_RE.search(window)
        time = TIME_RE.search(window)
        blocks.append({
            "file": match.group(1),
            "caption": cap.group(1).strip() if cap else "",
            "key": caption_key(cap.group(1)) if cap else "",
            "time": re.sub(r"\s+", "", time.group(1)) if time else "",
            "line": tex.count("\n", 0, match.start()) + 1,
        })
    return blocks


def normalize_page(text: str) -> str:
    return re.sub(r"\s+", "", text).replace("–", "--").replace("—", "--").replace("−", "-")


def pdf_pages(pdf: Path | None, pdf_text: Path | None) -> list[str] | None:
    if pdf_text is not None:
        raw = pdf_text.read_text(encoding="utf-8", errors="replace")
    elif pdf is not None and pdf.exists() and shutil.which("pdftotext"):
        raw = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=False).stdout
    else:
        return None
    return [normalize_page(p) for p in raw.split("\f")]


def figure_gate(workdir: Path, tex: str, pages: list[str] | None, report: Report) -> None:
    blocks = figure_blocks(tex)
    missing = [b for b in blocks if not b["file"].startswith("\\") and not (workdir / b["file"]).exists()]
    print(f"figures referenced={len(blocks)} missing_files={len(missing)}")
    report.emit("PASS" if not missing else "FAIL",
                "all figure files exist" if not missing else "missing figure files: " + ", ".join(b["file"] for b in missing[:8]))

    provenance = [b for b in blocks if not b["file"].startswith("\\")]
    no_time = [b for b in provenance if not b["time"]]
    if no_time:
        report.emit("FAIL", f"{len(no_time)} figures without a time footnote (first at line {no_time[0]['line']}: {no_time[0]['file']})")
    else:
        report.emit("PASS", "every video-frame figure has a time footnote")
    if pages is None:
        report.emit("SKIP", "figure/footnote same-page check (no PDF text; pass --pdf or --pdf-text)")
        return
    split = 0
    for b in provenance:
        if not b["time"] or not b["key"]:
            continue
        time_key = normalize_page(b["time"])
        cap_pages = {i for i, p in enumerate(pages) if b["key"] in p}
        time_pages = {i for i, p in enumerate(pages) if time_key in p}
        if cap_pages and time_pages and not (cap_pages & time_pages):
            split += 1
            print(f"  SPLIT {b['file']}: caption on page {sorted(cap_pages)[0] + 1}, footnote on page {sorted(time_pages)[0] + 1}")
        elif not time_pages:
            split += 1
            print(f"  NOFOOT {b['file']}: footnote '{b['time']}' not found in rendered text")
    report.emit("PASS" if split == 0 else "FAIL", "figure footnotes on the same page as captions" if split == 0 else f"{split} figures whose footnote is not on the caption page")


# ---------------------------------------------------------------- main
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--tex", default="notes.tex")
    parser.add_argument("--log", default="notes.log")
    parser.add_argument("--pdf", default="notes.pdf")
    parser.add_argument("--pdf-text", default=None, help="pdftotext output (pages separated by form feeds)")
    parser.add_argument("--overfull-pt", type=float, default=10.0)
    parser.add_argument("--skip-pdf", action="store_true")
    parser.add_argument("--skip-log", action="store_true")
    args = parser.parse_args(argv)

    workdir = Path(args.workdir).resolve()
    report = Report()
    density_gate(workdir, report)
    artifact_gate(workdir, report)
    tex_path = workdir / args.tex
    if not args.skip_log:
        log_gate(workdir / args.log, args.overfull_pt, report)
    if tex_path.exists():
        tex = tex_path.read_text(encoding="utf-8")
        pages = None if args.skip_pdf else pdf_pages(workdir / args.pdf, Path(args.pdf_text) if args.pdf_text else None)
        figure_gate(workdir, tex, pages, report)
    print("OVERALL", "PASS" if report.ok else "FAIL")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
