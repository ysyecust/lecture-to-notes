import json
import tempfile
import unittest
from pathlib import Path

from scripts.pdf_inspector import PdfInspection, sha256_file
from scripts.site_catalog import CatalogError, build_catalog
from tests.pdf_factory import write_pdf


def fake_inspector(path: Path, thumbnail_dir: Path) -> PdfInspection:
    digest = sha256_file(path)
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    thumbnail = thumbnail_dir / f"{digest[:16]}.webp"
    thumbnail.write_bytes(b"webp")
    detected = path.stem.replace("_", " ").replace("-", " ").title()
    return PdfInspection(path, detected, "filename", 1, digest, thumbnail)


class SiteCatalogTests(unittest.TestCase):
    def source_tree(self, root: Path, expected_pages: int = 1):
        content = root / "content"
        course = content / "courses/course-a"
        course.mkdir(parents=True)
        write_pdf(course / "legacy-name.pdf")
        (course / "course.json").write_text(
            json.dumps(
                {
                    "id": "course-a",
                    "title": "Course A",
                    "institution": "University",
                    "term": "2026",
                    "description": "A course",
                    "tags": ["systems"],
                    "source_url": "https://example.com/course",
                    "featured": True,
                    "items": [
                        {
                            "file": "legacy-name.pdf",
                            "title": "Trusted title",
                            "order": 1,
                            "expected_pages": expected_pages,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        inbox = content / "inbox"
        inbox.mkdir(parents=True)
        write_pdf(inbox / "community.pdf")
        (content / "papers.json").write_text(
            json.dumps(
                [
                    {
                        "id": "paper",
                        "title": "Paper",
                        "meta": "AI",
                        "url": "papers/paper.html",
                    }
                ]
            ),
            encoding="utf-8",
        )
        docs = root / "docs/papers"
        docs.mkdir(parents=True)
        (docs / "paper.html").write_text("paper", encoding="utf-8")
        return content, root / "docs"

    def test_builds_deterministic_schema_and_trusted_title(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content, docs = self.source_tree(root)
            output = root / "output"
            catalog = build_catalog(
                content,
                output,
                "2026-07-16T00:00:00Z",
                docs_root=docs,
                inspector=fake_inspector,
            )
            self.assertEqual(
                {"schema_version", "generated_at", "stats", "courses", "items", "papers"},
                set(catalog),
            )
            self.assertEqual(1, catalog["schema_version"])
            self.assertEqual(
                {"lecture_count", "paper_count", "page_count", "course_count", "pdf_bytes"},
                set(catalog["stats"]),
            )
            self.assertEqual("course-a", catalog["courses"][0]["id"])
            self.assertEqual("Trusted title", catalog["items"][0]["title"])
            self.assertEqual("Legacy Name", catalog["items"][0]["detected_title"])
            self.assertEqual("community-contributions", catalog["courses"][1]["id"])
            self.assertTrue((output / "pdfs/legacy-name.pdf").is_file())

    def test_rejects_page_count_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            content, docs = self.source_tree(root, expected_pages=2)
            with self.assertRaisesRegex(CatalogError, "page-count mismatch"):
                build_catalog(
                    content,
                    root / "output",
                    "date",
                    docs_root=docs,
                    inspector=fake_inspector,
                )

    def test_rejects_duplicate_basenames_and_http_sources(self):
        for mutation, message in (("duplicate", "duplicate PDF basename"), ("http", "HTTPS")):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                content, docs = self.source_tree(root)
                if mutation == "duplicate":
                    second = content / "courses/course-b"
                    second.mkdir()
                    write_pdf(second / "legacy-name.pdf")
                    (second / "course.json").write_text(
                        json.dumps(
                            {
                                "id": "course-b",
                                "title": "B",
                                "institution": "U",
                                "term": "2026",
                                "items": [{"file": "legacy-name.pdf", "title": "B"}],
                            }
                        ),
                        encoding="utf-8",
                    )
                else:
                    manifest_path = content / "courses/course-a/course.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["source_url"] = "http://example.com"
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaisesRegex(CatalogError, message):
                    build_catalog(
                        content,
                        root / "output",
                        "date",
                        docs_root=docs,
                        inspector=fake_inspector,
                    )


if __name__ == "__main__":
    unittest.main()
