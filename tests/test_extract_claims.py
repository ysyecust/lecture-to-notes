import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import extract_claims

SRT = """1
00:03:08,000 --> 00:03:11,000
纯石墨坩埚的熔点可以高达3000摄氏度

2
00:05:23,000 --> 00:05:26,000
做法是在1140度的高温环境中

3
00:09:10,000 --> 00:09:14,000
4寸 6寸 8寸 12寸

4
00:15:32,000 --> 00:15:35,000
腐蚀掉表面约20-50微米左右的厚度

5
00:47:24,000 --> 00:47:26,000
1埃=0.1纳米 是5.66埃

6
00:58:36,000 --> 00:58:40,000
CMP步骤多达30次 使用的抛光液种类超过20种 分为2种
"""

TEX = r"""\documentclass{article}\begin{document}
石墨坩埚熔点可达 3\,000\,$^\circ\mathrm{C}$。硅晶格常数 \textbf{5.43\,$\mathrm{\AA}$}，锗 5.66\,\angstrom（1\,\angstrom = 0.1\,nm）。
晶圆尺寸 4/6/8/12 英寸。腐蚀掉约 20--50\,\um。14\,nm 以下 CMP 步骤多达 30 次、抛光液种类超过 20 种。
\end{document}"""


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.rows = extract_claims.extract_claims(extract_claims.parse_srt(SRT))
        self.values = [r["value"] for r in self.rows]

    def test_numbers_with_units_are_extracted_once_each(self):
        for value in ("3000摄氏度", "1140度", "4寸", "12寸", "20-50微米", "5.66埃", "0.1纳米", "30次", "20种"):
            self.assertIn(value, self.values)
        self.assertEqual(len(self.values), len(set(self.values)))

    def test_bare_small_counts_are_not_claims(self):
        self.assertNotIn("2种", self.values)

    def test_rows_carry_context_and_time(self):
        row = next(r for r in self.rows if r["value"] == "1140度")
        self.assertEqual(row["source_time"], "05:23")
        self.assertIn("高温", row["claim"])

    def test_tsv_round_trip(self):
        text = extract_claims.format_tsv(self.rows)
        self.assertTrue(text.startswith("claim\tvalue\tsource_time\tin_notes\n"))
        self.assertEqual(len(extract_claims.parse_tsv(text)), len(self.rows))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.flat = extract_claims.flatten_tex(TEX)

    def test_latex_spacing_and_unit_macros_do_not_hide_numbers(self):
        self.assertTrue(extract_claims.claim_in_notes("3000摄氏度", self.flat))
        self.assertTrue(extract_claims.claim_in_notes("5.66埃", self.flat))
        self.assertTrue(extract_claims.claim_in_notes("20-50微米", self.flat))
        self.assertTrue(extract_claims.claim_in_notes("30次", self.flat))

    def test_missing_number_is_reported(self):
        self.assertFalse(extract_claims.claim_in_notes("1140度", self.flat))

    def test_cli_check_marks_rows_and_fails_on_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            srt = Path(tmp) / "audio.srt"
            srt.write_text(SRT, encoding="utf-8")
            tex = Path(tmp) / "notes.tex"
            tex.write_text(TEX, encoding="utf-8")
            tsv = Path(tmp) / "numerical_claims.tsv"
            self.assertEqual(extract_claims.main(["extract", str(srt), "--out", str(tsv)]), 0)
            code = extract_claims.main(["check", str(tsv), str(tex), "--write"])
            self.assertEqual(code, 1)
            rows = extract_claims.parse_tsv(tsv.read_text(encoding="utf-8"))
            by_value = {r["value"]: r["in_notes"] for r in rows}
            self.assertEqual(by_value["1140度"], "no")
            self.assertEqual(by_value["5.66埃"], "yes")


if __name__ == "__main__":
    unittest.main()
