#!/usr/bin/env python3
"""Prepare/upload media and submit an asynchronous Volcengine AUC task."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from asr_common import (
    AsrError,
    api_base,
    api_status,
    asr_headers,
    atomic_write_json,
    build_request,
    default_output_dir,
    fail,
    load_secret_file,
    post_json,
    prepare_audio,
    require_secret,
    upload_to_tos,
)


MODES = {
    "standard-v1": {
        "resource_id": "volc.bigasr.auc",
        "submit_path": "/api/v3/auc/bigmodel/submit",
        "query_path": "/api/v3/auc/bigmodel/query",
        "url_ttl": 6 * 60 * 60,
    },
    "standard-v2": {
        "resource_id": "volc.seedasr.auc",
        "submit_path": "/api/v3/auc/bigmodel/submit",
        "query_path": "/api/v3/auc/bigmodel/query",
        "url_ttl": 6 * 60 * 60,
    },
    "idle-v1": {
        "resource_id": "volc.bigasr.auc_idle",
        "submit_path": "/api/v3/auc/bigmodel/idle/submit",
        "query_path": "/api/v3/auc/bigmodel/idle/query",
        "url_ttl": 30 * 60 * 60,
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload local media to TOS and submit a standard/idle AUC task."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Local audio/video file (requires TOS)")
    source.add_argument("--audio-url", help="Existing direct HTTPS media URL; skips TOS upload")
    parser.add_argument("--mode", choices=sorted(MODES), default="standard-v2")
    parser.add_argument("--output-dir", type=Path, help="Job and prepared-audio directory")
    parser.add_argument("--job-file", type=Path, help="Override job JSON path")
    parser.add_argument("--secret-file", help="KEY=VALUE file; defaults to skill/.secret")
    parser.add_argument("--bitrate", default="48k", help="Prepared MP3 bitrate (default: 48k)")
    parser.add_argument("--language", default="", help="Optional ASR language code")
    parser.add_argument("--enable-ddc", action="store_true", help="Enable semantic smoothing")
    parser.add_argument("--speaker-info", action="store_true", help="Request speaker separation")
    parser.add_argument("--timeout", type=float, default=60, help="Submit HTTP timeout in seconds")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.input and importlib.util.find_spec("tos") is None:
            venv_dir = Path(__file__).resolve().parent.parent / ".venv"
            venv_python = venv_dir / "bin" / "python"
            if venv_python.is_file() and Path(sys.prefix).resolve() != venv_dir.resolve():
                os.execv(
                    str(venv_python),
                    [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
                )
        mode = MODES[args.mode]
        config = load_secret_file(args.secret_file)
        app_id = require_secret(config, "VOLCENGINE_ASR_APP_ID")
        task_id = str(uuid.uuid4())
        source_name: str
        tos_record = None

        if args.input:
            for key in (
                "TOS_ACCESS_KEY",
                "TOS_SECRET_KEY",
                "TOS_ENDPOINT",
                "TOS_REGION",
                "TOS_BUCKET",
            ):
                require_secret(config, key)
            source_path = args.input.expanduser().resolve()
            output_dir = (
                args.output_dir.expanduser().resolve()
                if args.output_dir
                else default_output_dir(source_path, args.mode)
            )
            prepared = prepare_audio(source_path, output_dir, args.bitrate)
            if prepared.duration_seconds >= 5 * 60 * 60:
                raise AsrError("Standard/idle AUC requires media shorter than 5 hours")
            if prepared.path.stat().st_size >= 512 * 1024 * 1024:
                raise AsrError("Standard/idle AUC requires media smaller than 512 MiB")
            prefix = config.get("TOS_PREFIX", "volcengine-asr").strip("/") or "volcengine-asr"
            object_key = f"{prefix}/{task_id}.mp3"
            print(f"Uploading prepared audio to private TOS object {object_key} ...")
            bucket, audio_url = upload_to_tos(
                config, prepared.path, object_key, int(mode["url_ttl"])
            )
            tos_record = {"bucket": bucket, "object_key": object_key}
            source_name = source_path.name
            source_path_text = str(source_path)
        else:
            audio_url = args.audio_url
            if not audio_url.lower().startswith(("http://", "https://")):
                raise AsrError("--audio-url must be an HTTP(S) direct-download URL")
            source_name = Path(audio_url.split("?", 1)[0]).name or "remote-media"
            source_path_text = ""
            output_dir = (
                args.output_dir.expanduser().resolve()
                if args.output_dir
                else Path.cwd() / "_volcengine_transcripts" / f"{task_id}__{args.mode}"
            )

        request_body = build_request(
            app_id,
            {"url": audio_url},
            language=args.language,
            enable_ddc=args.enable_ddc,
            speaker_info=args.speaker_info,
        )
        body, response_headers, _ = post_json(
            api_base() + str(mode["submit_path"]),
            request_body,
            asr_headers(config, str(mode["resource_id"]), task_id, sequence=True),
            args.timeout,
        )
        status_code, message, log_id = api_status(response_headers)
        print(f"Submit status={status_code or 'missing'} message={message or '-'} logid={log_id or '-'}")
        if status_code != "20000000":
            raise AsrError(
                f"Task submission failed: status={status_code or 'missing'}, message={message or body}"
            )

        job = {
            "schema_version": 1,
            "mode": args.mode,
            "resource_id": mode["resource_id"],
            "query_path": mode["query_path"],
            "task_id": task_id,
            "log_id": log_id,
            "source_name": source_name,
            "source_path": source_path_text,
            "output_dir": str(output_dir),
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "tos": tos_record,
        }
        job_path = (
            args.job_file.expanduser().resolve() if args.job_file else output_dir / "job.json"
        )
        atomic_write_json(job_path, job)
        print(f"Job file: {job_path}")
        print("Next: run poll_transcript.py with this job file")
        return 0
    except AsrError as exc:
        fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
