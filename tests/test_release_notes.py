import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"


class ReleaseNotesContentTests(unittest.TestCase):
    def test_release_notes_documents_tagged_releases(self):
        contents = RELEASE_NOTES.read_text(encoding="utf-8")
        for heading in (
            "## v1.2.0 — 2026-10-31",
            "## v1.1.0 — 2026-09-16",
            "## v1.0.1 — 2026-09-13",
            "## v1.0.0 — 2026-09-13",
        ):
            with self.subTest(heading=heading):
                self.assertIn(heading, contents)


if __name__ == "__main__":
    unittest.main()
