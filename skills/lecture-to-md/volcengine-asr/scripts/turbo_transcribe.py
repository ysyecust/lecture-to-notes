#!/usr/bin/env python3
"""Transcribe a local media file with Volcengine BigASR 1.0 Turbo."""

from __future__ import annotations

import argparse
import base64
import uuid
from pathlib import Path

from asr_common import (
    AsrError,
    api_base,
    api_status,
    asr_headers,
    build_request,
    default_output_dir,
    fail,
    load_secret_file,
    post_json,
    prepare_audio,
    require_secret,
    write_transcript_files,
)


RESOURCE_ID = "volc.bigasr.auc_turbo"
RECOGNIZE_PATH = "/api/v3/auc/bigmodel/recognize/flash"
MAX_DURATION_SECONDS = 2 * 60 * 60
MAX_AUDIO_BYTES = 100 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transcribe a local audio/video file with BigASR 1.0 Turbo."
    )
    parser.add_argument("input", type=Path, help="Local audio or video file")
    parser.add_argument("--output-dir", type=Path, help="Directory for JSON/TXT/SRT/MD")
    parser.add_argument("--secret-file", help="KEY=VALUE file; defaults to skill/.secret")
    parser.add_argument("--bitrate", default="48k", help="Prepared MP3 bitrate (default: 48k)")
    parser.add_argument("--language", default="", help="Optional ASR language code")
    parser.add_argument("--enable-ddc", action="store_true", help="Enable semantic smoothing")
    parser.add_argument("--speaker-info", action="store_true", help="Request speaker separation")
    parser.add_argument("--timeout", type=float, default=1800, help="HTTP timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        source = args.input.expanduser().resolve()
        output_dir = (
            args.output_dir.expanduser().resolve()
            if args.output_dir
            else default_output_dir(source, "turbo-v1")
        )
        config = load_secret_file(args.secret_file)
        app_id = require_secret(config, "VOLCENGINE_ASR_APP_ID")
        prepared = prepare_audio(source, output_dir, args.bitrate)
        if prepared.duration_seconds > MAX_DURATION_SECONDS:
            raise AsrError(
                f"Turbo accepts at most 2 hours; input is {prepared.duration_seconds / 3600:.2f} hours"
            )
        audio_size = prepared.path.stat().st_size
        if audio_size > MAX_AUDIO_BYTES:
            raise AsrError(
                f"Prepared audio is {audio_size / 1024 / 1024:.1f} MiB; Turbo limit is 100 MiB"
            )
        print(
            f"Prepared {prepared.path} "
            f"({prepared.duration_seconds:.1f}s, {audio_size / 1024 / 1024:.2f} MiB)"
        )
        encoded_audio = base64.b64encode(prepared.path.read_bytes()).decode("ascii")
        task_id = str(uuid.uuid4())
        request_body = build_request(
            app_id,
            {"data": encoded_audio},
            language=args.language,
            enable_ddc=args.enable_ddc,
            speaker_info=args.speaker_info,
        )
        body, response_headers, _ = post_json(
            api_base() + RECOGNIZE_PATH,
            request_body,
            asr_headers(config, RESOURCE_ID, task_id, sequence=True),
            args.timeout,
        )
        status_code, message, log_id = api_status(response_headers)
        print(f"Volcengine status={status_code or 'missing'} message={message or '-'} logid={log_id or '-'}")
        if status_code != "20000000":
            raise AsrError(
                f"Turbo recognition failed: status={status_code or 'missing'}, message={message or body}"
            )
        paths = write_transcript_files(
            body,
            output_dir,
            source_name=source.name,
            mode="turbo-v1",
            task_id=task_id,
        )
        print(f"Transcript TXT: {paths['txt']}")
        print(f"Transcript SRT: {paths['srt']}")
        print(f"Full result JSON: {paths['json']}")
        return 0
    except AsrError as exc:
        fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
