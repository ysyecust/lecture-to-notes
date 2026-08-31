from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.transcribe_x_asr import (
    Cue,
    discover_model_files,
    format_srt_timestamp,
    normalize_token_text,
    tokens_to_cues,
    write_srt,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "transcribe_x_asr.py"


class XAsrUtilityTests(unittest.TestCase):
    def test_normalizes_mixed_chinese_english_tokens(self):
        tokens = [" 昨", " 天", " 是", " ", "M", "on", "da", "y", " ，", " today"]
        self.assertEqual("昨天是 Monday，today", normalize_token_text(tokens))

    def test_token_timestamps_become_punctuation_bounded_cues(self):
        cues = tokens_to_cues(
            [" 你", " 好", " ，", " world", " ！"],
            [0.4, 0.7, 1.0, 1.4, 2.0],
            chunk_start=10.0,
            chunk_duration=3.0,
            max_cue_seconds=8.0,
            max_cue_chars=52,
        )
        self.assertEqual(["你好，world！"], [cue.text for cue in cues])
        self.assertGreaterEqual(cues[0].start, 10.0)
        self.assertLessEqual(cues[0].end, 13.0)

    def test_adjacent_cues_do_not_overlap(self):
        cues = tokens_to_cues(
            [" 一", "。", " 二", "。"],
            [0.4, 1.0, 1.1, 1.7],
            chunk_start=0.0,
            chunk_duration=2.0,
        )
        self.assertEqual(2, len(cues))
        self.assertGreaterEqual(cues[1].start, cues[0].end)

    def test_long_unpunctuated_tokens_are_split(self):
        cues = tokens_to_cues(
            [" a", " b", " c", " d"],
            [0.0, 2.0, 4.0, 9.0],
            chunk_start=0.0,
            chunk_duration=10.0,
            max_cue_seconds=5.0,
            max_cue_chars=100,
        )
        self.assertEqual(2, len(cues))

    def test_discovers_int8_model_files_preferentially(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory)
            for name in (
                "encoder.onnx",
                "encoder.int8.onnx",
                "decoder.onnx",
                "joiner.onnx",
                "joiner.int8.onnx",
                "tokens.txt",
            ):
                (model / name).write_bytes(b"")
            files = discover_model_files(model)
            self.assertEqual("encoder.int8.onnx", files.encoder.name)
            self.assertEqual("decoder.onnx", files.decoder.name)
            self.assertEqual("joiner.int8.onnx", files.joiner.name)

    def test_writes_standard_srt(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audio.srt"
            write_srt(output, [Cue(1.25, 2.5, "中英 mixed text")])
            self.assertEqual(
                "1\n00:00:01,250 --> 00:00:02,500\n中英 mixed text\n\n",
                output.read_text(encoding="utf-8"),
            )

    def test_help_does_not_require_optional_runtime(self):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("sherpa-onnx X ASR", completed.stdout)

    def test_timestamp_rounding(self):
        self.assertEqual("01:01:01,235", format_srt_timestamp(3661.2346))


if __name__ == "__main__":
    unittest.main()
