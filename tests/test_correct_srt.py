import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "correct_srt.py"


class CorrectSrtCliTests(unittest.TestCase):
    def run_correction(self, source, output=None):
        glossary = source.parent / "glossary.json"
        glossary.write_text(json.dumps({"刻石": "刻蚀"}), encoding="utf-8")
        command = [sys.executable, str(SCRIPT), str(source), "-g", str(glossary)]
        if output is not None:
            command += ["-o", str(output)]
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8")

    def test_no_entries_preserves_input_when_overwriting_in_place(self):
        for content, message in (
            (b"", "no subtitle entries"),
            (b"not an SRT transcript\n", "incomplete SRT block"),
            (b"1\n00:00:00,000 --> 00:00:01,000\n", "incomplete SRT block"),
        ):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "audio.srt"
                source.write_bytes(content)
                result = self.run_correction(source)
                self.assertEqual(source.read_bytes(), content)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    def test_no_entries_preserves_existing_explicit_output(self):
        for content in (b"", b"not an SRT transcript\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "audio.srt"
                source.write_bytes(content)
                output = Path(tmp) / "corrected.srt"
                original = b"existing output must survive\r\n"
                output.write_bytes(original)
                result = self.run_correction(source, output)
                self.assertEqual(source.read_bytes(), content)
                self.assertEqual(output.read_bytes(), original)
                self.assertEqual(result.returncode, 2)

    def test_no_entries_does_not_create_explicit_output(self):
        for content in (b"", b"not an SRT transcript\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "audio.srt"
                source.write_bytes(content)
                output = Path(tmp) / "corrected.srt"
                result = self.run_correction(source, output)
                self.assertEqual(source.read_bytes(), content)
                self.assertFalse(output.exists())
                self.assertEqual(result.returncode, 2)

    def test_incomplete_block_does_not_allow_partial_overwrite(self):
        for mode in ("in-place", "existing-output", "new-output"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / "audio.srt"
                content = ("1\n00:00:00,000 --> 00:00:01,000\n刻石\n\n"
                           "incomplete subtitle block\n").encode("utf-8")
                source.write_bytes(content)
                output = None if mode == "in-place" else Path(tmp) / "corrected.srt"
                original_output = b"existing output must survive\r\n"
                if mode == "existing-output":
                    output.write_bytes(original_output)
                result = self.run_correction(source, output)
                self.assertEqual(source.read_bytes(), content)
                if mode == "existing-output":
                    self.assertEqual(output.read_bytes(), original_output)
                elif mode == "new-output":
                    self.assertFalse(output.exists())
                self.assertEqual(result.returncode, 2)
                self.assertIn("incomplete SRT block", result.stderr)

    def test_valid_input_is_corrected_in_place_with_timing_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "audio.srt"
            content = ("1\n00:00:00,000 --> 00:00:01,000\n刻石\n第二行\n\n"
                       "2\n00:00:02,000 --> 00:00:03,000\n无需修改\n")
            source.write_text(content, encoding="utf-8")
            result = self.run_correction(source)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source.read_text(encoding="utf-8"),
                             content.replace("刻石", "刻蚀"))

    def test_valid_explicit_output_leaves_source_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "audio.srt"
            content = "1\n00:00:00,000 --> 00:00:01,000\n刻石\n"
            source.write_text(content, encoding="utf-8")
            original = source.read_bytes()
            output = Path(tmp) / "corrected.srt"
            result = self.run_correction(source, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(output.read_text(encoding="utf-8"),
                             content.replace("刻石", "刻蚀"))


if __name__ == "__main__":
    unittest.main()
