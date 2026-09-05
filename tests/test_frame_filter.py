import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import frame_filter

H, W = 200, 320
rng = np.random.default_rng(7)


def dark_frame():
    return rng.integers(0, 12, size=(H, W), dtype=np.uint8)


def with_nav_strip(frame, rows=12):
    pattern = np.tile(np.array([[30, 200, 30, 90]], dtype=np.uint8), (rows, W // 4))
    frame[H - rows:, :] = pattern
    return frame


def with_subtitle(frame, y0=150, y1=170):
    x = int(rng.integers(40, 200))
    for k in range(6):
        frame[y0 + 3:y1 - 3, x + k * 14: x + k * 14 + 8] = 255
    return frame


def with_center_person(frame):
    yy, xx = np.mgrid[0:H, 0:W]
    ellipse = ((xx - W / 2) / (0.12 * W)) ** 2 + ((yy - H * 0.55) / (0.35 * H)) ** 2 <= 1
    frame[ellipse] = 150
    return frame


def with_side_diagrams(frame):
    frame[40:120, 20:90] = 220
    frame[40:120, 230:300] = 220
    return frame


class BandDetectionTests(unittest.TestCase):
    def test_static_strip_and_subtitle_band_are_found(self):
        frames = []
        for i in range(24):
            f = with_nav_strip(dark_frame())
            if i % 4 != 0:  # 75% of frames carry a subtitle
                f = with_subtitle(f)
            frames.append(f)
        result = frame_filter.detect_bands(frames)
        self.assertGreaterEqual(result["nav_strip"], 10)
        self.assertLessEqual(result["nav_strip"], 14)
        self.assertIsNotNone(result["subtitle_band"])
        y0, y1 = result["subtitle_band"]
        self.assertLessEqual(y0, 153)
        self.assertGreaterEqual(y1, 167)
        self.assertGreaterEqual(result["crop_bottom"], H - 153)

    def test_plain_dark_bottom_is_not_a_strip(self):
        frames = [dark_frame() for _ in range(12)]
        result = frame_filter.detect_bands(frames)
        self.assertEqual(result["nav_strip"], 0)
        self.assertIsNone(result["subtitle_band"])
        self.assertEqual(result["crop_bottom"], 0)


class ScoreTests(unittest.TestCase):
    def test_presenter_only_frame_is_a_talking_head(self):
        scores = frame_filter.score_frame(with_subtitle(with_center_person(dark_frame())))
        self.assertTrue(frame_filter.classify(scores))

    def test_side_diagrams_are_content(self):
        scores = frame_filter.score_frame(with_side_diagrams(with_center_person(dark_frame())))
        self.assertFalse(frame_filter.classify(scores))

    def test_centered_diagram_on_black_is_content(self):
        frame = dark_frame()
        yy, xx = np.mgrid[0:H, 0:W]
        ring = np.abs(np.sqrt((xx - W / 2) ** 2 + (yy - H * 0.42) ** 2) - 0.22 * H) < 6
        frame[ring] = 200
        scores = frame_filter.score_frame(frame)
        self.assertFalse(frame_filter.classify(scores))

    def test_bright_slide_is_content(self):
        slide = np.full((H, W), 235, dtype=np.uint8)
        slide[60:80, 30:290] = 20
        scores = frame_filter.score_frame(slide)
        self.assertFalse(frame_filter.classify(scores))


class CliTests(unittest.TestCase):
    def test_crop_with_bands_json_removes_bottom_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "f.jpg"
            Image.fromarray(with_nav_strip(dark_frame())).save(src)
            bands = Path(tmp) / "bands.json"
            bands.write_text(json.dumps({"crop_bottom": 30}), encoding="utf-8")
            out = Path(tmp) / "c.jpg"
            code = frame_filter.main(["crop", str(src), "--out", str(out), "--bands", str(bands)])
            self.assertEqual(code, 0)
            with Image.open(out) as image:
                self.assertEqual(image.size, (W, H - 30))

    def test_score_cli_writes_json_with_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            head = Path(tmp) / "head.jpg"
            slide = Path(tmp) / "slide.jpg"
            Image.fromarray(with_center_person(dark_frame())).save(head)
            Image.fromarray(with_side_diagrams(dark_frame())).save(slide)
            out = Path(tmp) / "scores.json"
            code = frame_filter.main(["score", str(head), str(slide), "--json", str(out)])
            self.assertEqual(code, 0)
            rows = {Path(r["frame"]).name: r for r in json.loads(out.read_text(encoding="utf-8"))}
            self.assertTrue(rows["head.jpg"]["talking_head"])
            self.assertFalse(rows["slide.jpg"]["talking_head"])


if __name__ == "__main__":
    unittest.main()
