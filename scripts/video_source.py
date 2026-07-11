#!/usr/bin/env python3
"""Detect and metadata-probe lecture video sources."""

import argparse
import json
import re
import subprocess
import sys
from urllib.parse import urlsplit


class UnsupportedSourceError(ValueError):
    """Raised when a URL is not a supported lecture video source."""


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
