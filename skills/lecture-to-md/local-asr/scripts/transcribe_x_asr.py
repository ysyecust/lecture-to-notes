from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import detect_default_provider, require, resolve_model_dir  # noqa: E402


MODEL_MAX_CHUNK_SECONDS = 30.0
CJK = "\u3400-\u4dbf\u4e00-\u9fff"
STRONG_PUNCTUATION = re.compile(r"[。！？!?；;]$")
WEAK_PUNCTUATION = re.compile(r"[，,：:]$")


@dataclass(frozen=True)
class ModelFiles:
    encoder: Path
    decoder: Path
    joiner: Path
    tokens: Path


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def format_srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def normalize_token_text(tokens: Sequence[str]) -> str:
    text = "".join(tokens).replace("▁", " ")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(rf"(?<=[{CJK}])\s+(?=[{CJK}])", "", text)
    text = re.sub(r"\s+([，。！？；：,.!?;:])", r"\1", text)
    text = re.sub(r"([，。！？；：])\s+", r"\1", text)
    return text


def _pick_model_file(model_dir: Path, prefix: str) -> Path:
    candidates = sorted(model_dir.glob(f"{prefix}*.onnx"))
    if not candidates:
        raise FileNotFoundError(f"no {prefix}*.onnx under {model_dir}")
    int8 = [path for path in candidates if ".int8." in path.name]
    selected = int8 or candidates
    if len(selected) != 1:
        names = ", ".join(path.name for path in selected)
        raise ValueError(f"ambiguous {prefix} model files: {names}")
    return selected[0]


def discover_model_files(model_dir: Path) -> ModelFiles:
    model_dir = model_dir.resolve()
    tokens = model_dir / "tokens.txt"
    if not tokens.is_file():
        raise FileNotFoundError(f"missing tokens.txt under {model_dir}")
    return ModelFiles(
        encoder=_pick_model_file(model_dir, "encoder"),
        decoder=_pick_model_file(model_dir, "decoder"),
        joiner=_pick_model_file(model_dir, "joiner"),
        tokens=tokens,
    )


def tokens_to_cues(
    tokens: Sequence[str],
    timestamps: Sequence[float],
    *,
    chunk_start: float,
    chunk_duration: float,
    max_cue_seconds: float = 8.0,
    max_cue_chars: int = 52,
) -> list[Cue]:
    if not tokens or len(tokens) != len(timestamps):
        return []

    groups: list[tuple[list[str], float, float]] = []
    current: list[str] = []
    first_time = 0.0
    last_time = 0.0

    for token, raw_timestamp in zip(tokens, timestamps):
        timestamp = min(max(float(raw_timestamp), 0.0), chunk_duration)
        if current:
            proposed = normalize_token_text([*current, token])
            if timestamp - first_time >= max_cue_seconds or len(proposed) >= max_cue_chars:
                groups.append((current, first_time, last_time))
                current = []
        if not current:
            first_time = timestamp
        current.append(token)
        last_time = timestamp
        text = normalize_token_text(current)
        elapsed = max(0.0, last_time - first_time)
        should_split = bool(STRONG_PUNCTUATION.search(text))
        should_split = should_split or (
            elapsed >= 3.5 and bool(WEAK_PUNCTUATION.search(text))
        )
        should_split = should_split or elapsed >= max_cue_seconds
        should_split = should_split or len(text) >= max_cue_chars
        if should_split:
            groups.append((current, first_time, last_time))
            current = []

    if current:
        groups.append((current, first_time, last_time))

    cues: list[Cue] = []
    chunk_end = chunk_start + chunk_duration
    for index, (group_tokens, first, last) in enumerate(groups):
        text = normalize_token_text(group_tokens)
        if not text:
            continue
        prior_end = cues[-1].end if cues else chunk_start
        start = max(prior_end, chunk_start + first - 0.35)
        if index + 1 < len(groups):
            next_first = groups[index + 1][1]
            end = min(chunk_end, chunk_start + max(last + 0.35, next_first - 0.05))
        else:
            end = min(chunk_end, chunk_start + last + 0.8)
        if end <= start:
            end = min(chunk_end, start + 0.5)
        cues.append(Cue(start=start, end=end, text=text))
    return cues


def _select_boundary(
    samples: Any,
    sample_rate: int,
    *,
    min_seconds: float,
    target_seconds: float,
    max_seconds: float,
    numpy: Any,
) -> int:
    lower = max(1, round(min_seconds * sample_rate))
    target = round(target_seconds * sample_rate)
    upper = min(len(samples), round(max_seconds * sample_rate))
    if upper <= lower:
        return upper

    window = max(1, round(0.20 * sample_rate))
    step = max(1, round(0.05 * sample_rate))
    best_position = min(max(target, lower), upper)
    best_score = float("inf")
    float_samples = samples.astype(numpy.float32) / 32768.0
    for position in range(lower, upper + 1, step):
        start = max(0, position - window // 2)
        end = min(len(float_samples), position + window // 2)
        rms = float(numpy.sqrt(numpy.mean(float_samples[start:end] ** 2)))
        distance_penalty = 0.0005 * abs(position - target) / sample_rate
        score = rms + distance_penalty
        if score < best_score:
            best_score = score
            best_position = position
    return best_position


def iter_wave_chunks(
    wav_path: Path,
    *,
    min_seconds: float,
    target_seconds: float,
    max_seconds: float,
    numpy: Any,
) -> Iterable[tuple[float, Any, int]]:
    with wave.open(str(wav_path), "rb") as stream:
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
            raise ValueError("normalized WAV must be mono 16-bit PCM")
        sample_rate = stream.getframerate()
        if sample_rate != 16000:
            raise ValueError(f"normalized WAV must be 16 kHz, got {sample_rate}")

        max_samples = round(max_seconds * sample_rate)
        pending = numpy.empty(0, dtype=numpy.int16)
        offset_samples = 0
        eof = False
        while pending.size or not eof:
            needed = max(0, max_samples - pending.size)
            raw = stream.readframes(needed)
            incoming = numpy.frombuffer(raw, dtype=numpy.int16)
            if incoming.size:
                pending = numpy.concatenate((pending, incoming))
            eof = incoming.size < needed
            if not pending.size:
                break

            if eof:
                boundary = pending.size
            else:
                boundary = _select_boundary(
                    pending,
                    sample_rate,
                    min_seconds=min_seconds,
                    target_seconds=target_seconds,
                    max_seconds=max_seconds,
                    numpy=numpy,
                )
            chunk = numpy.ascontiguousarray(pending[:boundary])
            yield offset_samples / sample_rate, chunk, sample_rate
            offset_samples += boundary
            pending = pending[boundary:]


def write_srt(path: Path, cues: Sequence[Cue]) -> None:
    temp = path.with_suffix(path.suffix + ".part")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        for index, cue in enumerate(cues, start=1):
            stream.write(f"{index}\n")
            stream.write(
                f"{format_srt_timestamp(cue.start)} --> "
                f"{format_srt_timestamp(cue.end)}\n"
            )
            stream.write(cue.text + "\n\n")
    temp.replace(path)


def _normalize_audio(input_path: Path, output_path: Path) -> None:
    ffmpeg = require("ffmpeg")
    completed = subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip()
        raise RuntimeError(f"ffmpeg audio normalization failed: {detail[-1000:]}")


def _load_runtime() -> tuple[Any, Any]:
    try:
        import numpy
        import sherpa_onnx
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "X ASR requires optional packages: "
            "python -m pip install 'numpy>=1.24' 'sherpa-onnx>=1.13.6'"
        ) from error
    return numpy, sherpa_onnx


def transcribe(args: argparse.Namespace) -> dict[str, Any]:
    if not 0 < args.min_chunk_seconds <= args.chunk_seconds <= args.max_chunk_seconds:
        raise ValueError("require 0 < min chunk <= target chunk <= max chunk")
    if args.max_chunk_seconds > MODEL_MAX_CHUNK_SECONDS:
        raise ValueError(
            f"X ASR offline model chunks must be <= {MODEL_MAX_CHUNK_SECONDS:g}s"
        )

    numpy, sherpa_onnx = _load_runtime()
    model_dir = resolve_model_dir(str(args.model_dir)) if args.model_dir else resolve_model_dir()
    model_files = discover_model_files(Path(model_dir))
    provider = args.provider or os.environ.get("ASR_PROVIDER") or detect_default_provider()
    try:
        recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(model_files.encoder),
            decoder=str(model_files.decoder),
            joiner=str(model_files.joiner),
            tokens=str(model_files.tokens),
            num_threads=args.threads,
            provider=provider,
            decoding_method="greedy_search",
            debug=False,
        )
    except Exception as error:
        if provider == "cpu":
            raise
        print(f"provider '{provider}' 加载失败 ({error.__class__.__name__})，回退 cpu", file=sys.stderr)
        provider = "cpu"
        recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
            encoder=str(model_files.encoder),
            decoder=str(model_files.decoder),
            joiner=str(model_files.joiner),
            tokens=str(model_files.tokens),
            num_threads=args.threads,
            provider="cpu",
            decoding_method="greedy_search",
            debug=False,
        )

    all_cues: list[Cue] = []
    all_tokens: list[str] = []
    all_timestamps: list[float] = []
    chunks = 0
    audio_seconds = 0.0
    decode_seconds = 0.0
    with tempfile.TemporaryDirectory(prefix="lecture-x-asr-") as directory:
        normalized = Path(directory) / "audio.wav"
        _normalize_audio(args.input, normalized)
        for chunk_start, int_samples, sample_rate in iter_wave_chunks(
            normalized,
            min_seconds=args.min_chunk_seconds,
            target_seconds=args.chunk_seconds,
            max_seconds=args.max_chunk_seconds,
            numpy=numpy,
        ):
            chunks += 1
            chunk_duration = len(int_samples) / sample_rate
            audio_seconds = max(audio_seconds, chunk_start + chunk_duration)
            samples = numpy.ascontiguousarray(
                int_samples.astype(numpy.float32) / 32768.0
            )
            stream = recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            started = time.perf_counter()
            recognizer.decode_stream(stream)
            decode_seconds += time.perf_counter() - started
            result = stream.result
            result_tokens = list(getattr(result, "tokens", ()) or ())
            result_timestamps = list(getattr(result, "timestamps", ()) or ())
            if len(result_tokens) == len(result_timestamps):
                all_tokens.extend(str(token) for token in result_tokens)
                all_timestamps.extend(
                    chunk_start + float(timestamp) for timestamp in result_timestamps
                )
            cues = tokens_to_cues(
                result_tokens,
                result_timestamps,
                chunk_start=chunk_start,
                chunk_duration=chunk_duration,
                max_cue_seconds=args.max_cue_seconds,
                max_cue_chars=args.max_cue_chars,
            )
            if not cues and result.text.strip():
                cues = [
                    Cue(
                        start=chunk_start,
                        end=chunk_start + chunk_duration,
                        text=result.text.strip(),
                    )
                ]
            all_cues.extend(cues)
            print(
                f"chunks={chunks} audio_end={audio_seconds:.1f}s "
                f"cues={len(all_cues)} decode={decode_seconds:.2f}s",
                flush=True,
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_srt(args.output, all_cues)
    report = {
        "backend": "sherpa-onnx-x-asr",
        "sherpa_onnx_version": getattr(sherpa_onnx, "__version__", "unknown"),
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "model": {key: str(value) for key, value in asdict(model_files).items()},
        "threads": args.threads,
        "provider": provider,
        "language": args.language,
        "tokens": all_tokens,
        "timestamps": all_timestamps,
        "chunks": chunks,
        "cues": len(all_cues),
        "audio_seconds": audio_seconds,
        "decode_seconds": decode_seconds,
        "rtf": decode_seconds / audio_seconds if audio_seconds else None,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Transcribe lecture audio to SRT with a local sherpa-onnx X ASR "
            "Chinese/English transducer model. The model is supplied separately."
        )
    )
    parser.add_argument("input", type=Path, help="Audio or video input understood by ffmpeg")
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path, default=Path("audio_x_asr.srt"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--threads", type=int, default=max(1, min(8, os.cpu_count() or 1)))
    parser.add_argument("--provider", choices=["cpu", "cuda"], default=None)
    parser.add_argument("--lang", dest="language", default="zh")
    parser.add_argument("--min-chunk-seconds", type=float, default=20.0)
    parser.add_argument("--chunk-seconds", type=float, default=27.0)
    parser.add_argument("--max-chunk-seconds", type=float, default=30.0)
    parser.add_argument("--max-cue-seconds", type=float, default=8.0)
    parser.add_argument("--max-cue-chars", type=int, default=52)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = transcribe(args)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
