#!/usr/bin/env python3
"""Shared helpers for the Volcengine transcription command-line scripts."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SECRET_FILE = SKILL_DIR / ".secret"
DEFAULT_API_BASE = "https://openspeech.bytedance.com"


class AsrError(RuntimeError):
    """An actionable error raised by a transcription script."""


def load_secret_file(path: Optional[str] = None) -> Dict[str, str]:
    secret_path = Path(
        path
        or os.environ.get("VOLCENGINE_ASR_SECRET_FILE", "")
        or DEFAULT_SECRET_FILE
    ).expanduser()
    values: Dict[str, str] = {}
    if secret_path.exists():
        for line_number, raw_line in enumerate(
            secret_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise AsrError(
                    f"Invalid secret line {line_number} in {secret_path}; expected KEY=VALUE"
                )
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            values[key] = value
    for key, value in os.environ.items():
        if key.startswith("VOLCENGINE_") or key.startswith("TOS_"):
            values[key] = value
    return values


def require_secret(config: Mapping[str, str], key: str) -> str:
    value = config.get(key, "").strip()
    if not value:
        raise AsrError(
            f"Missing {key}. Add it to {DEFAULT_SECRET_FILE} or export it as an environment variable."
        )
    return value


def bool_config(config: Mapping[str, str], key: str, default: bool) -> bool:
    raw = config.get(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def ensure_command(command: str) -> None:
    try:
        subprocess.run(
            [command, "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise AsrError(f"Required command is unavailable: {command}") from exc


def media_duration_seconds(path: Path) -> float:
    ensure_command("ffprobe")
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AsrError(f"ffprobe could not read {path}: {completed.stderr.strip()}")
    try:
        return float(completed.stdout.strip())
    except ValueError as exc:
        raise AsrError(f"ffprobe returned no duration for {path}") from exc


def safe_stem(path: Path) -> str:
    stem = re.sub(r"[\x00-\x1f/\\]+", "_", path.stem).strip(" ._")
    return stem or "transcript"


def default_output_dir(source: Path, mode: str) -> Path:
    return source.parent / "_volcengine_transcripts" / f"{safe_stem(source)}__{mode}"


@dataclass(frozen=True)
class PreparedAudio:
    path: Path
    duration_seconds: float


def prepare_audio(source: Path, output_dir: Path, bitrate: str = "48k") -> PreparedAudio:
    source = source.expanduser().resolve()
    if not source.is_file():
        raise AsrError(f"Input file does not exist: {source}")
    ensure_command("ffmpeg")
    duration = media_duration_seconds(source)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "prepared_audio.mp3"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        "-map_metadata",
        "-1",
        str(destination),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AsrError(f"ffmpeg audio extraction failed: {completed.stderr.strip()}")
    return PreparedAudio(destination, duration)


def api_base() -> str:
    return os.environ.get("VOLCENGINE_ASR_API_BASE", DEFAULT_API_BASE).rstrip("/")


def post_json(
    url: str,
    payload: Mapping[str, Any],
    headers: Mapping[str, str],
    timeout: float,
) -> Tuple[Dict[str, Any], Dict[str, str], int]:
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **dict(headers)}
    request = Request(url, data=encoded, headers=request_headers, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            status = response.status
    except HTTPError as exc:
        raw = exc.read()
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
        status = exc.code
        message = raw.decode("utf-8", errors="replace")[:2000]
        raise AsrError(f"HTTP {status} from Volcengine: {message}") from exc
    except URLError as exc:
        raise AsrError(f"Could not reach Volcengine: {exc.reason}") from exc
    try:
        body = json.loads(raw.decode("utf-8")) if raw else {}
    except json.JSONDecodeError as exc:
        preview = raw.decode("utf-8", errors="replace")[:500]
        raise AsrError(f"Volcengine returned non-JSON data: {preview}") from exc
    if not isinstance(body, dict):
        raise AsrError("Volcengine returned a JSON value that is not an object")
    return body, response_headers, status


def asr_headers(
    config: Mapping[str, str],
    resource_id: str,
    task_id: str,
    *,
    sequence: bool = False,
    log_id: str = "",
) -> Dict[str, str]:
    headers = {
        "X-Api-App-Key": require_secret(config, "VOLCENGINE_ASR_APP_ID"),
        "X-Api-Access-Key": require_secret(config, "VOLCENGINE_ASR_ACCESS_TOKEN"),
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": task_id,
    }
    if sequence:
        headers["X-Api-Sequence"] = "-1"
    if log_id:
        headers["X-Tt-Logid"] = log_id
    return headers


def api_status(headers: Mapping[str, str]) -> Tuple[str, str, str]:
    return (
        headers.get("x-api-status-code", ""),
        headers.get("x-api-message", ""),
        headers.get("x-tt-logid", ""),
    )


def atomic_write_json(path: Path, value: Mapping[str, Any], mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.chmod(temporary, mode)
    temporary.replace(path)
    os.chmod(path, mode)


def milliseconds_to_srt(value: Any) -> str:
    try:
        total = max(0, int(value))
    except (TypeError, ValueError):
        total = 0
    hours, remainder = divmod(total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def milliseconds_to_clock(value: Any) -> str:
    try:
        total_seconds = max(0, int(value) // 1000)
    except (TypeError, ValueError):
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def result_payload(body: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = body.get("result")
    return candidate if isinstance(candidate, dict) else body


def utterances_from(body: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    payload = result_payload(body)
    utterances = payload.get("utterances", [])
    if isinstance(utterances, list):
        return [item for item in utterances if isinstance(item, dict)]
    return []


def transcript_text(body: Mapping[str, Any]) -> str:
    payload = result_payload(body)
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    pieces = [str(item.get("text", "")).strip() for item in utterances_from(body)]
    return "\n".join(piece for piece in pieces if piece)


def write_transcript_files(
    body: Mapping[str, Any],
    output_dir: Path,
    *,
    source_name: str,
    mode: str,
    task_id: str,
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "result.json"
    txt_path = output_dir / "transcript.txt"
    srt_path = output_dir / "transcript.srt"
    md_path = output_dir / "transcript.md"
    atomic_write_json(raw_path, dict(body), mode=0o644)

    text_value = transcript_text(body)
    txt_path.write_text(text_value + ("\n" if text_value else ""), encoding="utf-8")

    utterances = list(utterances_from(body))
    srt_blocks = []
    markdown_lines = [
        f"# {source_name}",
        "",
        f"- 模式：`{mode}`",
        f"- 任务 ID：`{task_id}`",
        "",
        "## 转录",
        "",
    ]
    for index, item in enumerate(utterances, start=1):
        item_text = str(item.get("text", "")).strip()
        if not item_text:
            continue
        start = item.get("start_time", 0)
        end = item.get("end_time", start)
        speaker = item.get("speaker_id", item.get("speaker", ""))
        speaker_prefix = f"说话人 {speaker}：" if speaker not in {"", None} else ""
        srt_blocks.append(
            f"{len(srt_blocks) + 1}\n{milliseconds_to_srt(start)} --> "
            f"{milliseconds_to_srt(end)}\n{speaker_prefix}{item_text}"
        )
        markdown_lines.append(
            f"- **[{milliseconds_to_clock(start)}]** {speaker_prefix}{item_text}"
        )
    if not utterances and text_value:
        markdown_lines.append(text_value)
    srt_path.write_text("\n\n".join(srt_blocks) + ("\n" if srt_blocks else ""), encoding="utf-8")
    md_path.write_text("\n".join(markdown_lines).rstrip() + "\n", encoding="utf-8")
    return {"json": raw_path, "txt": txt_path, "srt": srt_path, "md": md_path}


def build_request(
    app_id: str,
    audio: Mapping[str, str],
    *,
    language: str = "",
    enable_ddc: bool = False,
    speaker_info: bool = False,
) -> Dict[str, Any]:
    request: Dict[str, Any] = {
        "model_name": "bigmodel",
        "enable_itn": True,
        "enable_punc": True,
        "enable_ddc": enable_ddc,
        "show_utterances": True,
        "enable_speaker_info": speaker_info,
    }
    if language:
        request["language"] = language
    return {
        "user": {"uid": app_id},
        "audio": dict(audio),
        "request": request,
    }


def tos_client(config: Mapping[str, str]) -> Any:
    try:
        import tos  # type: ignore
    except ImportError as exc:
        raise AsrError(
            "The TOS Python SDK is required for local async uploads. "
            "Install it with: python3 -m pip install tos"
        ) from exc
    return tos.TosClientV2(
        require_secret(config, "TOS_ACCESS_KEY"),
        require_secret(config, "TOS_SECRET_KEY"),
        require_secret(config, "TOS_ENDPOINT"),
        require_secret(config, "TOS_REGION"),
    )


def upload_to_tos(
    config: Mapping[str, str],
    local_path: Path,
    object_key: str,
    expires_seconds: int,
) -> Tuple[str, str]:
    try:
        import tos  # type: ignore
    except ImportError as exc:
        raise AsrError(
            "The TOS Python SDK is required for local async uploads. "
            "Install it with: python3 -m pip install tos"
        ) from exc
    client = tos_client(config)
    bucket = require_secret(config, "TOS_BUCKET")
    with local_path.open("rb") as stream:
        response = client.put_object(bucket, object_key, content=stream)
    status = getattr(response, "status_code", 200)
    if status not in {200, 201, 204}:
        raise AsrError(f"TOS upload failed with HTTP status {status}")
    signed = client.pre_signed_url(
        tos.HttpMethodType.Http_Method_Get,
        bucket=bucket,
        key=object_key,
        expires=expires_seconds,
    )
    url = getattr(signed, "signed_url", "") or getattr(signed, "url", "")
    if not url:
        raise AsrError("TOS SDK did not return a pre-signed download URL")
    return bucket, str(url)


def delete_tos_object(config: Mapping[str, str], bucket: str, object_key: str) -> None:
    client = tos_client(config)
    client.delete_object(bucket, object_key)


def fail(message: str) -> "None":
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)

