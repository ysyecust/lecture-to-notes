#!/usr/bin/env python3
"""Offline integration tests for all script entry points."""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parent


def result_body(text):
    return {
        "audio_info": {"duration": 1000},
        "result": {
            "text": text,
            "utterances": [
                {"start_time": 0, "end_time": 1000, "text": text, "words": []}
            ],
        },
    }


class FakeAsrHandler(BaseHTTPRequestHandler):
    query_counts = {}

    def log_message(self, *_args):
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        task_id = self.headers.get("X-Api-Request-Id", "unknown")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Tt-Logid", f"fake-{task_id}")
        if self.path.endswith("/recognize/flash"):
            self.send_header("X-Api-Status-Code", "20000000")
            self.send_header("X-Api-Message", "OK")
            body = result_body("极速版模拟转录成功。")
        elif self.path.endswith("/submit"):
            self.send_header("X-Api-Status-Code", "20000000")
            self.send_header("X-Api-Message", "OK")
            body = {}
        elif self.path.endswith("/query"):
            count = self.query_counts.get(task_id, 0)
            self.query_counts[task_id] = count + 1
            if count == 0:
                self.send_header("X-Api-Status-Code", "20000001")
                self.send_header("X-Api-Message", "Processing")
                body = {}
            else:
                self.send_header("X-Api-Status-Code", "20000000")
                self.send_header("X-Api-Message", "OK")
                body = result_body("异步模式模拟转录成功。")
        else:
            self.send_header("X-Api-Status-Code", "45000001")
            self.send_header("X-Api-Message", "Unknown path")
            body = {}
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def create_wav(path: Path) -> None:
    sample_rate = 16000
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        frames = bytearray()
        for index in range(sample_rate):
            value = int(2000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            frames.extend(struct.pack("<h", value))
        output.writeframes(bytes(frames))


def run(command, env):
    completed = subprocess.run(
        [sys.executable, *map(str, command)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"Command failed ({completed.returncode}): {' '.join(map(str, command))}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAsrHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="volcengine-asr-test-") as temp:
            root = Path(temp)
            secret = root / ".secret"
            secret.write_text(
                "VOLCENGINE_ASR_APP_ID=fake-app\n"
                "VOLCENGINE_ASR_ACCESS_TOKEN=fake-token\n",
                encoding="utf-8",
            )
            media = root / "sample.wav"
            create_wav(media)
            env = os.environ.copy()
            env["VOLCENGINE_ASR_API_BASE"] = f"http://127.0.0.1:{server.server_port}"
            env["VOLCENGINE_ASR_SECRET_FILE"] = str(secret)

            turbo_output = root / "turbo"
            run(
                [SCRIPTS / "turbo_transcribe.py", media, "--output-dir", turbo_output],
                env,
            )
            assert "极速版模拟转录成功" in (turbo_output / "transcript.txt").read_text()

            for mode in ("standard-v1", "standard-v2", "idle-v1"):
                output = root / mode
                run(
                    [
                        SCRIPTS / "upload_submit.py",
                        "--mode",
                        mode,
                        "--audio-url",
                        "https://example.invalid/audio.mp3",
                        "--output-dir",
                        output,
                    ],
                    env,
                )
                run(
                    [
                        SCRIPTS / "poll_transcript.py",
                        output / "job.json",
                        "--interval",
                        "0.25",
                        "--timeout",
                        "5",
                    ],
                    env,
                )
                assert "异步模式模拟转录成功" in (output / "transcript.txt").read_text()
        print("offline integration tests passed: turbo-v1, standard-v1, standard-v2, idle-v1")
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
