import tempfile
import unittest
from pathlib import Path

from scripts.build_site import build_site
from tests.test_site_catalog import SiteCatalogTests, fake_inspector


ROOT = Path(__file__).resolve().parents[1]


class BuildSiteTests(unittest.TestCase):
    def test_container_build_makes_only_staging_output_writable(self):
        script = (ROOT / "scripts/build_site_container.sh").read_text()
        self.assertIn('mkdir -p "$STAGING"', script)
        self.assertIn('chmod 0777 "$STAGING"', script)
        self.assertIn('--user "$(id -u):$(id -g)"', script)
        self.assertNotIn('chmod 0777 "$ROOT"', script)

    def test_builds_shell_catalog_papers_and_legacy_pdf_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            SiteCatalogTests().source_tree(root)
            docs = root / "docs"
            for name in ("index.html", "reader.html", "contribute.html"):
                (docs / name).write_text(name, encoding="utf-8")
            (docs / "superpowers").mkdir()
            (docs / "superpowers/plan.md").write_text("private", encoding="utf-8")
            (docs / ".DS_Store").write_bytes(b"private")
            output = root / "_site"
            build_site(root, output, "2026-07-16T00:00:00Z", fake_inspector)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "reader.html").is_file())
            self.assertTrue((output / "contribute.html").is_file())
            self.assertTrue((output / "data/catalog.json").is_file())
            self.assertTrue((output / "pdfs/legacy-name.pdf").is_file())
            self.assertTrue((output / "papers/paper.html").is_file())
            self.assertFalse((output / "superpowers").exists())
            self.assertFalse(any(output.rglob(".DS_Store")))

    def test_refuses_source_directories_as_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            SiteCatalogTests().source_tree(root)
            with self.assertRaisesRegex(ValueError, "unsafe output"):
                build_site(root, root / "docs", "date", fake_inspector)


if __name__ == "__main__":
    unittest.main()
