import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_srt_health


def block(index, start, end, text):
    return f"{index}\n{start} --> {end}\n{text}\n"


class SrtHealthTests(unittest.TestCase):
    def test_healthy_track(self):
        text = "\n".join(
            [
                block(1, "00:00:05,000", "00:00:12,000", "opening"),
                block(2, "00:00:47,000", "00:00:53,000", "middle"),
                block(3, "00:01:32,000", "00:01:38,000", "ending"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertTrue(result["healthy"])
        self.assertEqual(result["entry_count"], 3)
        self.assertGreaterEqual(result["coverage"], 0.9)

    def test_truncated_track(self):
        text = block(1, "00:00:01,000", "00:00:10,000", "opening")

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertFalse(result["healthy"])
        self.assertIn("coverage_below_threshold", result["reasons"])

    def test_non_monotonic_track(self):
        text = "\n".join(
            [
                block(1, "00:00:20,000", "00:00:25,000", "later"),
                block(2, "00:00:10,000", "00:00:15,000", "earlier"),
            ]
        )

        with self.assertRaises(check_srt_health.SrtParseError):
            check_srt_health.assess_srt(text, duration=30)

    def test_repetition(self):
        text = "\n".join(
            [
                block(1, "00:00:05,000", "00:00:10,000", "same"),
                block(2, "00:00:45,000", "00:00:50,000", "same"),
                block(3, "00:01:30,000", "00:01:35,000", "same"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertFalse(result["healthy"])
        self.assertIn("repetition_above_threshold", result["reasons"])

    def test_empty_runtime_window(self):
        text = "\n".join(
            [
                block(1, "00:00:05,000", "00:00:10,000", "opening"),
                block(2, "00:01:32,000", "00:01:38,000", "ending"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertFalse(result["healthy"])
        self.assertIn("empty_runtime_window", result["reasons"])


if __name__ == "__main__":
    unittest.main()
