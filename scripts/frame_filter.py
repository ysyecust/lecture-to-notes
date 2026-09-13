#!/usr/bin/env python3
"""
Frame hygiene: overlay bands, composite panel layouts, crops, and talking-head scores.

Slide content is never cropped by guessing which region matters. This tool only removes
geometry measured from the video itself: persistent overlays (a burned-in subtitle band,
a static navigation strip) and the panel layout of composite recordings, where a camera
feed and a screen capture share one picture. It also flags frames whose only content is
the presenter, so a text-only model can reject them without seeing the picture.

Subcommands:
    bands  FRAME... [--json out.json]
        Sample frames from one video and locate the static navigation strip at the
        bottom and the burned-in subtitle band above it. Prints JSON:
        {"height": H, "nav_strip": px, "subtitle_band": [y0, y1] | null, "crop_bottom": px}
    layout FRAME... [--json layout.json] [--preview layout.png] [--box NAME=X0,Y0,X1,Y1 ...]
        Measure the panel layout of one video. `main` is the largest screen-shaped
        rectangle (16:9, 16:10, or 4:3) whose inner sides are persistent straight edges;
        what remains beside it becomes `left`/`right`/`top`/`bottom` after black letterbox
        rows and columns are trimmed. `composite` is true when figures must be cropped to
        one panel. `--box` records panels measured by eye instead of detecting them, and
        `--preview` draws the panels and a pixel ruler on the middle frame. Prints JSON:
        {"width": W, "height": H, "composite": bool, "panels": [{"name", "box"}, ...],
         "consistency": share of frames showing the main panel's edges, ...}
    crop   IMAGE --out OUT [--bands bands.json | --bottom PX] [--top PX]
           [--layout layout.json --panel NAME [--inset PX]]
        Remove `crop_bottom` rows (from `bands`) or explicit pixel margins, and keep one
        panel of a composite frame, moved `--inset` pixels inside every edge that is not
        the frame border so the blurred seam stays out of the figure.
    score  FRAME... [--json out.json] [--info-threshold 0.06] [--edge-threshold 0.02]
        Per-frame information score outside the presenter column, subtitle band, and
        logo corner; `talking_head` is true when both scores fall under the thresholds.

Requires Pillow and numpy, plus verify_notes.py beside this file for the layout.json
schema (install_skill.sh copies both).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont
except ImportError as error:  # pragma: no cover - environment dependent
    raise SystemExit("frame_filter.py needs Pillow and numpy: pip install Pillow numpy") from error

# Sibling stdlib-only script: `crop` and the delivery gate read layout.json with one schema.
from verify_notes import layout_problem


def load_gray(path: str) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


def sample_paths(paths: list[str], limit: int) -> list[str]:
    if len(paths) <= limit:
        return paths
    step = len(paths) / limit
    return [paths[int(i * step)] for i in range(limit)]


# ---------------------------------------------------------------- bands
def detect_bands(
    frames: list[np.ndarray],
    bottom_frac: float = 0.30,
    static_ratio: float = 0.6,
    spatial_std: float = 12.0,
    white_level: int = 225,
    white_pixel_share: float = 0.003,
    white_frame_share: float = 0.35,
) -> dict:
    """
    Locate a static navigation strip and a burned-in subtitle band from sampled frames.

    Navigation strip: bottom rows whose temporal variation is far below the rest of
    the lower picture (< `static_ratio` × median) yet carry spatial structure, so a
    plain black background is not mistaken for one. Subtitle band: rows in the bottom
    `bottom_frac` where at least `white_frame_share` of frames contain near-white
    strokes (subtitles are rendered white with a dark outline on every platform).

    Calibrated on a 1080p Bilibili lecture: navigation rows scored 0.35–0.39 of the
    median temporal std, subtitle rows 0.43–0.95 white-frame share, other rows ≤ 0.21.
    """
    stack = np.stack([f.astype(np.int16) for f in frames])  # (N, H, W)
    n, height, width = stack.shape
    temporal_std = stack.std(axis=0).mean(axis=1)              # (H,)
    spatial = stack.std(axis=2).mean(axis=0)                   # (H,)
    lower_limit = int(height * (1 - bottom_frac))
    baseline = float(np.median(temporal_std[lower_limit:]))
    static_rows = temporal_std < max(static_ratio * baseline, 1.0)

    # Navigation strip: the maximal run of static rows ending at the bottom edge,
    # trimmed to its topmost row that carries spatial structure (icons, text). A
    # plain static bottom (black letterbox) has no structured row and yields 0.
    nav = 0
    y = height - 1
    while y >= 0 and static_rows[y]:
        y -= 1
    run_top = y + 1
    structured = np.flatnonzero(spatial[run_top:height] > spatial_std)
    if structured.size:
        nav_top = max(run_top, run_top + int(structured[0]) - 4)
        nav = height - nav_top
    if nav < 4:
        nav = 0

    # Subtitle band: rows where many frames carry near-white strokes.
    white = (stack > white_level).mean(axis=2)                          # (N, H)
    text_rows = (white > white_pixel_share).mean(axis=0) >= white_frame_share  # (H,)
    candidate = np.zeros(height, dtype=bool)
    candidate[lower_limit:height - nav] = text_rows[lower_limit:height - nav]
    band = None
    ys = np.flatnonzero(candidate)
    if ys.size:
        # Take the lowest contiguous run (subtitles sit right above the nav strip).
        runs = np.split(ys, np.flatnonzero(np.diff(ys) > 2) + 1)
        run = runs[-1]
        if run.size >= 6:
            pad = max(2, run.size // 6)
            band = [int(max(lower_limit, run[0] - pad)), int(min(height - nav, run[-1] + pad + 1))]
    crop_bottom = height - band[0] if band else nav
    return {"height": int(height), "width": int(width), "nav_strip": int(nav),
            "subtitle_band": band, "crop_bottom": int(crop_bottom), "frames": int(n)}


# ---------------------------------------------------------------- layout
SCREEN_ASPECTS = {"16:9": 16 / 9, "16:10": 16 / 10, "4:3": 4 / 3}


def box_area(box) -> int:
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def box_intersection(a, b) -> tuple:
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def box_iou(a, b) -> float:
    inter = box_area(box_intersection(a, b))
    union = box_area(a) + box_area(b) - inter
    return inter / union if union else 0.0


def nearest_aspect(width: int, height: int) -> tuple[str, float]:
    ratio = width / height
    name, target = min(SCREEN_ASPECTS.items(), key=lambda item: abs(ratio / item[1] - 1))
    return name, abs(ratio / target - 1)


def longest_runs(mask: np.ndarray) -> np.ndarray:
    """Length of the longest run of True down each column of a 2-D boolean array."""
    best = np.zeros(mask.shape[1], dtype=np.int32)
    run = np.zeros(mask.shape[1], dtype=np.int32)
    for row in mask:
        run = np.where(row, run + 1, 0)
        np.maximum(best, run, out=best)
    return best


def line_candidates(runs: np.ndarray, length: int, min_run: float, limit: int) -> list[int]:
    """
    Boundaries whose persistent edge run is locally the longest.

    `runs[i]` describes the edge between pixel i and i + 1, reported as boundary i + 1.
    """
    picked: list[int] = []
    for index in np.argsort(-runs, kind="stable"):
        if runs[index] < min_run * length or len(picked) >= limit:
            break
        if all(abs(int(index) - other) > 2 for other in picked):
            picked.append(int(index))
    return sorted(index + 1 for index in picked)


def trim_letterbox(box, mean: np.ndarray, tstd: np.ndarray, dark: float = 40.0, flat: float = 6.0) -> tuple:
    """Shrink a box past edge rows and columns that are dark, uniform, and static."""
    x0, y0, x1, y1 = box

    def letterbox(values: np.ndarray, spread: np.ndarray) -> bool:
        return values.mean() < dark and values.std() < flat and spread.mean() < flat

    while x0 < x1 and y0 < y1:
        if letterbox(mean[y0, x0:x1], tstd[y0, x0:x1]):
            y0 += 1
        elif letterbox(mean[y1 - 1, x0:x1], tstd[y1 - 1, x0:x1]):
            y1 -= 1
        elif letterbox(mean[y0:y1, x0], tstd[y0:y1, x0]):
            x0 += 1
        elif letterbox(mean[y0:y1, x1 - 1], tstd[y0:y1, x1 - 1]):
            x1 -= 1
        else:
            break
    return x0, y0, x1, y1


MIN_LAYOUT_FRAMES = 20
MIN_DISTINCT_PICTURES = 5


def near_duplicate(a, b, slack: int = 8) -> bool:
    """Two boxes whose every side lies within `slack` px: one panel measured on either side of a seam or border."""
    return all(abs(p - q) <= slack for p, q in zip(a, b))


def choose_main(found: list[dict], overlap: float = 0.5, margin: float = 0.2) -> dict | None:
    """
    Pick the main panel among screen-shaped candidates.

    Candidates that share at least `overlap` of the smaller one without being near-duplicates
    describe the region differently, and the one whose edges have `margin` more coverage wins:
    the other borrows a line from inside a picture. On a 20-frame CppNow sample, a 16:10 box
    ending at the slide's footer rule (coverage 0.55) otherwise beat the framed slide (1.00)
    by area and cut the footer off. Of the rest the largest is the main panel, and it takes
    the outer box of its near-duplicates; the crop inset then removes the seam or border.
    An inner box clipped text set flush against the slide edge (NJU GSE L2: glyphs from
    column 551 beside a seam blurred over columns 544–549).
    """
    kept = []
    for candidate in found:
        area = box_area(candidate["box"])
        dominated = any(
            other["coverage"] >= candidate["coverage"] + margin
            and box_area(box_intersection(candidate["box"], other["box"])) >= overlap * min(area, box_area(other["box"]))
            and not near_duplicate(candidate["box"], other["box"])
            for other in found if other is not candidate)
        if not dominated:
            kept.append(candidate)
    if not kept:
        return None
    largest = max(kept, key=lambda c: box_area(c["box"]))
    group = [c["box"] for c in kept if near_duplicate(c["box"], largest["box"])]
    outer = (min(b[0] for b in group), min(b[1] for b in group), max(b[2] for b in group), max(b[3] for b in group))
    return {**largest, "box": outer}


def distinct_pictures(frames: list[np.ndarray], delta: float = 2.0) -> int:
    """Count frames that differ from the previous one by more than `delta` mean grey level (8× subsampled)."""
    small = [frame[::8, ::8].astype(np.int16) for frame in frames]
    return 1 + sum(float(np.abs(b - a).mean()) > delta for a, b in zip(small, small[1:]))


def frame_shows_box(frame: np.ndarray, box, edge_delta: int, presence: float, tolerance: int = 2) -> bool:
    """True when each inner side of `box` is an edge along `presence` of its length in this frame, within `tolerance` px."""
    height, width = frame.shape
    x0, y0, x1, y1 = box
    profiles = []
    for x in (x0, x1):
        if 0 < x < width:
            band = frame[y0:y1, max(0, x - 1 - tolerance):min(width, x + 1 + tolerance)].astype(np.int16)
            profiles.append(np.abs(np.diff(band, axis=1)).max(axis=1))
    for y in (y0, y1):
        if 0 < y < height:
            band = frame[max(0, y - 1 - tolerance):min(height, y + 1 + tolerance), x0:x1].astype(np.int16)
            profiles.append(np.abs(np.diff(band, axis=0)).max(axis=0))
    return all((profile > edge_delta).mean() >= presence for profile in profiles)


def layout_warnings(panels: list[dict], count: int, distinct: int | None = None,
                    partial: dict | None = None) -> list[str]:
    """Conditions under which a measured layout must be checked on the preview by eye."""
    warnings = []
    if count < MIN_LAYOUT_FRAMES:
        warnings.append(f"only {count} frames sampled; fewer than {MIN_LAYOUT_FRAMES} give panel edges little evidence")
    # False composites built from one repeated slide or shot held 1 distinct picture; real
    # composite windows of 20 frames held 8–17, except two static CMU stretches with 2–3.
    elif panels and distinct is not None and distinct < MIN_DISTINCT_PICTURES:
        warnings.append(f"only {distinct} distinct pictures among {count} frames; lines inside one slide or shot "
                        "can pass for panel edges")
    if panels:
        larger = [p["name"] for p in panels[1:] if box_area(p["box"]) > box_area(panels[0]["box"])]
        if larger:
            warnings.append(f"{', '.join(larger)} is larger than main; confirm on the preview that main holds the slides")
    elif partial:
        warnings.append(f"panel {list(partial['box'])} shows in only {partial['consistency']:.0%} of frames; if the "
                        "video switches between side-by-side and full-screen, check the preview and record panels with --box")
    return warnings


def detect_layout(
    frames: list[np.ndarray],
    edge_delta: int = 10,
    persist: float = 0.5,
    min_coverage: float = 0.5,
    aspect_tolerance: float = 0.01,
    min_side: float = 0.25,
    full_share: float = 0.9,
    min_strip_share: float = 0.08,
    side_presence: float = 0.3,
    min_consistency: float = 0.8,
    partial_share: float = 0.3,
    limit: int = 16,
) -> dict:
    """
    Measure the panel layout of a composite recording from sampled frames.

    A panel side is a line whose pixels differ from their neighbours by more than
    `edge_delta` in at least `persist` of the frames. A candidate rectangle needs each
    side that is not the frame border to be such a line along `min_coverage` of its
    length and, after letterbox trimming, a screen aspect within `aspect_tolerance`.
    A static camera also produces persistent lines (a blackboard frame, a chalk tray),
    so the main panel is the largest candidate, not the one with the strongest edges.

    Calibrated 2026-09-13 on sampled frames of four composites and three full-screen
    lectures. NJU GSE 2026 L2 (1280×410): slides 734×410 on the right, the seam blurred
    over columns 544–549, camera sub-rectangles reached 34% of the frame against 57%
    for the slides. CMU 11-768 L3 (1920×960): slides 1280×720 at y=120 and camera
    640×360 at the right, exact. A CppNow talk (1920×1080): slides 1334×750 beside a
    speaker sidebar; here the whole 16:9 frame is itself a candidate, hence
    `full_share`. Stanford CS336 L2–L4 full-screen video: every candidate covered ≥ 99%
    of the frame, so they stay non-composite. Coverage is measured after letterbox
    trimming; measured before it, a CppNow box ending where dark rows stop matched
    16:10 by chance while no frame showed an edge there. A candidate must also show its
    inner sides in `min_consistency` of the single frames, within 2 px: on 20-frame
    windows of the full-screen CS336 L4 lecture, boxes assembled from camera texture
    scored 0.0–0.65 and were reported as composites in 4 of 33 windows without this
    check, while the real seams above scored 0.9–1.0.

    Limits: a layout present in fewer than `persist` of the frames leaves no persistent
    line and is not detected (a CppNow/CS336 half-and-half mix came back non-composite
    without a warning), and a dark slide on a black letterbox hides its edge, so on six
    such CMU frames the camera became `main` (warned).
    """
    count = len(frames)
    height, width = frames[0].shape
    vertical = np.zeros((height, width - 1), dtype=np.float32)
    horizontal = np.zeros((height - 1, width), dtype=np.float32)
    total = np.zeros((height, width), dtype=np.float64)
    squares = np.zeros((height, width), dtype=np.float64)
    for frame in frames:
        pixels = frame.astype(np.int16)
        vertical += np.abs(np.diff(pixels, axis=1)) > edge_delta
        horizontal += np.abs(np.diff(pixels, axis=0)) > edge_delta
        total += pixels
        squares += pixels.astype(np.float64) ** 2
    edge_v = vertical / count >= persist
    edge_h = horizontal / count >= persist
    mean = total / count
    tstd = np.sqrt(np.maximum(squares / count - mean ** 2, 0.0))
    cum_v = np.vstack([np.zeros((1, width - 1)), np.cumsum(edge_v, axis=0)])
    cum_h = np.hstack([np.zeros((height - 1, 1)), np.cumsum(edge_h, axis=1)])

    def coverage(x0: int, y0: int, x1: int, y1: int) -> float:
        sides = []
        if x0 > 0:
            sides.append((cum_v[y1, x0 - 1] - cum_v[y0, x0 - 1]) / (y1 - y0))
        if x1 < width:
            sides.append((cum_v[y1, x1 - 1] - cum_v[y0, x1 - 1]) / (y1 - y0))
        if y0 > 0:
            sides.append((cum_h[y0 - 1, x1] - cum_h[y0 - 1, x0]) / (x1 - x0))
        if y1 < height:
            sides.append((cum_h[y1 - 1, x1] - cum_h[y1 - 1, x0]) / (x1 - x0))
        return float(min(sides)) if sides else 1.0

    xs = [0, *line_candidates(longest_runs(edge_v), height, min_side, limit), width]
    ys = [0, *line_candidates(longest_runs(edge_h.T), width, min_side, limit), height]
    found, partial, seen = [], [], set()
    for i, x0 in enumerate(xs):
        for x1 in xs[i + 1:]:
            if x1 - x0 < min_side * width:
                continue
            for j, y0 in enumerate(ys):
                for y1 in ys[j + 1:]:
                    if y1 - y0 < min_side * height:
                        continue
                    box = trim_letterbox((x0, y0, x1, y1), mean, tstd)
                    if box in seen or box[2] - box[0] < min_side * width or box[3] - box[1] < min_side * height:
                        continue
                    seen.add(box)
                    aspect, error = nearest_aspect(box[2] - box[0], box[3] - box[1])
                    if error > aspect_tolerance:
                        continue
                    # Measure the sides after trimming: where a letterbox ends must itself be an edge.
                    cover = coverage(*box)
                    if cover < min_coverage or box_area(box) >= full_share * width * height:
                        continue
                    # Persistence adds evidence up across frames; a real seam also shows in
                    # nearly every single frame, while lines assembled from a moving person or
                    # camera texture do not.
                    shown = [frame_shows_box(frame, box, edge_delta, side_presence) for frame in frames]
                    record = {"box": box, "aspect": aspect, "aspect_error": error, "coverage": cover,
                              "consistency": sum(shown) / count}
                    (found if sum(shown) >= min_consistency * count else partial).append(record)

    result = {"width": int(width), "height": int(height), "frames": int(count), "source": "detected",
              "composite": False, "panels": [], "consistency": None, "unmatched": [], "candidates": [],
              "warnings": layout_warnings([], count)}
    # Candidates covering nearly the whole picture were skipped above: that is the picture
    # itself (full-screen slides, or a 16:9 frame whose own border matches the prior).
    main = choose_main(found)
    if main is None:
        # A layout that shows in part of the frames (a recording that switches to full-screen
        # slides for a while) is reported, never silently dropped.
        weak = [c for c in partial if c["consistency"] >= partial_share]
        ranked = sorted(weak, key=lambda c: (-round(c["consistency"], 2), -c["coverage"], -box_area(c["box"])))
        result["candidates"] = [{"box": list(c["box"]), "consistency": round(c["consistency"], 3)} for c in ranked[:3]]
        result["warnings"] = layout_warnings([], count, partial=choose_main(weak))
        return result
    x0, y0, x1, y1 = main["box"]
    aspect, error = nearest_aspect(x1 - x0, y1 - y0)
    panels = [{"name": "main", "box": [x0, y0, x1, y1], "aspect": aspect,
               "aspect_error": round(error, 4), "coverage": round(main["coverage"], 3)}]
    regions = {"left": (0, 0, x0, height), "right": (x1, 0, width, height),
               "top": (x0, 0, x1, y0), "bottom": (x0, y1, x1, height)}
    for name, region in regions.items():
        if box_area(region) == 0:
            continue
        box = trim_letterbox(region, mean, tstd)
        if box_area(box) >= min_strip_share * width * height:
            panels.append({"name": name, "box": [int(v) for v in box]})
    # Frames that do not show the main panel's edges (full-screen demos, transitions, a
    # dark slide on a black letterbox) are listed so the writer checks their figures by eye.
    unmatched = [i for i, frame in enumerate(frames) if not frame_shows_box(frame, main["box"], edge_delta, side_presence)]
    result.update(composite=True, panels=panels, unmatched=unmatched, consistency=round(1 - len(unmatched) / count, 3),
                  warnings=layout_warnings(panels, count, distinct_pictures(frames)))
    return result


def manual_layout(width: int, height: int, specs: list[str]) -> dict:
    """Panels measured by eye: each spec is NAME=X0,Y0,X1,Y1 in frame pixels."""
    panels = []
    for spec in specs:
        name, _, coords = spec.partition("=")
        try:
            values = [int(v) for v in coords.split(",")]
        except ValueError:
            values = []
        if not name or len(values) != 4:
            raise ValueError(f"--box expects NAME=X0,Y0,X1,Y1, got {spec!r}")
        x0, y0, x1, y1 = values
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            raise ValueError(f"--box {spec!r} lies outside the {width}x{height} frame")
        panels.append({"name": name, "box": values})
    names = [panel["name"] for panel in panels]
    if len(set(names)) != len(names):
        raise ValueError("--box names must be unique")
    return {"width": width, "height": height, "frames": 0, "source": "manual", "composite": True,
            "panels": panels, "consistency": None, "unmatched": [], "warnings": []}


def inset_box(box, width: int, height: int, inset: int) -> tuple[int, int, int, int]:
    """Move every side that is not the frame border `inset` pixels inward."""
    x0, y0, x1, y1 = box
    x0 = x0 + inset if x0 > 0 else x0
    y0 = y0 + inset if y0 > 0 else y0
    x1 = x1 - inset if x1 < width else x1
    y1 = y1 - inset if y1 < height else y1
    if x1 <= x0 or y1 <= y0:
        raise ValueError(f"inset {inset} leaves nothing of panel {list(box)}")
    return x0, y0, x1, y1


PANEL_COLORS = ((230, 57, 70), (29, 120, 220), (42, 157, 80), (240, 160, 20), (150, 60, 200))


def draw_preview(path: str, layout: dict, out: str) -> None:
    """Draw a pixel ruler and every panel with its name and box on one frame."""
    with Image.open(path) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    width, height = canvas.size

    def label(xy, text, color):
        left, top, right, bottom = draw.textbbox(xy, text, font=font)
        draw.rectangle([left - 2, top - 2, right + 2, bottom + 2], fill=(0, 0, 0))
        draw.text(xy, text, fill=color, font=font)

    for x in range(0, width, 50):
        draw.line([(x, 0), (x, 12 if x % 100 == 0 else 6)], fill=(255, 255, 0), width=2)
        if x % 100 == 0 and x:
            label((x + 3, 14), str(x), (255, 255, 0))
    for y in range(0, height, 50):
        draw.line([(0, y), (12 if y % 100 == 0 else 6, y)], fill=(255, 255, 0), width=2)
        if y % 100 == 0 and y:
            label((14, y + 3), str(y), (255, 255, 0))
    for index, panel in enumerate(layout.get("panels", [])):
        color = PANEL_COLORS[index % len(PANEL_COLORS)]
        x0, y0, x1, y1 = panel["box"]
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=color, width=3)
        label((x0 + 8, y0 + 30), f"{panel['name']} [{x0},{y0},{x1},{y1}]", color)
    for candidate in layout.get("candidates", []):
        x0, y0, x1, y1 = candidate["box"]
        draw.rectangle([x0, y0, x1 - 1, y1 - 1], outline=(200, 200, 200), width=2)
        label((x0 + 8, y1 - 24), f"candidate {candidate['consistency']:.0%} [{x0},{y0},{x1},{y1}]", (220, 220, 220))
    canvas.save(out)


# ---------------------------------------------------------------- crop
def crop_image(path: str, out: str, top: int = 0, bottom: int = 0, box=None) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        x0, y0, x1, y1 = box if box else (0, 0, width, height)
        y0 = max(y0, top, 0)
        y1 = max(y0 + 1, min(y1, height - max(0, bottom)))
        cropped = image.crop((x0, y0, x1, y1))
        cropped.save(out, quality=92)
        return cropped.size


# ---------------------------------------------------------------- score
def score_frame(
    gray: np.ndarray,
    center: tuple[float, float] = (0.35, 0.65),
    bottom_frac: float = 0.15,
    logo: tuple[float, float] = (0.12, 0.12),
    bright: int = 60,
    edge_delta: int = 30,
) -> dict:
    """
    Measure how much non-presenter content a frame carries.

    `info` is the share of bright pixels outside the presenter column, subtitle band,
    and top-right logo corner; `edge` is the share of strong horizontal gradients in
    the same region. A dark frame with only a person in the middle scores near zero on
    both; slides, diagrams, and photographs score well above.
    """
    height, width = gray.shape
    mask = np.ones_like(gray, dtype=bool)
    mask[:, int(width * center[0]):int(width * center[1])] = False
    mask[int(height * (1 - bottom_frac)):, :] = False
    mask[: int(height * logo[1]), int(width * (1 - logo[0])):] = False
    region = gray[mask]
    info = float((region > bright).mean()) if region.size else 0.0
    grad = np.abs(np.diff(gray.astype(np.int16), axis=1)) > edge_delta
    edge_region = grad[mask[:, 1:]]
    edge = float(edge_region.mean()) if edge_region.size else 0.0
    # A presenter's torso runs off the bottom of the picture; a centered diagram
    # (a lens, a chamber) usually does not. Measure the centre columns just above
    # the subtitle band.
    torso = gray[int(height * (1 - bottom_frac - 0.20)): int(height * (1 - bottom_frac)),
                 int(width * center[0]): int(width * center[1])]
    center_bottom = float((torso > bright).mean()) if torso.size else 0.0
    return {"info": round(info, 4), "edge": round(edge, 4), "center_bottom": round(center_bottom, 4),
            "bright_total": round(float((gray > bright).mean()), 4)}


def classify(scores: dict, info_threshold: float = 0.06, edge_threshold: float = 0.02,
             torso_threshold: float = 0.10) -> bool:
    """True when the frame is dark outside the centre and a body fills the centre-bottom."""
    return (scores["info"] < info_threshold and scores["edge"] < edge_threshold
            and scores.get("center_bottom", 1.0) > torso_threshold)


# ---------------------------------------------------------------- CLI
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_bands = sub.add_parser("bands")
    p_bands.add_argument("frames", nargs="+")
    p_bands.add_argument("--json", default=None)
    p_bands.add_argument("--max-frames", type=int, default=60)

    p_layout = sub.add_parser("layout")
    p_layout.add_argument("frames", nargs="+")
    p_layout.add_argument("--json", default=None)
    p_layout.add_argument("--max-frames", type=int, default=60)
    p_layout.add_argument("--preview", default=None, help="PNG with the panels and a pixel ruler drawn on the middle frame")
    p_layout.add_argument("--box", action="append", default=[], metavar="NAME=X0,Y0,X1,Y1",
                          help="record a panel measured by eye instead of detecting the layout (repeatable)")

    p_crop = sub.add_parser("crop")
    p_crop.add_argument("image")
    p_crop.add_argument("--out", required=True)
    p_crop.add_argument("--bands", default=None, help="bands.json from the `bands` subcommand")
    p_crop.add_argument("--top", type=int, default=0)
    p_crop.add_argument("--bottom", type=int, default=0)
    p_crop.add_argument("--layout", default=None, help="layout.json from the `layout` subcommand")
    p_crop.add_argument("--panel", default=None, help="panel name from layout.json, e.g. main or left")
    p_crop.add_argument("--inset", type=int, default=5, help="pixels to move inside every non-border panel edge")

    p_score = sub.add_parser("score")
    p_score.add_argument("frames", nargs="+")
    p_score.add_argument("--json", default=None)
    p_score.add_argument("--info-threshold", type=float, default=0.06)
    p_score.add_argument("--edge-threshold", type=float, default=0.02)
    p_score.add_argument("--bottom-frac", type=float, default=0.15)

    args = parser.parse_args(argv)

    if args.command == "bands":
        paths = sample_paths(args.frames, args.max_frames)
        frames = [load_gray(p) for p in paths]
        shape = frames[0].shape
        frames = [f for f in frames if f.shape == shape]
        result = detect_bands(frames)
        text = json.dumps(result)
        print(text)
        if args.json:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
        return 0

    if args.command == "layout":
        paths = sample_paths(args.frames, args.max_frames)
        frames = [load_gray(p) for p in paths]
        shape = Counter(f.shape for f in frames).most_common(1)[0][0]
        kept = [(p, f) for p, f in zip(paths, frames) if f.shape == shape]
        try:
            if args.box:
                result = manual_layout(shape[1], shape[0], args.box)
            else:
                result = detect_layout([f for _, f in kept])
        except ValueError as error:
            print(f"layout: {error}", file=sys.stderr)
            return 2
        if len(kept) < len(frames):
            result["warnings"].append(f"{len(frames) - len(kept)} frames are not {shape[1]}x{shape[0]} and were "
                                      "skipped; measure each resolution separately")
        unmatched = [kept[i][0] for i in result.pop("unmatched")]
        result["unmatched_frames"] = unmatched[:20]
        result["unmatched_count"] = len(unmatched)
        text = json.dumps(result)
        print(text)
        for warning in result["warnings"]:
            print(f"layout: warning: {warning}", file=sys.stderr)
        if args.json:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
        if args.preview:
            draw_preview(kept[len(kept) // 2][0], result, args.preview)
        return 0

    if args.command == "crop":
        bottom = args.bottom
        if args.bands:
            bottom = int(json.loads(Path(args.bands).read_text(encoding="utf-8"))["crop_bottom"])
        box = None
        note = ""
        if args.layout or args.panel:
            if not (args.layout and args.panel):
                print("crop: --layout and --panel must be given together", file=sys.stderr)
                return 2
            try:
                layout = json.loads(Path(args.layout).read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                print(f"crop: cannot read {args.layout}: {error}", file=sys.stderr)
                return 2
            problem = layout_problem(layout)
            if problem:
                print(f"crop: {args.layout} {problem}; rerun frame_filter.py layout", file=sys.stderr)
                return 2
            for warning in layout.get("warnings") or []:
                print(f"crop: warning: {args.layout}: {warning}", file=sys.stderr)
            panels = {panel["name"]: panel for panel in layout["panels"]}
            if args.panel not in panels:
                print(f"crop: panel {args.panel!r} is not in {args.layout}; choose one of: "
                      f"{', '.join(panels) or '(no panels)'}", file=sys.stderr)
                return 2
            with Image.open(args.image) as image:
                size = image.size
            if size != (layout["width"], layout["height"]):
                print(f"crop: {args.image} is {size[0]}x{size[1]} but {args.layout} was measured on "
                      f"{layout['width']}x{layout['height']} frames", file=sys.stderr)
                return 2
            try:
                box = inset_box(panels[args.panel]["box"], layout["width"], layout["height"], args.inset)
            except ValueError as error:
                print(f"crop: {error}", file=sys.stderr)
                return 2
            note = f" panel={args.panel} box={list(box)}"
        size = crop_image(args.image, args.out, args.top, bottom, box)
        print(f"{args.out} {size[0]}x{size[1]} (top={args.top} bottom={bottom}{note})")
        return 0

    if args.command == "score":
        rows = []
        for path in args.frames:
            scores = score_frame(load_gray(path), bottom_frac=args.bottom_frac)
            scores["talking_head"] = classify(scores, args.info_threshold, args.edge_threshold)
            scores["frame"] = path
            rows.append(scores)
            flag = "TALKING_HEAD" if scores["talking_head"] else "ok"
            print(f"{flag:13s} info={scores['info']:.3f} edge={scores['edge']:.3f} {path}")
        if args.json:
            Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        flagged = sum(1 for r in rows if r["talking_head"])
        print(f"frames={len(rows)} talking_head={flagged}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
