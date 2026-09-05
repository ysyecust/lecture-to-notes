#!/usr/bin/env python3
"""
Frame hygiene for models without image input: overlay bands, crops, and talking-head scores.

Slide content is never cropped automatically. This tool only measures and removes
persistent overlays (a burned-in subtitle band, a static navigation strip) and
flags frames whose only content is the presenter, so a text-only model can reject
them without seeing the picture.

Subcommands:
    bands  FRAME... [--json out.json]
        Sample frames from one video and locate the static navigation strip at the
        bottom and the burned-in subtitle band above it. Prints JSON:
        {"height": H, "nav_strip": px, "subtitle_band": [y0, y1] | null, "crop_bottom": px}
    crop   IMAGE --out OUT [--bands bands.json | --bottom PX] [--top PX]
        Remove `crop_bottom` rows (from `bands`) or explicit pixel margins.
    score  FRAME... [--json out.json] [--info-threshold 0.06] [--edge-threshold 0.02]
        Per-frame information score outside the presenter column, subtitle band, and
        logo corner; `talking_head` is true when both scores fall under the thresholds.

Requires Pillow and numpy.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import numpy as np
    from PIL import Image
except ImportError as error:  # pragma: no cover - environment dependent
    raise SystemExit("frame_filter.py needs Pillow and numpy: pip install Pillow numpy") from error


def load_gray(path: str) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8)


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


def crop_image(path: str, out: str, top: int = 0, bottom: int = 0) -> tuple[int, int]:
    with Image.open(path) as image:
        width, height = image.size
        box = (0, max(0, top), width, max(top + 1, height - max(0, bottom)))
        cropped = image.crop(box)
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

    p_crop = sub.add_parser("crop")
    p_crop.add_argument("image")
    p_crop.add_argument("--out", required=True)
    p_crop.add_argument("--bands", default=None, help="bands.json from the `bands` subcommand")
    p_crop.add_argument("--top", type=int, default=0)
    p_crop.add_argument("--bottom", type=int, default=0)

    p_score = sub.add_parser("score")
    p_score.add_argument("frames", nargs="+")
    p_score.add_argument("--json", default=None)
    p_score.add_argument("--info-threshold", type=float, default=0.06)
    p_score.add_argument("--edge-threshold", type=float, default=0.02)
    p_score.add_argument("--bottom-frac", type=float, default=0.15)

    args = parser.parse_args(argv)

    if args.command == "bands":
        paths = args.frames
        if len(paths) > args.max_frames:
            step = len(paths) / args.max_frames
            paths = [paths[int(i * step)] for i in range(args.max_frames)]
        frames = [load_gray(p) for p in paths]
        shape = frames[0].shape
        frames = [f for f in frames if f.shape == shape]
        result = detect_bands(frames)
        text = json.dumps(result)
        print(text)
        if args.json:
            Path(args.json).write_text(text + "\n", encoding="utf-8")
        return 0

    if args.command == "crop":
        bottom = args.bottom
        if args.bands:
            bottom = int(json.loads(Path(args.bands).read_text(encoding="utf-8"))["crop_bottom"])
        size = crop_image(args.image, args.out, args.top, bottom)
        print(f"{args.out} {size[0]}x{size[1]} (top={args.top} bottom={bottom})")
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
