"""
Deterministic synthetic lecture video for OCR and frame-filter checks.

Renders frames with Pillow (no ffmpeg drawtext dependency), then encodes them with
ffmpeg. The picture imitates a Bilibili lecture: dark background, a burned-in white
subtitle line near the bottom, a static navigation strip at the
very bottom, a small watermark in the top-right corner, and two content regimes —
side diagrams for the first half, a presenter-like torso in the centre for the second.

Also produces a "Whisper-like" SRT with the homophone errors the OCR glossary must
learn to correct (刻石→刻蚀, 光眼膜→光掩膜).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1280, 720
FPS = 2
NAV_STRIP = 40
SUBTITLE_Y = int(HEIGHT * 0.83)
# 60 px without an outline: RapidOCR read every line exactly with STHeiti, Hiragino, and
# Arial Unicode at this size, while 40 px outlined text produced homophone misreads.
SUBTITLE_FONT_PX = 60

FONT_CANDIDATES = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "C:/Windows/Fonts/msyh.ttc",
)

# (start_second, end_second, subtitle text); gaps have no subtitle.
SUBTITLES = (
    (0, 4, "这种过程就叫刻蚀"),
    (4, 8, "刻蚀技术可以分为两类"),
    (8, 12, "光掩膜上的图形被转移到硅片"),
    (12, 16, "光掩膜非常昂贵"),
    (16, 20, "晶圆厂里的机器"),
)
DURATION = 24
NAV_TEXT = "冶炼硅锭   制造晶圆   光刻工艺   刻蚀   薄膜沉积   CMP"

# Whisper-like transcript with homophone errors at the same times.
WHISPER_LIKE_SRT = """1
00:00:00,000 --> 00:00:03,500
这种过程就叫刻石

2
00:00:04,000 --> 00:00:07,500
刻石技术可以分为两类

3
00:00:08,000 --> 00:00:11,500
光眼膜上的图形被转移到硅片

4
00:00:12,000 --> 00:00:15,500
光眼膜非常昂贵

5
00:00:16,000 --> 00:00:19,500
晶圆厂里的机器
"""


def find_cjk_font() -> str | None:
    env = os.environ.get("LECTURE_TEST_CJK_FONT")
    if env and Path(env).exists():
        return env
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def subtitle_ink_bounds(font_path: str) -> tuple[int, int]:
    """
    Rows actually covered by subtitle ink for this font.

    Fonts place glyph ink differently inside the em box (Noto Sans CJK starts ~10 px
    lower than STHeiti at 60 px), so band assertions compare against measured ink,
    not the nominal draw position.
    """
    font = ImageFont.truetype(font_path, SUBTITLE_FONT_PX)
    image = Image.new("L", (WIDTH, HEIGHT), 0)
    draw = ImageDraw.Draw(image)
    longest = max((text for _, _, text in SUBTITLES), key=len)
    width = draw.textlength(longest, font=font)
    draw.text((int((WIDTH - width) / 2), SUBTITLE_Y), longest, font=font, fill=255)
    import numpy as np
    rows = np.flatnonzero((np.asarray(image) > 128).any(axis=1))
    if rows.size == 0:
        raise RuntimeError("subtitle rendered no ink")
    return int(rows[0]), int(rows[-1]) + 1


def subtitle_at(second: float) -> str:
    for start, end, text in SUBTITLES:
        if start <= second < end:
            return text
    return ""


def is_presenter_segment(second: float) -> bool:
    """Second half of the video shows a presenter-like torso instead of diagrams."""
    return second >= DURATION / 2


def render_frame(second: float, font_path: str) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), (12, 12, 14))
    draw = ImageDraw.Draw(image)
    if is_presenter_segment(second):
        # Torso: bright vertical block in the centre running off the bottom edge.
        draw.rectangle([int(WIDTH * 0.42), int(HEIGHT * 0.25), int(WIDTH * 0.58), HEIGHT], fill=(170, 150, 140))
        draw.ellipse([int(WIDTH * 0.45), int(HEIGHT * 0.10), int(WIDTH * 0.55), int(HEIGHT * 0.30)], fill=(190, 170, 160))
    else:
        # Diagrams: bright panels left and right with a few dark "lines".
        for x0, x1 in ((0.05, 0.30), (0.70, 0.95)):
            box = [int(WIDTH * x0), int(HEIGHT * 0.15), int(WIDTH * x1), int(HEIGHT * 0.60)]
            draw.rectangle(box, fill=(225, 225, 230))
            for k in range(4):
                y = box[1] + 30 + k * 60
                draw.line([box[0] + 20, y, box[2] - 20, y], fill=(40, 40, 60), width=6)
    # Navigation strip: static colour and static text.
    draw.rectangle([0, HEIGHT - NAV_STRIP, WIDTH, HEIGHT], fill=(58, 60, 92))
    nav_font = ImageFont.truetype(font_path, 22)
    draw.text((30, HEIGHT - NAV_STRIP + 8), NAV_TEXT, font=nav_font, fill=(215, 215, 225))
    # Watermark.
    draw.text((WIDTH - 150, 18), "bilibili", font=ImageFont.truetype(font_path, 24), fill=(160, 160, 170))
    # Burned-in subtitle: white, centred.
    text = subtitle_at(second)
    if text:
        font = ImageFont.truetype(font_path, SUBTITLE_FONT_PX)
        width = draw.textlength(text, font=font)
        x = int((WIDTH - width) / 2)
        draw.text((x, SUBTITLE_Y), text, font=font, fill=(255, 255, 255))
    return image


def render_frames(out_dir: Path, font_path: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(DURATION * FPS):
        second = index / FPS
        path = out_dir / f"{index:05d}.png"
        render_frame(second, font_path).save(path)
        paths.append(path)
    return paths


def encode(frames_dir: Path, out_mp4: Path, ffmpeg: str = "ffmpeg") -> Path:
    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(FPS),
            "-i", str(frames_dir / "%05d.png"), "-pix_fmt", "yuv420p"]
    errors = []
    for codec in ("libx264", "mpeg4"):
        completed = subprocess.run(base + ["-c:v", codec, str(out_mp4)], capture_output=True, text=True)
        if completed.returncode == 0 and out_mp4.exists():
            return out_mp4
        errors.append(f"{codec}: {completed.stderr[-300:]}")
    raise RuntimeError("ffmpeg could not encode the synthetic video: " + " | ".join(errors))


def build(workdir: Path) -> dict:
    """Render, encode, and write the Whisper-like SRT. Returns paths."""
    font = find_cjk_font()
    if font is None:
        raise RuntimeError("no CJK font found; set LECTURE_TEST_CJK_FONT")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not on PATH")
    frames = render_frames(workdir / "frames", font)
    video = encode(workdir / "frames", workdir / "synthetic.mp4")
    srt = workdir / "whisper_like.srt"
    srt.write_text(WHISPER_LIKE_SRT, encoding="utf-8")
    return {"video": video, "frames": frames, "whisper_srt": srt, "font": font}
