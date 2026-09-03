#!/usr/bin/env python3
"""Poll an asynchronous Volcengine AUC task and download transcript files."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict

from asr_common import (
    AsrError,
    api_base,
    api_status,
    asr_headers,
    bool_config,
    delete_tos_object,
    fail,
    load_secret_file,
    post_json,
    write_transcript_files,
)


PROCESSING_CODES = {"20000001", "20000002"}
SUCCESS_CODE = "20000000"


def is_retryable_query_error(exc: AsrError) -> bool:
    """Return whether a query failure is likely to be a transient transport issue."""
    message = str(exc)
    return message.startswith("Could not reach Volcengine:") or message.startswith(
        "Volcengine returned non-JSON data:"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Poll a standard/idle AUC job until its transcript is ready."
    )
    parser.add_argument("job_file", type=Path, help="job.json from upload_submit.py")
    parser.add_argument("--secret-file", help="KEY=VALUE file; defaults to skill/.secret")
    parser.add_argument("--interval", type=float, default=3.0, help="Seconds between queries")
    parser.add_argument("--timeout", type=float, help="Overall wait timeout in seconds")
    parser.add_argument("--once", action="store_true", help="Query once and exit if pending")
    parser.add_argument("--keep-upload", action="store_true", help="Do not delete the TOS object")
    return parser.parse_args()


def read_job(path: Path) -> Dict[str, Any]:
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AsrError(f"Job file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AsrError(f"Job file is invalid JSON: {path}") from exc
    required = ["mode", "resource_id", "query_path", "task_id", "output_dir"]
    missing = [key for key in required if not job.get(key)]
    if missing:
        raise AsrError(f"Job file is missing fields: {', '.join(missing)}")
    return job


def maybe_delete_upload(
    config: Dict[str, str], job: Dict[str, Any], *, keep_upload: bool
) -> None:
    tos_record = job.get("tos")
    should_delete = bool_config(config, "TOS_AUTO_DELETE", True) and not keep_upload
    if not should_delete or not isinstance(tos_record, dict):
        return
    bucket = str(tos_record.get("bucket", ""))
    object_key = str(tos_record.get("object_key", ""))
    if bucket and object_key:
        delete_tos_object(config, bucket, object_key)
        print(f"Deleted temporary TOS object: tos://{bucket}/{object_key}")


def main() -> int:
    args = parse_args()
    try:
        job_path = args.job_file.expanduser().resolve()
        job = read_job(job_path)
        config = load_secret_file(args.secret_file)
        default_timeout = 25 * 60 * 60 if job["mode"] == "idle-v1" else 4 * 60 * 60
        timeout = args.timeout if args.timeout is not None else default_timeout
        started = time.monotonic()
        attempt = 0
        while True:
            attempt += 1
            try:
                body, response_headers, _ = post_json(
                    api_base() + str(job["query_path"]),
                    {},
                    asr_headers(
                        config,
                        str(job["resource_id"]),
                        str(job["task_id"]),
                        log_id=str(job.get("log_id", "")),
                    ),
                    60,
                )
            except AsrError as exc:
                elapsed = time.monotonic() - started
                if args.once or not is_retryable_query_error(exc) or elapsed >= timeout:
                    raise
                print(
                    f"Query #{attempt}: transient error={exc}; retrying "
                    f"in {max(0.25, args.interval):.1f}s elapsed={elapsed:.1f}s"
                )
                time.sleep(max(0.25, args.interval))
                continue
            status_code, message, log_id = api_status(response_headers)
            elapsed = time.monotonic() - started
            print(
                f"Query #{attempt}: status={status_code or 'missing'} "
                f"message={message or '-'} elapsed={elapsed:.1f}s"
            )
            if status_code == SUCCESS_CODE:
                output_dir = Path(str(job["output_dir"])).expanduser().resolve()
                paths = write_transcript_files(
                    body,
                    output_dir,
                    source_name=str(job.get("source_name", "transcript")),
                    mode=str(job["mode"]),
                    task_id=str(job["task_id"]),
                )
                maybe_delete_upload(config, job, keep_upload=args.keep_upload)
                print(f"Transcript TXT: {paths['txt']}")
                print(f"Transcript SRT: {paths['srt']}")
                print(f"Full result JSON: {paths['json']}")
                return 0
            if status_code not in PROCESSING_CODES:
                maybe_delete_upload(config, job, keep_upload=args.keep_upload)
                raise AsrError(
                    f"Recognition failed: status={status_code or 'missing'}, "
                    f"message={message or body}, logid={log_id or job.get('log_id', '')}"
                )
            if args.once:
                print("Task is still pending; run this command again later.")
                return 2
            if elapsed >= timeout:
                raise AsrError(
                    f"Polling timed out after {timeout:.0f}s. The job remains reusable: {job_path}"
                )
            time.sleep(max(0.25, args.interval))
    except AsrError as exc:
        fail(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
