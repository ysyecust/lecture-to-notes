#!/usr/bin/env python3
"""
smart_crop.py — Detect and crop the slide/content region from lecture video frames.

Many lecture recordings use a picture-in-picture layout:
  - A large slide/PPT area (high information density)
  - A smaller lecturer camera feed (low information density)

This script automatically detects the slide region and crops it out,
producing cleaner figures for LaTeX notes.

Strategies (tried in order):
  1. Edge-density split: divide the frame vertically, pick the half with
     more edges (= more text/diagrams = slide region).
  2. Color-variance split: the slide region typically has higher color
     variance (text, diagrams) vs. the lecturer region (uniform background).
  3. Aspect-ratio heuristic: if the frame is ultra-wide (>2.2:1), assume
     side-by-side layout and crop the larger content region.

Usage:
  python smart_crop.py <input_image> <output_image> [--threshold 0.6]
  python smart_crop.py --batch <input_dir> <output_dir> [--threshold 0.6]
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageFilter, ImageStat
except ImportError:
    print("Error: Pillow is required. Install with: pip install Pillow", file=sys.stderr)
    sys.exit(1)


def compute_edge_density(img: Image.Image) -> float:
    """Compute edge density as a proxy for information content."""
    gray = img.convert("L")
    edges = gray.filter(ImageFilter.FIND_EDGES)
    stat = ImageStat.Stat(edges)
    return stat.mean[0]


def compute_color_variance(img: Image.Image) -> float:
    """Compute color variance — slides have more variance than a lecturer."""
    stat = ImageStat.Stat(img)
    # Average variance across RGB channels
    return sum(stat.var) / len(stat.var)


def detect_blackboard(img: Image.Image, threshold: float = 0.25) -> bool:
    """
    Detect if a significant portion of the image is a blackboard/chalkboard.

    Blackboards are characterized by large areas of dark green or dark gray.
    When a blackboard is detected, it likely contains hand-drawn diagrams
    and should NOT be cropped out.
    """
    rgb = img.convert("RGB")
    pixels = list(rgb.getdata())
    total = len(pixels)
    if total == 0:
        return False

    blackboard_pixels = 0
    for r, g, b in pixels:
        # Dark green (classic chalkboard): low R, moderate G, low B
        is_dark_green = (r < 120 and g > r and g < 180 and b < 120
                         and g - r > 10)
        # Dark gray/black board
        is_dark = (r < 80 and g < 80 and b < 80)
        if is_dark_green or is_dark:
            blackboard_pixels += 1

    ratio = blackboard_pixels / total
    return ratio > threshold


def both_sides_have_content(left_density: float, right_density: float,
                            min_ratio: float = 0.35) -> bool:
    """
    Check if both sides have significant content.

    If the weaker side still has > min_ratio of the total density,
    both sides likely contain important information (e.g., blackboard diagrams
    on one side, slides on the other). In this case, keep the full frame.
    """
    total = left_density + right_density
    if total == 0:
        return False
    weaker = min(left_density, right_density)
    return (weaker / total) > min_ratio


def detect_slide_region(img: Image.Image, threshold: float = 0.6) -> tuple:
    """
    Detect the slide region in a lecture frame.

    Returns (x1, y1, x2, y2) bounding box of the detected slide region,
    or None if the frame appears to be all-slide (no cropping needed).
    """
    w, h = img.size
    aspect = w / h

    # Strategy 0: If aspect ratio is normal (< 2.0), likely full-screen slide
    # or full-screen lecturer — check if there's a clear split
    if aspect < 1.8:
        # Try vertical split (top/bottom) for standard 16:9 with overlay
        top = img.crop((0, 0, w, h // 2))
        bot = img.crop((0, h // 2, w, h))
        top_density = compute_edge_density(top)
        bot_density = compute_edge_density(bot)

        # If one half is dramatically denser, crop to it
        total = top_density + bot_density
        if total > 0:
            ratio = max(top_density, bot_density) / total
            if ratio > threshold:
                if top_density > bot_density:
                    return (0, 0, w, h // 2)
                else:
                    return (0, h // 2, w, h)
        return None  # No clear split, keep full frame

    # === SAFEGUARD: Blackboard detection ===
    # If a large portion of the frame is blackboard, the lecturer is likely
    # drawing diagrams on it. Keep the full frame to preserve those diagrams.
    if detect_blackboard(img, threshold=0.20):
        # Blackboard detected — only crop if the slide side is VERY dominant
        # (raise the effective threshold significantly)
        threshold = max(threshold, 0.75)

    # Strategy 1: Ultra-wide frame — likely side-by-side layout
    # Try splitting at various vertical positions
    best_split = None
    best_score = 0
    best_left_density = 0
    best_right_density = 0

    for split_pct in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]:
        split_x = int(w * split_pct)

        left = img.crop((0, 0, split_x, h))
        right = img.crop((split_x, 0, w, h))

        left_density = compute_edge_density(left)
        right_density = compute_edge_density(right)

        # Normalize by area to get density per pixel
        left_score = left_density * left.size[0]
        right_score = right_density * right.size[0]

        total = left_score + right_score
        if total == 0:
            continue

        # The side with higher information density is likely the slide
        if left_score > right_score:
            ratio = left_score / total
            if ratio > best_score:
                best_score = ratio
                best_split = (0, 0, split_x, h)
                best_left_density = left_density
                best_right_density = right_density
        else:
            ratio = right_score / total
            if ratio > best_score:
                best_score = ratio
                best_split = (split_x, 0, w, h)
                best_left_density = left_density
                best_right_density = right_density

    # === SAFEGUARD: Both-sides-have-content check ===
    # If the "weaker" side still has significant edge density,
    # both sides likely contain important info (e.g., blackboard diagrams
    # on one side, slides on the other). Keep full frame.
    if best_split and both_sides_have_content(
            best_left_density, best_right_density, min_ratio=0.42):
        return None  # Both sides have content, keep full frame

    # Also check color variance as a secondary signal
    if best_split:
        x1, y1, x2, y2 = best_split
        slide_region = img.crop(best_split)
        other_x1 = 0 if x1 > 0 else x2
        other_x2 = x1 if x1 > 0 else w
        other_region = img.crop((other_x1, y1, other_x2, y2))

        slide_var = compute_color_variance(slide_region)
        other_var = compute_color_variance(other_region)

        # === SAFEGUARD: High variance on discarded side ===
        # If the "discarded" side also has high color variance,
        # it probably contains diagrams/writing, not just a lecturer.
        if other_var > slide_var * 0.8:
            return None  # Discarded side has too much content, keep full

        # If both strategies agree (edge density + color variance),
        # we're confident about the crop
        if slide_var > other_var * 0.5:  # Slide has reasonable variance
            return best_split

    # Strategy 2: Fall back to right-side crop for typical lecture layouts
    # (lecturer on left, slide on right)
    if aspect > 2.0:
        right_region = img.crop((w // 3, 0, w, h))
        left_region = img.crop((0, 0, w // 3, h))
        right_d = compute_edge_density(right_region)
        left_d = compute_edge_density(left_region)

        # Only crop if one side is MUCH denser (2x, not 1.5x)
        if right_d > left_d * 2.0:
            return (w // 3, 0, w, h)
        elif left_d > right_d * 2.0:
            return (0, 0, w * 2 // 3, h)

    return None  # No confident detection


def crop_slide(input_path: str, output_path: str, threshold: float = 0.6,
               min_width: int = 640, padding: int = 10) -> bool:
    """
    Crop the slide region from a lecture frame.

    Returns True if cropping was applied, False if the original was kept.
    """
    img = Image.open(input_path)
    region = detect_slide_region(img, threshold)

    if region is None:
        # No clear slide region detected, keep original
        img.save(output_path)
        return False

    x1, y1, x2, y2 = region

    # Add small padding
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(img.size[0], x2 + padding)
    y2 = min(img.size[1], y2 + padding)

    cropped = img.crop((x1, y1, x2, y2))

    # Don't crop if result is too small
    if cropped.size[0] < min_width:
        img.save(output_path)
        return False

    cropped.save(output_path)
    return True


def batch_crop(input_dir: str, output_dir: str, threshold: float = 0.6) -> dict:
    """Crop all images in a directory. Returns stats."""
    os.makedirs(output_dir, exist_ok=True)
    stats = {"total": 0, "cropped": 0, "kept": 0}

    for f in sorted(Path(input_dir).glob("*.png")):
        out = os.path.join(output_dir, f.name)
        was_cropped = crop_slide(str(f), out, threshold)
        stats["total"] += 1
        if was_cropped:
            stats["cropped"] += 1
        else:
            stats["kept"] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(description="Smart crop slide region from lecture frames")
    parser.add_argument("input", help="Input image or directory (with --batch)")
    parser.add_argument("output", help="Output image or directory (with --batch)")
    parser.add_argument("--batch", action="store_true", help="Process entire directory")
    parser.add_argument("--threshold", type=float, default=0.6,
                        help="Split confidence threshold (0.5-0.9, default 0.6)")
    args = parser.parse_args()

    if args.batch:
        stats = batch_crop(args.input, args.output, args.threshold)
        print(f"Processed {stats['total']} frames: "
              f"{stats['cropped']} cropped, {stats['kept']} kept original")
    else:
        was_cropped = crop_slide(args.input, args.output, args.threshold)
        action = "Cropped slide region" if was_cropped else "Kept original (no clear split)"
        print(f"{action}: {args.output}")


if __name__ == "__main__":
    main()
