import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class XSupportDocumentationTests(unittest.TestCase):
    def test_readme_and_skill_document_x_contract(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        skill = (ROOT / "skills/lecture-to-notes/SKILL.md").read_text(encoding="utf-8")
        for text in (readme, skill):
            self.assertIn("X/Twitter", text)
            self.assertIn("scripts/video_source.py", text)
            self.assertIn("scripts/check_srt_health.py", text)
            self.assertIn("x.com/", text)
        self.assertIn("/video/<n>", skill)
        self.assertIn("90%", skill)
        self.assertIn("Whisper", skill)
