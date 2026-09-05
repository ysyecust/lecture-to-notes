import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import ocr_hardsubs

IGNORE = re.compile(ocr_hardsubs.DEFAULT_IGNORE)


def srt(entries):
    return ocr_hardsubs.format_srt(entries)


class SrtRoundTripTests(unittest.TestCase):
    def test_parse_and_format_round_trip(self):
        entries = [
            {"start": 0.0, "end": 2.24, "text": "芯片到底是怎么被制造出来的"},
            {"start": 61.5, "end": 63.0, "text": "两行\n字幕"},
        ]
        text = srt(entries)
        parsed = ocr_hardsubs.parse_srt(text)
        self.assertEqual(len(parsed), 2)
        self.assertAlmostEqual(parsed[0]["end"], 2.24, places=3)
        self.assertEqual(parsed[1]["text"], "两行 字幕")
        self.assertIn("00:01:01,500 --> 00:01:03,000", text)


class CleaningTests(unittest.TestCase):
    def test_watermarks_and_short_fragments_are_dropped(self):
        lines = ["bilibili", "@谈三圈", "!", "刻蚀技术可以分为两类", "谈三圈blibili"]
        self.assertEqual(ocr_hardsubs.clean_lines(lines, IGNORE), ["刻蚀技术可以分为两类"])

    def test_normalize_ignores_punctuation_and_spaces(self):
        self.assertEqual(ocr_hardsubs.normalize("刻蚀，技术 可以（分为）两类。"), "刻蚀技术可以分为两类")


class DetectTests(unittest.TestCase):
    def test_majority_of_samples_with_text_means_hardsubs(self):
        results = [["bilibili", "刻蚀技术"], ["光刻胶"], [], ["谈三圈"], ["硅片厚度"]]
        verdict = ocr_hardsubs.assess_hits(results, IGNORE)
        self.assertEqual(verdict["hits"], 3)
        self.assertTrue(verdict["has_hardsubs"])

    def test_logo_only_frames_do_not_count(self):
        results = [["bilibili"], ["@谈三圈"], [], ["bilibili"]]
        self.assertFalse(ocr_hardsubs.assess_hits(results, IGNORE)["has_hardsubs"])


class ExtractTests(unittest.TestCase):
    def test_consecutive_frames_with_same_text_merge_into_one_entry(self):
        readings = {
            "f0": ["bilibili", "芯片到底是怎么被制造出来的"],
            "f1": ["芯片到底是怎么被制造出来的"],
            "f2": ["芯片到底是怎么被制造出来的!"],   # OCR jitter
            "f3": [],
            "f4": ["这是全网最详细的芯片制造教学"],
            "f5": ["这是全网最详细的芯片制造教学"],
        }
        frames = [(float(i), f"f{i}") for i in range(6)]
        entries = ocr_hardsubs.extract_entries(frames, lambda p: readings[p], fps=1.0, ignore=IGNORE)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["text"], "芯片到底是怎么被制造出来的")
        self.assertEqual((entries[0]["start"], entries[0]["end"]), (0.0, 3.0))
        self.assertEqual((entries[1]["start"], entries[1]["end"]), (4.0, 6.0))

    def test_majority_reading_wins_inside_a_run(self):
        readings = {"f0": ["光刻胶"], "f1": ["光刻股"], "f2": ["光刻胶"]}
        frames = [(float(i), f"f{i}") for i in range(3)]
        entries = ocr_hardsubs.extract_entries(frames, lambda p: readings[p], fps=1.0, ignore=IGNORE, similarity=0.6)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["text"], "光刻胶")


class GeometryTests(unittest.TestCase):
    def test_static_nav_text_and_moving_subtitles_give_crop_geometry(self):
        frames = []
        for i in range(10):
            boxes = [("制造晶圆", 1044, 1072), ("光刻工艺", 1045, 1073), ("谈三圈 bilibili", 30, 70)]
            boxes.append(("Roh-Silizium 蒸馏塔", 220, 300))
            if i % 10 < 7:  # 70% of frames carry a subtitle line
                boxes.append((f"字幕第{i}行内容不同", 905 + (i % 3), 968 + (i % 3)))
            frames.append(boxes)
        geometry = ocr_hardsubs.band_geometry(frames, 1080, IGNORE)
        self.assertEqual(geometry["nav_strip"], 1080 - 1040)
        y0, y1 = geometry["subtitle_band"]
        self.assertLessEqual(y0, 905)
        self.assertGreaterEqual(y1, 970)
        self.assertEqual(geometry["crop_bottom"], 1080 - y0)
        self.assertAlmostEqual(geometry["subtitle_frame_share"], 0.7)

    def test_no_bottom_text_means_nothing_to_crop(self):
        frames = [[("标题", 100, 140)] for _ in range(6)]
        geometry = ocr_hardsubs.band_geometry(frames, 1080, IGNORE)
        self.assertEqual(geometry["nav_strip"], 0)
        self.assertIsNone(geometry["subtitle_band"])
        self.assertEqual(geometry["crop_bottom"], 0)


class GlossaryTests(unittest.TestCase):
    def test_homophone_errors_become_pairs(self):
        whisper = [
            {"start": 0, "end": 2, "text": "这种过程就叫刻石"},
            {"start": 10, "end": 12, "text": "刻石技术可以分为两类"},
            {"start": 20, "end": 22, "text": "光眼膜上的图形"},
            {"start": 30, "end": 32, "text": "光眼膜非常昂贵"},
            {"start": 40, "end": 42, "text": "完全无关的一句话"},
        ]
        ocr = [
            {"start": 0.5, "end": 2.5, "text": "这种过程就叫刻蚀"},
            {"start": 10.2, "end": 12.5, "text": "刻蚀技术可以分为两类"},
            {"start": 19.8, "end": 22.0, "text": "光掩膜上的图形"},
            {"start": 30.1, "end": 32.4, "text": "光掩膜非常昂贵"},
            {"start": 40.0, "end": 42.0, "text": "晶圆厂里的机器"},
        ]
        glossary, stats = ocr_hardsubs.build_glossary(whisper, ocr, window=3.0, min_count=2)
        self.assertEqual(glossary.get("石"), "蚀")
        self.assertEqual(glossary.get("眼"), "掩")
        self.assertEqual(stats["aligned"], 4)

    def test_single_occurrence_is_not_a_rule(self):
        whisper = [{"start": 0, "end": 2, "text": "这种过程就叫刻石"}]
        ocr = [{"start": 0, "end": 2, "text": "这种过程就叫刻蚀"}]
        glossary, _ = ocr_hardsubs.build_glossary(whisper, ocr, min_count=2)
        self.assertEqual(glossary, {})

    def test_long_rewrites_are_not_glossary_material(self):
        whisper = [{"start": 0, "end": 2, "text": "今天讲讲芯片的减肥和瘦身"}] * 2
        ocr = [{"start": 0, "end": 2, "text": "今天我们来聊一聊芯片工艺"}] * 2
        glossary, _ = ocr_hardsubs.build_glossary(whisper, ocr, min_count=1, min_ratio=0.0)
        for wrong, right in glossary.items():
            self.assertLessEqual(len(wrong), 4)
            self.assertLessEqual(len(right), 4)


if __name__ == "__main__":
    unittest.main()
