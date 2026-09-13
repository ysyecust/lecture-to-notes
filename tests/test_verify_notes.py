import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_notes


TEX = r"""\documentclass{article}
\begin{document}
\section{问题一}
""" + "讲" * 3000 + r"""
\begin{figure}[H]
\centering
\includegraphics[width=\textwidth]{figures/01_arc.jpg}
\caption{电弧炉熔炼示意：主反应与副反应\vtag}
\end{figure}
\srcnote{03:57--04:02}
\begin{figure}[H]
\includegraphics[width=\textwidth]{figures/02_cz.jpg}
\caption{直拉法示意\protect\footnotemark}
\end{figure}
\footnotetext{视频画面时间区间：06:29--06:34。}
\section{问题二}\section{问题三}\section{问题四}\section{问题五}
\end{document}
"""

LOG_CLEAN = "This is XeTeX\nOverfull \\hbox (3.2pt too wide) in paragraph\nOutput written on notes.pdf (5 pages).\n"
LOG_BAD = ("! Undefined control sequence.\nMissing character: There is no 龘 in font\n"
           "LaTeX Warning: Command \\r invalid in math mode on input line 9.\n"
           "Overfull \\hbox (25.0pt too wide) in paragraph\n"
           "LaTeX Warning: Reference `fig:x' on page 3 undefined on input line 12.\n")


def make_workdir(tmp, log=LOG_CLEAN, split_footnote=False, drop_figure=False):
    workdir = Path(tmp)
    (workdir / "figures").mkdir()
    (workdir / "figures/01_arc.jpg").write_bytes(b"x")
    if not drop_figure:
        (workdir / "figures/02_cz.jpg").write_bytes(b"x")
    (workdir / "notes.tex").write_text(TEX, encoding="utf-8")
    (workdir / "notes.log").write_text(log, encoding="utf-8")
    (workdir / "metadata.json").write_text(json.dumps({"duration": 3600}), encoding="utf-8")
    (workdir / "lecture_profile.json").write_text(json.dumps({
        "mode": "conceptual-talk", "audience": "first-time reader",
        "central_question": "Why?", "reader_outcome": "Explain it",
        "visual_teaching_atoms": 0, "formula_teaching_atoms": 0,
    }), encoding="utf-8")
    (workdir / "teaching_atoms.tsv").write_text("atom\tstatus\tevidence\n核心论证\tok\tnotes.tex\n", encoding="utf-8")
    (workdir / "numerical_claims.tsv").write_text("claim\tvalue\tsource_time\tin_notes\n", encoding="utf-8")
    for name in ("figure_manifest.tsv", "figure_verification.txt", "audio.srt"):
        (workdir / name).write_text("x\n", encoding="utf-8")
    page1 = "电弧炉熔炼示意：主反应与副反应 1 视频画面时间区间：03:57–04:02。"
    page2 = "直拉法示意 2" + ("" if split_footnote else " 视频画面时间区间：06:29–06:34。")
    page3 = "视频画面时间区间：06:29–06:34。" if split_footnote else "尾页"
    (workdir / "rendered.txt").write_text("\f".join([page1, page2, page3]), encoding="utf-8")
    return workdir


def run(workdir, *extra):
    out = io.StringIO()
    with redirect_stdout(out):
        code = verify_notes.main(["--workdir", str(workdir), "--pdf-text", str(workdir / "rendered.txt"), *extra])
    return code, out.getvalue()


class VerifyNotesTests(unittest.TestCase):
    def test_clean_workdir_passes_every_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(make_workdir(tmp))
        self.assertEqual(code, 0, out)
        self.assertIn("need_figures>=0", out)
        self.assertIn("need_math>=0", out)
        self.assertIn("OVERALL PASS", out)
        self.assertIn("figure footnotes on the same page as captions", out)

    def test_log_problems_fail_individually(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(make_workdir(tmp, log=LOG_BAD))
        self.assertEqual(code, 1)
        self.assertIn("FAIL compile errors", out)
        self.assertIn("FAIL 1 Missing character", out)
        self.assertIn("FAIL 1 undefined references", out)
        self.assertIn("invalid in math mode", out)
        self.assertIn("overfull boxes exceed 10pt", out)

    def test_footnote_on_another_page_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(make_workdir(tmp, split_footnote=True))
        self.assertEqual(code, 1)
        self.assertIn("SPLIT figures/02_cz.jpg", out)

    def test_missing_figure_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(make_workdir(tmp, drop_figure=True))
        self.assertEqual(code, 1)
        self.assertIn("missing figure files: figures/02_cz.jpg", out)

    def test_missing_profile_fails_density_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = make_workdir(tmp)
            (workdir / "lecture_profile.json").unlink()
            code, out = run(workdir)
        self.assertEqual(code, 1)
        self.assertIn("FAIL lecture_profile.json missing", out)

    def test_pdf_check_can_be_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = make_workdir(tmp)
            out = io.StringIO()
            with redirect_stdout(out):
                code = verify_notes.main(["--workdir", str(workdir), "--skip-pdf"])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("SKIP figure/footnote same-page check", out.getvalue())


try:
    from PIL import Image
except ImportError:  # pragma: no cover - environment dependent
    Image = None

COMPOSITE = {"width": 1280, "height": 410, "composite": True,
             "panels": [{"name": "main", "box": [546, 0, 1280, 410]}, {"name": "left", "box": [0, 0, 546, 410]}]}


@unittest.skipIf(Image is None, "layout gate tests write images with Pillow")
class LayoutGateTests(unittest.TestCase):
    def workdir(self, tmp, figures, layout=None):
        """`figures` holds (file name, (width, height), panel) for each image and manifest row."""
        workdir = make_workdir(tmp)
        rows = ["figure\tframe\tstart\tend\ttopic\tpanel"]
        for name, size, panel in figures:
            Image.new("RGB", size, (250, 250, 250)).save(workdir / "figures" / name)
            rows.append(f"figures/{name}\tf_0191.png\t00:47:30\t00:47:45\t注意力\t{panel}")
        (workdir / "figure_manifest.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
        if layout is not None:
            (workdir / "layout.json").write_text(json.dumps(layout), encoding="utf-8")
        return workdir

    def test_uncropped_composite_figure_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(self.workdir(tmp, [("wide.jpg", (1280, 410), "main")], COMPOSITE))
        self.assertEqual(code, 1, out)
        self.assertIn("does not match panel main", out)

    def test_panel_crops_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            figures = [("slide.jpg", (731, 410), "main"), ("board.png", (543, 410), "left")]
            code, out = run(self.workdir(tmp, figures, COMPOSITE))
        self.assertEqual(code, 0, out)
        self.assertIn("PASS 2 manifest figures fit the frame layout", out)

    def test_composite_figure_must_name_a_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(self.workdir(tmp, [("slide.jpg", (731, 410), "")], COMPOSITE))
        self.assertEqual(code, 1, out)
        self.assertIn("`panel` must name one of main, left or full", out)

    def test_full_frame_on_purpose_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(self.workdir(tmp, [("wide.jpg", (1280, 410), "full")], COMPOSITE))
        self.assertEqual(code, 0, out)
        self.assertIn("FULL figures/wide.jpg", out)

    def test_wide_figure_without_layout_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(self.workdir(tmp, [("wide.jpg", (1280, 410), "")]))
        self.assertEqual(code, 1, out)
        self.assertIn("wider than 2:1", out)

    def test_single_picture_figure_without_layout_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out = run(self.workdir(tmp, [("slide.jpg", (1920, 1080), "")]))
        self.assertEqual(code, 0, out)

    def test_image_size_reads_png_and_jpeg_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Image.new("RGB", (321, 123), (10, 20, 30))
            image.save(Path(tmp) / "a.png")
            image.save(Path(tmp) / "b.jpg", quality=90)
            image.save(Path(tmp) / "c.jpg", progressive=True)
            for name in ("a.png", "b.jpg", "c.jpg"):
                self.assertEqual(verify_notes.image_size(Path(tmp) / name), (321, 123), name)
            junk = Path(tmp) / "junk.jpg"
            junk.write_bytes(b"x")
            self.assertIsNone(verify_notes.image_size(junk))


class FigureBlockParsingTests(unittest.TestCase):
    def test_both_footnote_macros_are_recognised(self):
        blocks = verify_notes.figure_blocks(TEX)
        self.assertEqual([b["file"] for b in blocks], ["figures/01_arc.jpg", "figures/02_cz.jpg"])
        self.assertEqual(blocks[0]["time"], "03:57--04:02")
        self.assertEqual(blocks[1]["time"], "06:29--06:34")
        self.assertEqual(blocks[0]["key"], "电弧炉熔炼示意主")

    def test_log_parser_counts(self):
        stats = verify_notes.parse_log(LOG_BAD, overfull_pt=10)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertEqual(stats["math_invalid"], 1)
        self.assertEqual(stats["overfull_bad"], 1)
        self.assertEqual(stats["undefined"], 1)


if __name__ == "__main__":
    unittest.main()
