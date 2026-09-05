import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/lecture-to-notes/SKILL.md"
ASSETS_PLACEHOLDER = "/ABSOLUTE/PATH/TO/lecture-to-notes/assets"


class InstallSkillTests(unittest.TestCase):
    def test_installer_produces_every_asset_the_skill_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run(
                ["bash", str(ROOT / "scripts/install_skill.sh"), tmp],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            installed = Path(tmp) / "lecture-to-notes"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "references/reader-first-writing.md").is_file())
            self.assertTrue((installed / "assets/INSTALLED_FROM").is_file())
            text = (installed / "SKILL.md").read_text(encoding="utf-8")
            references = set(re.findall(
                re.escape(ASSETS_PLACEHOLDER) + r"/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)", text))
            self.assertGreater(len(references), 10)
            for relative in sorted(references):
                self.assertTrue((installed / "assets" / relative).exists(), relative)
            for helper in ("transcribe_whisper.py", "ocr_hardsubs.py", "frame_filter.py", "verify_notes.py", "extract_claims.py"):
                self.assertTrue((installed / "assets" / helper).is_file(), helper)

    def test_reinstall_replaces_previous_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            stale = Path(tmp) / "lecture-to-notes/assets/stale.py"
            stale.parent.mkdir(parents=True)
            stale.write_text("old", encoding="utf-8")
            subprocess.run(["bash", str(ROOT / "scripts/install_skill.sh"), tmp], check=True, capture_output=True)
            self.assertFalse(stale.exists())


if __name__ == "__main__":
    unittest.main()
