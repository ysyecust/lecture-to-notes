import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import video_source


class DetectPlatformTests(unittest.TestCase):
    def test_supported_urls(self):
        cases = {
            "https://www.youtube.com/watch?v=abc": "youtube",
            "https://youtu.be/abc": "youtube",
            "https://www.bilibili.com/video/BV1xx411c7mD": "bilibili",
            "https://b23.tv/abcdef": "bilibili",
            "https://x.com/person/status/2075594420163092606": "x",
            "https://x.com/person/status/2075594420163092606/video/1": "x",
            "https://mobile.twitter.com/person/status/2075594420163092606?x=1#fragment": "x",
        }

        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(video_source.detect_platform(url), expected)

    def test_unsupported_urls(self):
        cases = (
            "https://x.com/",
            "https://x.com/person",
            "https://t.co/abc",
            "not-a-url",
            "ftp://x.com/person/status/123",
            "http://[::1",
            "https://x.com:bad/person/status/123",
            "https://x.com/person/status/１２３",
            "https://x.com/person/status/123/video/١",
        )

        for url in cases:
            with self.subTest(url=url):
                with self.assertRaises(video_source.UnsupportedSourceError):
                    video_source.detect_platform(url)
