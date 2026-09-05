"""
Compile notes-template.tex with a smoke body that exercises every template macro.

Skipped when xelatex is not installed; the `template` CI job installs TeX Live with
CJK support so the check always runs there.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "skills/lecture-to-notes/assets/notes-template.tex"

SMOKE_BODY = r"""\section{测试}
温度 1150\,\degC，厚度 20--50\,\um，节点 14\,\nm，晶格 5.43\,\angstrom；公式 $T=1150\degC$。
\begin{importantbox}{核心概念}
每张配图下方以脚注标注其在原视频中的画面时间区间。
\end{importantbox}
\begin{figure}[H]\centering\rule{3cm}{1cm}\caption{示意\vtag}\end{figure}
\srcnote{03:57--04:02}
\subsection{本章小结}
正文结束。
"""


@unittest.skipUnless(shutil.which("xelatex"), "needs xelatex")
class TemplateCompileTests(unittest.TestCase):
    def test_template_compiles_with_macros(self):
        source = TEMPLATE.read_text(encoding="utf-8")
        marker = "%% --- 正文内容开始 --- %%"
        self.assertIn(marker, source)
        with tempfile.TemporaryDirectory() as tmp:
            tex = Path(tmp) / "t.tex"
            tex.write_text(source.replace(marker, marker + "\n" + SMOKE_BODY), encoding="utf-8")
            returncode = -1
            stdout = ""
            for _ in range(2):  # two passes so the table of contents resolves
                completed = subprocess.run(
                    ["xelatex", "-interaction=nonstopmode", "-halt-on-error", "t.tex"],
                    cwd=tmp, capture_output=True, text=True, check=False,
                )
                returncode, stdout = completed.returncode, completed.stdout
            log = (Path(tmp) / "t.log").read_text(encoding="utf-8", errors="replace")
            errors = [line for line in log.splitlines() if line.startswith("! ")]
            self.assertEqual(returncode, 0, "\n".join(errors[:5]) or stdout[-800:])
            self.assertEqual(errors, [])
            self.assertNotIn("invalid in math mode", log)
            self.assertNotIn("Missing character", log)
            self.assertTrue((Path(tmp) / "t.pdf").exists())
            pages = re.search(r"Output written on t\.pdf \((\d+) pages", log)
            self.assertIsNotNone(pages, "xelatex log lacks the 'Output written' line")
            self.assertGreaterEqual(int(pages.group(1)) if pages else 0, 3)


if __name__ == "__main__":
    unittest.main()
