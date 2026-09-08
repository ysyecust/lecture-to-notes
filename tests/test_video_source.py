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
            "https://youtube.com/live/abc": "youtube",
            "https://youtube.com/shorts/abc": "youtube",
            "https://youtube.com/embed/abc": "youtube",
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
            "https://youtube.com/",
            "https://youtube.com/channel/teacher",
            "https://youtube.com/watch",
            "https://youtube.com/watch?v=",
            "https://youtube.com/arbitrary/path",
            "https://youtu.be/",
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

    def test_youtube_video_ids_are_ascii_and_have_no_extra_segments(self):
        cases = (
            "https://youtu.be/abc/extra",
            "https://youtu.be/视频",
            "https://youtube.com/live/abc/extra",
            "https://youtube.com/shorts/视频",
            "https://youtube.com/embed/abc/extra",
            "https://youtube.com/watch?v=视频",
            "https://youtube.com/watch?v=abc%2Fextra",
        )

        for url in cases:
            with self.subTest(url=url):
                with self.assertRaises(video_source.UnsupportedSourceError):
                    video_source.detect_platform(url)


class ProbeTests(unittest.TestCase):
    URL = "https://x.com/person/status/2075594420163092606/video/1"

    @mock.patch("video_source.subprocess.run")
    def test_probe_returns_compact_metadata(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "id": "2075594420163092606",
                    "title": "Lecture",
                    "uploader": "Teacher",
                    "duration": 120.5,
                    "webpage_url": self.URL,
                    "thumbnail": "https://example.test/thumb.jpg",
                    "subtitles": {"en": [{}]},
                    "automatic_captions": {"zh": [{}]},
                }
            ),
            stderr="",
        )

        result = video_source.probe_source(self.URL)

        self.assertEqual(result["platform"], "x")
        self.assertEqual(result["id"], "2075594420163092606")
        self.assertEqual(result["subtitle_languages"], ["en", "zh"])
        self.assertTrue(result["has_thumbnail"])
        run.assert_called_once_with(
            [
                "yt-dlp",
                "--dump-single-json",
                "--no-playlist",
                "--skip-download",
                self.URL,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_extractor_failure(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="private post"
        )

        with self.assertRaisesRegex(video_source.ProbeError, "private post"):
            video_source.probe_source(self.URL)

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_missing_id_or_invalid_duration(self, run):
        payloads = (
            {"duration": 1},
            {"id": "123", "duration": 0},
            {"id": "123", "duration": -1},
            {"id": "123", "duration": True},
        )

        for payload in payloads:
            with self.subTest(payload=payload):
                run.return_value = subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=json.dumps(payload),
                    stderr="",
                )
                with self.assertRaises(video_source.ProbeError):
                    video_source.probe_source(self.URL)

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_non_object_metadata(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps([]), stderr=""
        )

        with self.assertRaisesRegex(video_source.ProbeError, "JSON object"):
            video_source.probe_source(self.URL)

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_non_mapping_subtitles(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps({"id": "123", "duration": 1, "subtitles": []}),
            stderr="",
        )

        with self.assertRaisesRegex(video_source.ProbeError, "subtitles"):
            video_source.probe_source(self.URL)

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_non_mapping_automatic_captions(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {"id": "123", "duration": 1, "automatic_captions": "zh"}
            ),
            stderr="",
        )

        with self.assertRaisesRegex(video_source.ProbeError, "automatic_captions"):
            video_source.probe_source(self.URL)

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_non_finite_duration(self, run):
        for duration in (float("nan"), float("inf")):
            with self.subTest(duration=duration):
                run.return_value = subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout=json.dumps({"id": "123", "duration": duration}),
                    stderr="",
                )
                with self.assertRaises(video_source.ProbeError):
                    video_source.probe_source(self.URL)

    @mock.patch("video_source.subprocess.run")
    def test_probe_rejects_invalid_json(self, run):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="not JSON", stderr=""
        )

        with self.assertRaisesRegex(video_source.ProbeError, "invalid JSON metadata"):
            video_source.probe_source(self.URL)

    @mock.patch("video_source.subprocess.run", side_effect=FileNotFoundError)
    def test_probe_reports_missing_ytdlp(self, run):
        with self.assertRaisesRegex(video_source.ProbeError, "yt-dlp"):
            video_source.probe_source(self.URL)


class CookieArgumentTests(unittest.TestCase):
    def test_no_cookie_source_adds_no_flags(self):
        self.assertEqual(video_source.cookie_arguments(), [])

    def test_browser_and_file_map_to_their_flags(self):
        self.assertEqual(
            video_source.cookie_arguments(cookies_from_browser="chrome"),
            ["--cookies-from-browser", "chrome"],
        )
        self.assertEqual(
            video_source.cookie_arguments(cookies_file="/tmp/cookies.txt"),
            ["--cookies", "/tmp/cookies.txt"],
        )

    def test_two_cookie_sources_are_rejected(self):
        with self.assertRaises(ValueError):
            video_source.cookie_arguments(
                cookies_from_browser="chrome", cookies_file="/tmp/cookies.txt"
            )


class ProbeCookieTests(unittest.TestCase):
    PAYLOAD = {
        "id": "BV1xx411c7mD",
        "title": "lecture",
        "duration": 60,
        "uploader": "teacher",
    }

    def _run(self, returncode=0, stderr="", stdout=None):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=returncode,
            stdout=json.dumps(stdout if stdout is not None else self.PAYLOAD),
            stderr=stderr,
        )
        return mock.patch.object(subprocess, "run", return_value=completed)

    def test_browser_cookies_reach_the_yt_dlp_command(self):
        with self._run() as runner:
            video_source.probe_source(
                "https://www.bilibili.com/video/BV1xx411c7mD",
                cookies_from_browser="chrome",
            )
        command = runner.call_args[0][0]
        self.assertIn("--cookies-from-browser", command)
        self.assertEqual(command[command.index("--cookies-from-browser") + 1], "chrome")
        self.assertEqual(command[-1], "https://www.bilibili.com/video/BV1xx411c7mD")

    def test_probe_without_cookies_keeps_the_original_command(self):
        with self._run() as runner:
            video_source.probe_source("https://www.bilibili.com/video/BV1xx411c7mD")
        command = runner.call_args[0][0]
        self.assertNotIn("--cookies-from-browser", command)
        self.assertNotIn("--cookies", command)

    def test_http_412_suggests_retrying_with_cookies(self):
        with self._run(returncode=1, stderr="ERROR: unable to download: HTTP Error 412"):
            with self.assertRaises(video_source.ProbeError) as caught:
                video_source.probe_source(
                    "https://www.bilibili.com/video/BV1xx411c7mD"
                )
        self.assertIn("--cookies-from-browser", str(caught.exception))

    def test_hint_is_omitted_once_cookies_were_supplied(self):
        with self._run(returncode=1, stderr="ERROR: unable to download: HTTP Error 412"):
            with self.assertRaises(video_source.ProbeError) as caught:
                video_source.probe_source(
                    "https://www.bilibili.com/video/BV1xx411c7mD",
                    cookies_from_browser="chrome",
                )
        self.assertNotIn("retry with", str(caught.exception))

    def test_unrelated_failures_do_not_get_the_cookie_hint(self):
        with self._run(returncode=1, stderr="ERROR: video unavailable"):
            with self.assertRaises(video_source.ProbeError) as caught:
                video_source.probe_source(
                    "https://www.bilibili.com/video/BV1xx411c7mD"
                )
        self.assertNotIn("--cookies-from-browser", str(caught.exception))
