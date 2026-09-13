import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as error:  # pragma: no cover - environment dependent
    raise unittest.SkipTest(f"frame_filter tests need Pillow and numpy: {error}")

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


def camera_view(height, width, i, seed):
    """Static camera: noisy wall, a dark board with a persistent frame and chalk tray, a moving body."""
    noise = np.random.default_rng(seed + i)
    view = noise.integers(40, 70, size=(height, width)).astype(np.uint8)
    view[int(height * 0.11):int(height * 0.72), 8:width - 8] = noise.integers(5, 20, size=(int(height * 0.72) - int(height * 0.11), width - 16))
    view[int(height * 0.72):int(height * 0.75), 4:width - 4] = 160
    x = 10 + (i * 17) % max(1, width - 50)
    view[int(height * 0.4):, x:x + 30] = 150
    return view


def slide_view(height, width, i):
    """Slides that turn every four frames: light page, dark title bar, text lines."""
    page = np.random.default_rng(100 + i // 4)
    view = np.full((height, width), 245, dtype=np.uint8)
    view[: max(4, height // 10), :] = 90
    for k in range(5):
        y = height // 5 + k * height // 7
        x = int(page.integers(8, width // 5))
        view[y:y + 6, x:min(width, x + int(page.integers(width // 3, width - x)))] = 30
    return view


def side_by_side_frames(count=24):
    """GSE-like 560×180 frame: 4:3 camera left, 16:9 slides right, a blurred grey seam."""
    frames = []
    for i in range(count):
        frame = np.zeros((180, 560), dtype=np.uint8)
        frame[:, :240] = camera_view(180, 240, i, 1)
        frame[:, 240:] = slide_view(180, 320, i)
        frame[:, 238:241] = 120
        frames.append(frame)
    return frames


def letterboxed_frames(count=24):
    """CMU-like 480×240 frame: 16:9 slides at y=30, a 16:9 camera at the right, black elsewhere."""
    frames = []
    for i in range(count):
        frame = np.random.default_rng(900 + i).integers(0, 3, size=(240, 480)).astype(np.uint8)
        frame[30:210, 0:320] = slide_view(180, 320, i)
        frame[75:165, 320:480] = camera_view(90, 160, i, 2)
        frames.append(frame)
    return frames


def sidebar_frames(count=24):
    """CppNow-like 16:9 480×270 frame: a speaker sidebar left, 16:9 slides inset on dark grey."""
    frames = []
    for i in range(count):
        frame = np.random.default_rng(700 + i).integers(28, 31, size=(270, 480)).astype(np.uint8)
        frame[20:200, 0:120] = camera_view(180, 120, i, 3)
        frame[40:229, 132:468] = slide_view(189, 336, i)
        frames.append(frame)
    return frames


def fullscreen_frames(count=16):
    return [slide_view(180, 320, i) for i in range(count)]


def panel(result, name):
    return next(p for p in result["panels"] if p["name"] == name)


class LayoutDetectionTests(unittest.TestCase):
    def assertBoxNear(self, box, expected, slack=3):
        for got, want in zip(box, expected):
            self.assertLessEqual(abs(got - want), slack, f"{box} vs {expected}")

    def test_side_by_side_slides_win_over_camera_rectangles(self):
        result = frame_filter.detect_layout(side_by_side_frames())
        self.assertTrue(result["composite"], result)
        self.assertBoxNear(panel(result, "main")["box"], [240, 0, 560, 180])
        self.assertBoxNear(panel(result, "left")["box"], [0, 0, 240, 180])
        self.assertEqual(result["consistency"], 1.0)

    def test_letterbox_is_trimmed_from_main_and_strip(self):
        result = frame_filter.detect_layout(letterboxed_frames())
        self.assertTrue(result["composite"], result)
        self.assertBoxNear(panel(result, "main")["box"], [0, 30, 320, 210])
        self.assertBoxNear(panel(result, "right")["box"], [320, 75, 480, 165])
        self.assertEqual({p["name"] for p in result["panels"]}, {"main", "right"})

    def test_sidebar_inside_a_16_9_frame_is_found(self):
        result = frame_filter.detect_layout(sidebar_frames())
        self.assertTrue(result["composite"], result)
        self.assertBoxNear(panel(result, "main")["box"], [132, 40, 468, 229])
        self.assertIn("left", {p["name"] for p in result["panels"]})

    def test_full_screen_slides_are_not_composite(self):
        result = frame_filter.detect_layout(fullscreen_frames())
        self.assertFalse(result["composite"], result)
        self.assertEqual(result["panels"], [])

    def candidate(self, box, coverage):
        return {"box": box, "coverage": coverage,
                "aspect_error": frame_filter.nearest_aspect(box[2] - box[0], box[3] - box[1])[1]}

    def test_box_borrowing_a_line_inside_the_slide_loses_to_the_framed_slide(self):
        # CppNow chapter-1 sample: the 16:10 box ends at the slide's footer rule.
        found = [self.candidate((531, 0, 1920, 869), 0.55), self.candidate((556, 162, 1900, 917), 1.0),
                 self.candidate((561, 167, 1895, 917), 0.99)]
        self.assertEqual(frame_filter.choose_main(found)["box"], (556, 162, 1900, 917))

    def test_largest_slide_wins_over_better_supported_camera_rectangles(self):
        # NJU GSE L2: blackboard lines inside the camera score higher coverage than the seam.
        found = [self.candidate((546, 0, 1280, 410), 0.65), self.candidate((0, 0, 530, 330), 0.73),
                 self.candidate((0, 0, 537, 338), 0.50)]
        self.assertEqual(frame_filter.choose_main(found)["box"], (546, 0, 1280, 410))
        self.assertIsNone(frame_filter.choose_main([]))

    def test_near_duplicates_merge_into_their_outer_box(self):
        # NJU GSE 20-frame windows: x0 546/550 and x1 1278/1280 are one panel; the inner box clipped glyphs.
        found = [self.candidate((550, 0, 1278, 410), 0.95), self.candidate((546, 0, 1280, 410), 0.65)]
        self.assertEqual(frame_filter.choose_main(found)["box"], (546, 0, 1280, 410))

    def test_layout_shown_in_part_of_the_frames_is_reported_not_dropped(self):
        # 30% full-screen frames in a side-by-side recording: below the consistency gate, still named.
        full = [slide_view(180, 560, i) for i in range(9)]
        result = frame_filter.detect_layout(side_by_side_frames(21) + full)
        self.assertFalse(result["composite"], result)
        self.assertTrue(result["candidates"], result)
        self.assertTrue(any("shows in only" in w for w in result["warnings"]), result["warnings"])

    def test_repeated_picture_is_warned(self):
        frames = [side_by_side_frames(1)[0]] * 30
        self.assertEqual(frame_filter.distinct_pictures(frames), 1)
        result = frame_filter.detect_layout(frames)
        if result["composite"]:
            self.assertTrue(any("distinct pictures" in w for w in result["warnings"]), result["warnings"])

    def test_frame_shows_box_tolerates_an_edge_inside_a_thin_border(self):
        frame = np.full((100, 200), 30, dtype=np.uint8)
        frame[20:80, 40:160] = 240
        frame[18:23, 38:162] = 170   # 5 px grey border along the top
        self.assertTrue(frame_filter.frame_shows_box(frame, (40, 20, 160, 80), 10, 0.3))
        self.assertTrue(frame_filter.frame_shows_box(frame, (40, 22, 160, 80), 10, 0.3))
        self.assertFalse(frame_filter.frame_shows_box(np.full((100, 200), 30, dtype=np.uint8), (40, 20, 160, 80), 10, 0.3))

    def test_warnings_flag_few_frames_and_a_panel_larger_than_main(self):
        # CMU L3 dark frames only: the camera became main and the slides a larger remainder.
        panels = [{"name": "main", "box": [1280, 300, 1920, 660]}, {"name": "left", "box": [24, 134, 1279, 840]}]
        warnings = frame_filter.layout_warnings(panels, 6)
        self.assertTrue(any("only 6 frames" in w for w in warnings), warnings)
        self.assertTrue(any("left is larger than main" in w for w in warnings), warnings)
        self.assertEqual(frame_filter.detect_layout(side_by_side_frames())["warnings"], [])
        repeated = frame_filter.layout_warnings(panels[:1], 30, distinct=1)
        self.assertTrue(any("only 1 distinct pictures among 30 frames" in w for w in repeated), repeated)
        partial = frame_filter.layout_warnings([], 60, partial={"box": (561, 167, 1895, 917), "consistency": 0.65})
        self.assertTrue(any("shows in only 65% of frames" in w for w in partial), partial)

    def test_inset_moves_only_inner_edges(self):
        self.assertEqual(frame_filter.inset_box([240, 0, 560, 180], 560, 180, 3), (243, 0, 560, 180))
        self.assertEqual(frame_filter.inset_box([0, 30, 320, 210], 480, 240, 3), (0, 33, 317, 207))
        with self.assertRaises(ValueError):
            frame_filter.inset_box([10, 10, 14, 14], 100, 100, 3)

    def test_manual_boxes_are_validated(self):
        layout = frame_filter.manual_layout(560, 180, ["main=240,0,560,180", "left=0,0,240,180"])
        self.assertEqual(layout["source"], "manual")
        self.assertTrue(layout["composite"])
        for bad in (["main=240,0,600,180"], ["main=1,2,3"], ["main=0,0,10,10", "main=0,0,20,20"]):
            with self.assertRaises(ValueError):
                frame_filter.manual_layout(560, 180, bad)


class LayoutCliTests(unittest.TestCase):
    def write_frames(self, tmp, frames):
        paths = []
        for index, frame in enumerate(frames):
            path = Path(tmp) / f"f_{index:03d}.png"
            Image.fromarray(frame).save(path)
            paths.append(str(path))
        return paths

    def test_layout_then_crop_main_and_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_frames(tmp, side_by_side_frames())
            layout = Path(tmp) / "layout.json"
            preview = Path(tmp) / "preview.png"
            self.assertEqual(frame_filter.main(["layout", *paths, "--json", str(layout), "--preview", str(preview)]), 0)
            result = json.loads(layout.read_text(encoding="utf-8"))
            self.assertTrue(preview.is_file())
            self.assertEqual(result["unmatched_count"], 0)
            main_box = panel(result, "main")["box"]
            out = Path(tmp) / "main.jpg"
            self.assertEqual(frame_filter.main(["crop", paths[5], "--out", str(out), "--layout", str(layout), "--panel", "main"]), 0)
            with Image.open(out) as image:
                self.assertEqual(image.size, (main_box[2] - main_box[0] - 5, 180))
            left = Path(tmp) / "left.jpg"
            self.assertEqual(frame_filter.main(["crop", paths[5], "--out", str(left), "--layout", str(layout),
                                                "--panel", "left", "--inset", "0"]), 0)
            with Image.open(left) as image:
                self.assertEqual(image.size[1], 180)

    def test_crop_rejects_unknown_panel_and_other_frame_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = Path(tmp) / "layout.json"
            layout.write_text(json.dumps(frame_filter.manual_layout(560, 180, ["main=240,0,560,180"])), encoding="utf-8")
            src = Path(tmp) / "frame.png"
            Image.fromarray(side_by_side_frames(1)[0]).save(src)
            other = Path(tmp) / "other.png"
            Image.fromarray(dark_frame()).save(other)
            out = str(Path(tmp) / "c.jpg")
            self.assertEqual(frame_filter.main(["crop", str(src), "--out", out, "--layout", str(layout), "--panel", "board"]), 2)
            self.assertEqual(frame_filter.main(["crop", str(other), "--out", out, "--layout", str(layout), "--panel", "main"]), 2)
            self.assertEqual(frame_filter.main(["crop", str(src), "--out", out, "--panel", "main"]), 2)
            for content in ("[1, 2, 3]", "null", "{}", '{"width": 560}', "{not json"):
                with self.subTest(content=content):
                    layout.write_text(content, encoding="utf-8")
                    self.assertEqual(frame_filter.main(["crop", str(src), "--out", out, "--layout", str(layout),
                                                        "--panel", "main"]), 2)

    def test_layout_reports_frames_of_another_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_frames(tmp, side_by_side_frames(22))
            for index in range(3):
                path = Path(tmp) / f"other_{index}.png"
                Image.fromarray(dark_frame()).save(path)
                paths.append(str(path))
            layout = Path(tmp) / "layout.json"
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(frame_filter.main(["layout", *paths, "--json", str(layout)]), 0)
            warnings = json.loads(layout.read_text(encoding="utf-8"))["warnings"]
            self.assertTrue(any("3 frames are not 560x180" in w for w in warnings), warnings)

    def test_crop_repeats_layout_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            layout = Path(tmp) / "layout.json"
            data = frame_filter.manual_layout(560, 180, ["main=240,0,560,180"])
            data["warnings"] = ["left is larger than main; confirm on the preview that main holds the slides"]
            layout.write_text(json.dumps(data), encoding="utf-8")
            src = Path(tmp) / "frame.png"
            Image.fromarray(side_by_side_frames(1)[0]).save(src)
            errors = io.StringIO()
            with contextlib.redirect_stderr(errors), contextlib.redirect_stdout(io.StringIO()):
                code = frame_filter.main(["crop", str(src), "--out", str(Path(tmp) / "c.jpg"),
                                          "--layout", str(layout), "--panel", "main"])
            self.assertEqual(code, 0)
            self.assertIn("left is larger than main", errors.getvalue())

    def test_manual_box_cli_records_panels(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.write_frames(tmp, side_by_side_frames(2))
            layout = Path(tmp) / "layout.json"
            code = frame_filter.main(["layout", *paths, "--box", "main=241,0,560,180", "--box", "left=0,0,238,180",
                                      "--json", str(layout)])
            self.assertEqual(code, 0)
            result = json.loads(layout.read_text(encoding="utf-8"))
            self.assertEqual([p["name"] for p in result["panels"]], ["main", "left"])
            self.assertEqual(frame_filter.main(["layout", *paths, "--box", "main=241,0,999,180"]), 2)


if __name__ == "__main__":
    unittest.main()
