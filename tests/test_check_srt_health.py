import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_srt_health


def block(index, start, end, text):
    return f"{index}\n{start} --> {end}\n{text}\n"


def healthy_track():
    return "\n".join(
        [
            block(1, "00:00:05,000", "00:00:12,000", "opening"),
            block(2, "00:00:47,000", "00:00:53,000", "middle"),
            block(3, "00:01:32,000", "00:01:38,000", "ending"),
        ]
    )


class SrtHealthTests(unittest.TestCase):
    def test_healthy_track(self):
        result = check_srt_health.assess_srt(healthy_track(), duration=100)

        self.assertTrue(result["healthy"])
        self.assertEqual(result["entry_count"], 3)
        self.assertGreaterEqual(result["coverage"], 0.9)

    def test_rejects_timeline_far_beyond_duration_and_bounds_coverage(self):
        text = "\n".join(
            [
                block(1, "00:00:05,000", "00:00:12,000", "opening"),
                block(2, "00:00:47,000", "00:00:53,000", "middle"),
                block(3, "00:01:32,000", "99:00:00,000", "ending"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertFalse(result["healthy"])
        self.assertIn("timestamp_exceeds_duration", result["reasons"])
        self.assertEqual(result["coverage"], 1.0)

    def test_accepts_timeline_overrun_within_tolerance(self):
        text = "\n".join(
            [
                block(1, "00:00:05,000", "00:00:12,000", "opening"),
                block(2, "00:00:47,000", "00:00:53,000", "middle"),
                block(3, "00:01:32,000", "00:01:40,999", "ending"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertTrue(result["healthy"])
        self.assertEqual(result["coverage"], 1.0)

    def test_rejects_timeline_overrun_beyond_tolerance(self):
        text = "\n".join(
            [
                block(1, "00:00:05,000", "00:00:12,000", "opening"),
                block(2, "00:00:47,000", "00:00:53,000", "middle"),
                block(3, "00:01:32,000", "00:01:41,001", "ending"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertFalse(result["healthy"])
        self.assertIn("timestamp_exceeds_duration", result["reasons"])

    def test_timeline_overrun_tolerance_scales_for_long_media(self):
        within_tolerance = "\n".join(
            [
                block(1, "00:01:40,000", "00:03:20,000", "opening"),
                block(2, "00:15:00,000", "00:16:40,000", "middle"),
                block(3, "00:28:20,000", "00:33:21,999", "ending"),
            ]
        )
        beyond_tolerance = within_tolerance.replace(
            "00:33:21,999", "00:33:22,001"
        )

        accepted = check_srt_health.assess_srt(within_tolerance, duration=2000)
        rejected = check_srt_health.assess_srt(beyond_tolerance, duration=2000)

        self.assertTrue(accepted["healthy"])
        self.assertEqual(accepted["coverage"], 1.0)
        self.assertFalse(rejected["healthy"])
        self.assertIn("timestamp_exceeds_duration", rejected["reasons"])

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

    def test_rejects_invalid_numeric_options(self):
        cases = [
            ("duration_bool", {"duration": True}),
            ("duration_string", {"duration": "100"}),
            ("duration_zero", {"duration": 0}),
            ("duration_negative", {"duration": -1}),
            ("duration_nan", {"duration": float("nan")}),
            ("duration_infinity", {"duration": float("inf")}),
            ("duration_negative_infinity", {"duration": float("-inf")}),
            (
                "min_coverage_negative",
                {"duration": 100, "min_coverage": -0.01},
            ),
            (
                "min_coverage_above_one",
                {"duration": 100, "min_coverage": 1.01},
            ),
            (
                "min_coverage_nan",
                {"duration": 100, "min_coverage": float("nan")},
            ),
            (
                "min_coverage_infinity",
                {"duration": 100, "min_coverage": float("inf")},
            ),
            (
                "max_repetition_negative",
                {"duration": 100, "max_repetition": -0.01},
            ),
            (
                "max_repetition_above_one",
                {"duration": 100, "max_repetition": 1.01},
            ),
            (
                "max_repetition_nan",
                {"duration": 100, "max_repetition": float("nan")},
            ),
            (
                "max_repetition_infinity",
                {"duration": 100, "max_repetition": float("inf")},
            ),
            ("window_ratio_zero", {"duration": 100, "window_ratio": 0}),
            (
                "window_ratio_negative",
                {"duration": 100, "window_ratio": -0.01},
            ),
            (
                "window_ratio_above_limit",
                {"duration": 100, "window_ratio": 0.2001},
            ),
            (
                "window_ratio_nan",
                {"duration": 100, "window_ratio": float("nan")},
            ),
            (
                "window_ratio_infinity",
                {"duration": 100, "window_ratio": float("inf")},
            ),
        ]

        for label, options in cases:
            with self.subTest(label=label):
                with self.assertRaises(check_srt_health.SrtParseError):
                    check_srt_health.assess_srt(healthy_track(), **options)

    def test_full_span_cue_lacks_distinct_runtime_evidence(self):
        text = block(1, "00:00:00,000", "00:01:40,000", "entire lecture")

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertFalse(result["healthy"])
        self.assertTrue(all(result["windows"].values()))
        self.assertEqual(
            result["reasons"], ["insufficient_distinct_runtime_evidence"]
        )

    def test_window_evidence_requires_a_distinct_cue_assignment(self):
        text = "\n".join(
            [
                block(1, "00:00:00,000", "00:00:02,000", "first"),
                block(2, "00:00:03,000", "00:00:04,000", "second"),
                block(3, "00:00:05,000", "00:01:40,000", "spanning"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertFalse(result["healthy"])
        self.assertTrue(all(result["windows"].values()))
        self.assertIn("insufficient_distinct_runtime_evidence", result["reasons"])

    def test_main_reports_invalid_utf8_without_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.srt"
            path.write_bytes(b"\xff\xfe")
            stderr = io.StringIO()
            argv = ["check_srt_health.py", str(path), "--duration", "100"]

            with patch.object(sys, "argv", argv), patch.object(
                sys, "stderr", stderr
            ):
                status = check_srt_health.main()

        self.assertEqual(status, 2)
        self.assertTrue(stderr.getvalue().strip())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_requires_ascii_decimal_cue_index(self):
        for index in ("cue", "١"):
            with self.subTest(index=index):
                with self.assertRaises(check_srt_health.SrtParseError):
                    check_srt_health.parse_srt(
                        block(
                            index,
                            "00:00:05,000",
                            "00:00:10,000",
                            "caption",
                        )
                    )

    def test_rejects_cues_concatenated_without_blank_separator(self):
        text = block(
            1, "00:00:05,000", "00:00:10,000", "first"
        ) + block(2, "00:00:20,000", "00:00:25,000", "second")

        with self.assertRaises(check_srt_health.SrtParseError):
            check_srt_health.parse_srt(text)

    def test_rejects_out_of_range_timestamp_components(self):
        for invalid_end in ("00:60:00,000", "00:00:60,000"):
            with self.subTest(invalid_end=invalid_end):
                with self.assertRaises(check_srt_health.SrtParseError):
                    check_srt_health.parse_srt(
                        block(1, "00:00:00,000", invalid_end, "caption")
                    )

    def test_rejects_non_ascii_timestamp_digits(self):
        text = block(
            1,
            "٠٠:٠٠:٠٥,٠٠٠",
            "٠٠:٠٠:١٠,٠٠٠",
            "caption",
        )

        with self.assertRaises(check_srt_health.SrtParseError):
            check_srt_health.parse_srt(text)

    def test_seconds_normalizes_numeric_conversion_errors(self):
        for parts in (
            ("bad", "00", "00", "000"),
            ("00", None, "00", "000"),
            ("9" * 400, "00", "00", "000"),
        ):
            with self.subTest(parts=parts):
                with self.assertRaises(check_srt_health.SrtParseError):
                    check_srt_health._seconds(parts)

    def test_direct_parsing_and_assessment_accept_one_leading_bom(self):
        text = "\ufeff" + healthy_track()

        entries = check_srt_health.parse_srt(text)
        result = check_srt_health.assess_srt(text, duration=100)

        self.assertEqual(len(entries), 3)
        self.assertTrue(result["healthy"])

    def test_reasons_keep_deterministic_order(self):
        text = "\n".join(
            [
                block(1, "00:00:01,000", "00:00:02,000", "same"),
                block(2, "00:00:03,000", "00:00:04,000", "same"),
                block(3, "00:00:05,000", "00:00:06,000", "same"),
            ]
        )

        result = check_srt_health.assess_srt(text, duration=100)

        self.assertEqual(
            result["reasons"],
            [
                "coverage_below_threshold",
                "repetition_above_threshold",
                "empty_runtime_window",
                "insufficient_distinct_runtime_evidence",
            ],
        )


if __name__ == "__main__":
    unittest.main()
