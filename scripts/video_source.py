#!/usr/bin/env python3
"""Detect and metadata-probe lecture video sources."""

import argparse
import json
import math
import re
import subprocess
import sys
from collections.abc import Mapping
from urllib.parse import parse_qs, urlsplit


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

    if host == "youtu.be" and re.fullmatch(r"/[A-Za-z0-9_-]+", path):
        return "youtube"

    if host == "youtube.com" or host.endswith(".youtube.com"):
        video_ids = parse_qs(parsed.query, keep_blank_values=True).get("v", [])
        if path == "/watch" and len(video_ids) == 1 and re.fullmatch(
            r"[A-Za-z0-9_-]+", video_ids[0]
        ):
            return "youtube"
        if re.fullmatch(r"/(?:live|shorts|embed)/[A-Za-z0-9_-]+", path):
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


# Extractor failures that authentication usually fixes. Bilibili answers an
# unauthenticated probe with HTTP 412; YouTube asks the caller to sign in.
_AUTH_HINT_MARKERS = (
    "http error 412",
    "sign in to confirm",
    "confirm you're not a bot",
    "login required",
    "account cookies",
)

_AUTH_HINT = (
    "the extractor rejected an unauthenticated request; retry with "
    "--cookies-from-browser chrome (or safari/firefox/edge), or --cookies FILE"
)


def _needs_auth(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in _AUTH_HINT_MARKERS)


def cookie_arguments(
    cookies_from_browser: str | None = None, cookies_file: str | None = None
) -> list[str]:
    """Build the yt-dlp cookie flags shared by probing and downloading."""
    if cookies_from_browser and cookies_file:
        raise ValueError(
            "pass either cookies_from_browser or cookies_file, not both"
        )
    if cookies_from_browser:
        return ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        return ["--cookies", cookies_file]
    return []


def probe_source(
    url: str,
    cookies_from_browser: str | None = None,
    cookies_file: str | None = None,
) -> dict:
    platform = detect_platform(url)
    command = [
        "yt-dlp",
        "--dump-single-json",
        "--no-playlist",
        "--skip-download",
        *cookie_arguments(cookies_from_browser, cookies_file),
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
        if _needs_auth(completed.stderr) and not (
            cookies_from_browser or cookies_file
        ):
            detail = f"{detail}\n{_AUTH_HINT}"
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
    cookie_group = probe_parser.add_mutually_exclusive_group()
    cookie_group.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="read cookies from a local browser profile, e.g. chrome",
    )
    cookie_group.add_argument(
        "--cookies",
        dest="cookies_file",
        metavar="FILE",
        help="read cookies from a Netscape-format cookie file",
    )

    args = parser.parse_args()

    try:
        if args.command == "detect":
            print(detect_platform(args.url))
        else:
            metadata = probe_source(
                args.url,
                cookies_from_browser=args.cookies_from_browser,
                cookies_file=args.cookies_file,
            )
            print(json.dumps(metadata, ensure_ascii=False, indent=2))
    except UnsupportedSourceError as error:
        print(error, file=sys.stderr)
        return 2
    except ProbeError as error:
        print(error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
