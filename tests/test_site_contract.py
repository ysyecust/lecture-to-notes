import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SiteContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        cls.reader = (ROOT / "docs/reader.html").read_text(encoding="utf-8")
        cls.contribute = (ROOT / "docs/contribute.html").read_text(encoding="utf-8")
        cls.components = (ROOT / "docs/assets/components.js").read_text(encoding="utf-8")
        cls.reader_js = (ROOT / "docs/assets/reader.js").read_text(encoding="utf-8")
        cls.styles = (ROOT / "docs/assets/styles.css").read_text(encoding="utf-8")

    def test_homepage_is_semantic_and_catalog_driven(self):
        for fragment in (
            'class="skip-link"',
            '<nav class="nav-shell"',
            'label for="course-search"',
            'id="course-grid"',
            'id="course-detail"',
            'id="empty-state"',
            'type="module" src="assets/home.js"',
        ):
            self.assertIn(fragment, self.index)
        self.assertNotIn("const DATA", self.index)
        self.assertNotIn("onclick=", self.index)

    def test_components_do_not_inject_catalog_html(self):
        self.assertIn("textContent", self.components)
        self.assertIn("document.createElement", self.components)
        self.assertNotIn("innerHTML", self.components)

    def test_reader_uses_catalog_ids_and_has_recovery_actions(self):
        for fragment in (
            'id="course-nav"',
            'id="mobile-item-select"',
            'id="reader-title"',
            'id="reader-meta"',
            'id="pdf-frame" title="PDF 阅读器"',
            'id="open-pdf"',
            'id="download-pdf"',
            'id="source-link"',
            'id="reader-error"',
            'type="module" src="assets/reader.js"',
        ):
            self.assertIn(fragment, self.reader)
        self.assertIn(".get('id')", self.reader_js)
        self.assertNotIn(".get('pdf')", self.reader_js)

    def test_contribution_page_describes_pr_boundary_and_limits(self):
        for fragment in (
            "只有维护者合并后",
            "≤ 25 MiB",
            "≤ 10 个 PDF",
            "≤ 100 MiB",
            "https://github.com/ysyecust/lecture-to-notes/upload/main/content/inbox",
            "- [x] I have the right to share these PDFs for educational use.",
        ):
            self.assertIn(fragment, self.contribute)

    def test_pages_have_restrictive_csp_and_external_styles(self):
        for source in (self.index, self.reader, self.contribute):
            self.assertIn("Content-Security-Policy", source)
            self.assertIn("object-src 'none'", source)
            self.assertIn('href="assets/styles.css"', source)
            self.assertNotIn("<style", source)

    def test_visual_tokens_and_responsive_accessibility_are_present(self):
        for fragment in (
            "--lab-paper: #f7fafb",
            "--blueprint: #173a50",
            "--ink-blue: #2f6bff",
            "--annotation: #ff6b5b",
            "--grid-line: #ccd8e0",
            ".course-spine",
            ".lecture-ticks",
            "prefers-reduced-motion",
            "max-width: 820px",
            "max-width: 560px",
        ):
            self.assertIn(fragment, self.styles)


if __name__ == "__main__":
    unittest.main()
