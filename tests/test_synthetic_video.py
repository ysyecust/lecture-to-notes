"""
End-to-end checks of the OCR and frame-filter helpers on a synthetic lecture video.

Skipped unless ffmpeg, ffprobe, a CJK font, Pillow/numpy, and rapidocr-onnxruntime are
available; the `synthetic-video` CI job installs all of them.
"""
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    import numpy  # noqa: F401
    from PIL import Image  # noqa: F401
except ImportError as error:  # pragma: no cover - environment dependent
    raise unittest.SkipTest(f"synthetic video tests need Pillow and numpy: {error}")

import synthetic_video

HAS_OCR = importlib.util.find_spec("rapidocr_onnxruntime") is not None
HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
FONT = synthetic_video.find_cjk_font()


def run_cli(module, argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = module.main(argv)
    return code, out.getvalue()


@unittest.skipUnless(HAS_FFMPEG and FONT, "needs ffmpeg/ffprobe and a CJK font")
class SyntheticVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.workdir = Path(cls.tmp.name)
        cls.assets = synthetic_video.build(cls.workdir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_video_and_frames_exist(self):
        self.assertTrue(self.assets["video"].stat().st_size > 10_000)
        self.assertEqual(len(self.assets["frames"]), synthetic_video.DURATION * synthetic_video.FPS)

    def test_frame_filter_bands_from_rendered_frames(self):
        import frame_filter
        frames = [frame_filter.load_gray(str(p)) for p in self.assets["frames"][::2]]
        bands = frame_filter.detect_bands(frames)
        self.assertGreaterEqual(bands["nav_strip"], synthetic_video.NAV_STRIP - 12, bands)
        self.assertLessEqual(bands["nav_strip"], synthetic_video.NAV_STRIP + 12, bands)
        self.assertIsNotNone(bands["subtitle_band"], bands)
        y0, y1 = bands["subtitle_band"]
        self.assertLessEqual(y0, synthetic_video.SUBTITLE_Y + 4, bands)
        self.assertGreaterEqual(y1, synthetic_video.SUBTITLE_Y + 30, bands)

    def test_frame_filter_scores_separate_diagram_and_presenter(self):
        import frame_filter
        diagram = frame_filter.load_gray(str(self.assets["frames"][10]))    # t = 5 s
        presenter = frame_filter.load_gray(str(self.assets["frames"][36]))  # t = 18 s
        self.assertFalse(frame_filter.classify(frame_filter.score_frame(diagram)))
        self.assertTrue(frame_filter.classify(frame_filter.score_frame(presenter)))

    @unittest.skipUnless(HAS_OCR, "needs rapidocr-onnxruntime")
    def test_detect_reports_hardsubs_and_geometry(self):
        import ocr_hardsubs
        bands = self.workdir / "bands.json"
        code, out = run_cli(ocr_hardsubs, ["detect", str(self.assets["video"]), "--samples", "8", "--geometry", str(bands)])
        self.assertEqual(code, 0, out)
        verdict = json.loads(out.strip().splitlines()[-1])
        self.assertTrue(verdict["has_hardsubs"], verdict)
        geometry = json.loads(bands.read_text(encoding="utf-8"))
        self.assertGreaterEqual(geometry["nav_strip"], synthetic_video.NAV_STRIP - 12, geometry)
        self.assertIsNotNone(geometry["subtitle_band"], geometry)
        y0, y1 = geometry["subtitle_band"]
        self.assertLessEqual(y0, synthetic_video.SUBTITLE_Y + 4, geometry)
        self.assertGreaterEqual(y1, synthetic_video.SUBTITLE_Y + 30, geometry)
        self.assertGreaterEqual(geometry["crop_bottom"], synthetic_video.HEIGHT - synthetic_video.SUBTITLE_Y - 4, geometry)

    @unittest.skipUnless(HAS_OCR, "needs rapidocr-onnxruntime")
    def test_extract_then_glossary_learns_homophone_fixes(self):
        import ocr_hardsubs
        srt = self.workdir / "hardsub_ocr.srt"
        code, out = run_cli(ocr_hardsubs, ["extract", str(self.assets["video"]), "--out", str(srt), "--fps", "1"])
        self.assertEqual(code, 0, out)
        entries = ocr_hardsubs.parse_srt(srt.read_text(encoding="utf-8"))
        joined = "".join(e["text"] for e in entries)
        self.assertGreaterEqual(len(entries), 4, entries)
        self.assertIn("刻蚀", joined)
        self.assertIn("光掩膜", joined)
        for line in ("冶炼硅锭", "bilibili"):
            self.assertNotIn(line, joined, "navigation strip / watermark text must not leak into the subtitle track")

        glossary_path = self.workdir / "glossary_auto.json"
        code, out = run_cli(ocr_hardsubs, ["glossary", str(srt), str(self.assets["whisper_srt"]), "--out", str(glossary_path), "--min-count", "2"])
        self.assertEqual(code, 0, out)
        glossary = json.loads(glossary_path.read_text(encoding="utf-8"))
        self.assertEqual(glossary.get("石"), "蚀", glossary)
        self.assertEqual(glossary.get("眼"), "掩", glossary)


if __name__ == "__main__":
    unittest.main()
