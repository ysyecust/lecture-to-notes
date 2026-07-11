#!/usr/bin/env python3
"""Detect and metadata-probe lecture video sources."""

import argparse
import json
import math
import re
import subprocess
import sys
from collections.abc import Mapping
from urllib.parse import urlsplit


class UnsupportedSourceError(ValueError):
    """Raised when a URL is not a supported lecture video source."""


class ProbeError(RuntimeError):
    """Raised when yt-dlp cannot validate a playable source."""


def _normalized_host(host: str) -> str:
    normalized = host.lower().rstrip(".")
    for prefix in ("www.", "mobile.", "m."):
        if normalized.startswith(prefix):
            return normalized[len(prefix) :]
    return normalized


def detect_platform(url: str) -> str:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as error:
        raise UnsupportedSourceError(f"Unsupported video URL: {url}") from error

    if parsed.scheme not in ("http", "https") or not hostname:
        raise UnsupportedSourceError(f"Unsupported video URL: {url}")

    host = _normalized_host(hostname)
    path = parsed.path.rstrip("/")

    if host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com"):
        return "youtube"

    if host == "b23.tv" and path:
        return "bilibili"

    if (
        host == "bilibili.com" or host.endswith(".bilibili.com")
    ) and re.fullmatch(r"/video/BV[0-9A-Za-z]+", path, re.IGNORECASE):
        return "bilibili"

    if host in ("x.com", "twitter.com") and re.fullmatch(
        r"/[^/]+/status/[0-9]+(?:/video/[0-9]+)?", path
    ):
        return "x"

    raise UnsupportedSourceError(f"Unsupported video URL: {url}")


def _subtitle_languages(payload: dict) -> list[str]:
    languages = set()
    for field in ("subtitles", "automatic_captions"):
        tracks = payload.get(field)
        if tracks is None:
            continue
        if not isinstance(tracks, Mapping):
            raise ProbeError(
                f"yt-dlp returned invalid {field} metadata; expected an object"
            )
        languages.update(tracks.keys())
    return sorted(languages)


def _compact_metadata(platform: str, payload: dict) -> dict:
    if not isinstance(payload, Mapping):
        raise ProbeError("yt-dlp metadata must be a JSON object")

    source_id = str(payload.get("id") or "").strip()
    if not source_id:
        raise ProbeError("yt-dlp returned no playable video ID")

    duration = payload.get("duration")
    if (
        type(duration) not in (int, float)
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise ProbeError("yt-dlp returned no positive video duration")

    return {
        "platform": platform,
        "id": source_id,
        "title": payload.get("title") or "",
        "uploader": payload.get("uploader") or "",
        "duration": float(duration),
        "webpage_url": payload.get("webpage_url") or "",
        "has_thumbnail": bool(payload.get("thumbnail")),
        "subtitle_languages": _subtitle_languages(payload),
    }


def probe_source(url: str) -> dict:
    platform = detect_platform(url)
    command = [
        "yt-dlp",
        "--dump-single-json",
        "--no-playlist",
        "--skip-download",
        url,
    ]

    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False
        )
    except FileNotFoundError as error:
        raise ProbeError("yt-dlp executable was not found") from error

    if completed.returncode != 0:
        detail = completed.stderr.strip() or "unknown extractor failure"
        raise ProbeError(f"yt-dlp probe failed: {detail}")

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ProbeError("yt-dlp returned invalid JSON metadata") from error

    return _compact_metadata(platform, payload)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect_parser = subparsers.add_parser("detect")
    detect_parser.add_argument("url")

    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("url")

    args = parser.parse_args()

    try:
        if args.command == "detect":
            print(detect_platform(args.url))
        else:
            print(json.dumps(probe_source(args.url), ensure_ascii=False, indent=2))
    except UnsupportedSourceError as error:
        print(error, file=sys.stderr)
        return 2
    except ProbeError as error:
        print(error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
