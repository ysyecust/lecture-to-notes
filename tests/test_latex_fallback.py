import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "skills/lecture-to-notes/SKILL.md").read_text(encoding="utf-8")
TEMPLATE = (
    ROOT / "skills/lecture-to-notes/assets/notes-template.tex"
).read_text(encoding="utf-8")


class LatexFallbackTests(unittest.TestCase):
    def test_skill_checks_every_template_package(self):
        checked = set(re.findall(r"for pkg in ([^;]+); do", SKILL)[0].split())
        required = {
            "ctex",
            "tcolorbox",
            "environ",
            "trimspaces",
            "listings",
            "hyperref",
            "booktabs",
            "float",
            "subcaption",
            "etoolbox",
        }
        self.assertTrue(required <= checked, required - checked)

    def test_template_prefers_ctex_and_has_native_xetex_fallback(self):
        self.assertIn(r"\IfFileExists{ctex.sty}", TEMPLATE)
        self.assertIn(r"\usepackage[fontset=fandol]{ctex}", TEMPLATE)
        self.assertIn(r'\XeTeXlinebreaklocale "zh"', TEMPLATE)
        self.assertIn("Songti SC", TEMPLATE)
        self.assertIn("Noto Serif CJK SC", TEMPLATE)
        self.assertLess(
            TEMPLATE.index(r"\IfFileExists{ctex.sty}"),
            TEMPLATE.index(r"\usepackage{amsmath, amssymb}"),
        )

    def test_install_guidance_names_every_non_core_package(self):
        install_line = next(
            line for line in SKILL.splitlines() if "tlmgr install ctex" in line
        )
        for package in ("ctex", "tcolorbox", "environ", "trimspaces", "etoolbox"):
            self.assertIn(package, install_line)


if __name__ == "__main__":
    unittest.main()
