import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.pdf_inspector import (
    PdfInspectionError,
    TextLine,
    choose_title,
    inspect_pdf,
    parse_bbox,
    parse_pdfinfo,
    pdf_structure_bytes,
    stable_item_id,
)
from tests.pdf_factory import write_pdf


class TitleSelectionTests(unittest.TestCase):
    def test_prefers_meaningful_metadata_title(self):
        lines = [TextLine("First Page Heading", 48.0, 72.0, 36.0)]
        result = choose_title(
            "Stanford CS336 Lecture 1", lines, "lecture01.pdf", 792.0
        )
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

    def test_parses_pdfinfo_and_bbox(self):
        self.assertEqual("4", parse_pdfinfo("Pages: 4\nTitle: Test\n")["Pages"])
        lines, height = parse_bbox(
            b'<doc><page height="792"><flow><block><line><word yMin="70" yMax="92">Heading</word></line></block></flow></page></doc>'
        )
        self.assertEqual(792.0, height)
        self.assertEqual("Heading", lines[0].text)
        self.assertEqual(22.0, lines[0].height)

    def test_structure_scan_ignores_streams_comments_and_uri_strings(self):
        data = (
            b"% /JavaScript in a comment\n"
            b"1 0 obj << /S /URI /URI (https://example.com/JavaScript) >> endobj\n"
            b"2 0 obj << /Length 12 >>\nstream\n/JS /Launch\nendstream\nendobj\n"
        )
        structure = pdf_structure_bytes(data)
        self.assertNotIn(b"/JavaScript", structure)
        self.assertNotIn(b"/JS", structure)
        self.assertNotIn(b"/Launch", structure)

    def test_structure_scan_retains_action_tokens(self):
        structure = pdf_structure_bytes(
            b"1 0 obj << /S /JavaScript /JS (app.alert('x')) >> endobj"
        )
        self.assertIn(b"/JavaScript", structure)
        self.assertIn(b"/JS", structure)


TOOLS = ("qpdf", "pdfinfo", "pdftotext", "pdftoppm", "magick")


@unittest.skipUnless(
    all(shutil.which(tool) for tool in TOOLS),
    "PDF toolchain required",
)
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


if __name__ == "__main__":
    unittest.main()
