import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"
SECTION_HEADING = "## 2026-07-11 — X/Twitter lecture video support"


class ReleaseNotesTests(unittest.TestCase):
    def test_x_twitter_release_entry_documents_support_and_compatibility(self):
        self.assertTrue(
            RELEASE_NOTES.is_file(),
            "root RELEASE_NOTES.md must document the X/Twitter release",
        )

        contents = RELEASE_NOTES.read_text(encoding="utf-8")
        self.assertIn(SECTION_HEADING, contents)
        section = contents.split(SECTION_HEADING, 1)[1].split("\n## ", 1)[0]

        required_text = (
            "X/Twitter",
            "scripts/video_source.py",
            "scripts/check_srt_health.py",
            "--no-playlist",
            "10%",
            "50%",
            "90%",
            "Whisper",
            "Bilibili",
            "No breaking changes",
            "backward compatibility",
            "python3 scripts/video_source.py detect",
            "python3 scripts/video_source.py probe",
        )
        for text in required_text:
            with self.subTest(text=text):
                self.assertIn(text, section)


if __name__ == "__main__":
    unittest.main()
