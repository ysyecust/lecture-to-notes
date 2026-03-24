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

    # Strategy 1: Ultra-wide frame — likely side-by-side layout
    # Try splitting at various vertical positions
    best_split = None
    best_score = 0

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
        else:
            ratio = right_score / total
            if ratio > best_score:
                best_score = ratio
                best_split = (split_x, 0, w, h)

    # Also check color variance as a secondary signal
    if best_split:
        x1, y1, x2, y2 = best_split
        slide_region = img.crop(best_split)
        other_x1 = 0 if x1 > 0 else x2
        other_x2 = x1 if x1 > 0 else w
        other_region = img.crop((other_x1, y1, other_x2, y2))

        slide_var = compute_color_variance(slide_region)
        other_var = compute_color_variance(other_region)

        # If both strategies agree (edge density + color variance),
        # we're confident about the crop
        if slide_var > other_var * 0.5:  # Slide has reasonable variance
            return best_split

    # Strategy 2: Fall back to right-side crop for typical lecture layouts
    # (lecturer on left, slide on right)
    if aspect > 2.0:
        right_region = img.crop((w // 3, 0, w, h))
        left_region = img.crop((0, 0, w // 3, h))
        if compute_edge_density(right_region) > compute_edge_density(left_region) * 1.5:
            return (w // 3, 0, w, h)
        elif compute_edge_density(left_region) > compute_edge_density(right_region) * 1.5:
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
