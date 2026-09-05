#!/usr/bin/env python3
"""
Whisper transcription with platform-aware backend selection and a time budget.

Backend preference per platform:
  macOS on Apple silicon : mlx-whisper (Metal GPU) > faster-whisper > openai-whisper
  everything else        : faster-whisper (CTranslate2) > openai-whisper

Why this exists: on 2026-09-03 a Bilibili run spent 85 minutes on CPU
`whisper --model medium` without producing one segment, while mlx-whisper
large-v3-turbo transcribed the same 61-minute audio in about 6 minutes on the
same machine. The agent had no progress signal to decide when to switch.

This script gives that signal: it streams backend output, and when the budget
passes with no segment produced it kills the backend and exits 3 so the caller
can switch backends instead of waiting blindly.

Usage:
    python3 transcribe_whisper.py audio.wav --workdir /abs/workdir [--language zh]
        [--backend auto|mlx|faster|openai] [--model NAME]
        [--initial-prompt FILE] [--budget-minutes N] [--out audio.srt] [--dry-run]

Exit codes:
    0  transcript written
    2  no usable backend (install mlx-whisper / faster-whisper / openai-whisper)
    3  budget exceeded before the first segment; backend killed
    4  backend exited with an error
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

DEFAULT_MODELS = {
    "mlx": "mlx-community/whisper-large-v3-turbo",
    "faster": "large-v3-turbo",
    "openai": "small",
}

# Runner for faster-whisper: it has no CLI, so stream segments from Python and
# flush the SRT incrementally so a watcher can see progress.
FASTER_RUNNER = r"""
import sys
audio, model_name, language, out_srt, prompt = sys.argv[1:6]
from faster_whisper import WhisperModel
model = WhisperModel(model_name, device="auto", compute_type="auto")
segments, info = model.transcribe(
    audio, language=language or None, initial_prompt=prompt or None, vad_filter=True)
def stamp(t):
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}"
with open(out_srt, "w", encoding="utf-8") as fh:
    for i, seg in enumerate(segments, 1):
        line = f"[{stamp(seg.start)} --> {stamp(seg.end)}] {seg.text.strip()}"
        print(line, flush=True)
        fh.write(f"{i}\n{stamp(seg.start)} --> {stamp(seg.end)}\n{seg.text.strip()}\n\n")
        fh.flush()
"""


def detect_platform() -> tuple[str, str]:
    """Return (system, machine) lowercased, e.g. ('darwin', 'arm64')."""
    return platform.system().lower(), platform.machine().lower()


def available_backends() -> dict[str, list[str] | None]:
    """Map backend name to the argv prefix that launches it, or None if absent."""
    found: dict[str, list[str] | None] = {"mlx": None, "faster": None, "openai": None}
    mlx_cli = shutil.which("mlx_whisper")
    if mlx_cli:
        found["mlx"] = [mlx_cli]
    elif importlib.util.find_spec("mlx_whisper") is not None:
        found["mlx"] = [sys.executable, "-m", "mlx_whisper.cli"]
    if importlib.util.find_spec("faster_whisper") is not None:
        found["faster"] = [sys.executable, "-c", FASTER_RUNNER]
    whisper_cli = shutil.which("whisper")
    if whisper_cli:
        found["openai"] = [whisper_cli]
    elif importlib.util.find_spec("whisper") is not None:
        found["openai"] = [sys.executable, "-m", "whisper"]
    return found


def select_backend(
    system: str,
    machine: str,
    available: dict[str, list[str] | None],
    requested: str = "auto",
) -> tuple[str, str]:
    """
    Pick a backend name and explain why.

    Raises RuntimeError when the requested backend is missing or nothing is installed.
    """
    if requested != "auto":
        if available.get(requested):
            return requested, f"requested {requested}"
        raise RuntimeError(f"backend {requested!r} is not installed")
    apple_gpu = system == "darwin" and machine in {"arm64", "aarch64"}
    order = ["mlx", "faster", "openai"] if apple_gpu else ["faster", "openai"]
    for name in order:
        if available.get(name):
            if name == "mlx":
                why = "Apple silicon → Metal GPU backend"
            elif apple_gpu:
                why = f"first available on {system}/{machine}; mlx-whisper not installed (pip install mlx-whisper for GPU)"
            else:
                why = f"first available on {system}/{machine}"
            return name, why
    raise RuntimeError(
        "no transcription backend found; install one of: "
        "pip install mlx-whisper (macOS arm64), pip install faster-whisper, pip install openai-whisper"
    )


def default_model(backend: str) -> str:
    return DEFAULT_MODELS[backend]


def resolve_cache_env(workdir: Path, environ: dict[str, str], writable=os.access) -> dict[str, str]:
    """
    Return environment overrides that keep model caches writable.

    Sandboxed hosts may block `~/.cache`; when the default cache root is not
    writable the caches move under `<workdir>/.cache` so downloads still succeed.
    """
    overrides: dict[str, str] = {}
    home_cache = Path(environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    probe = home_cache if home_cache.exists() else home_cache.parent
    if not writable(str(probe), os.W_OK):
        local = workdir / ".cache"
        overrides["XDG_CACHE_HOME"] = str(local)
        overrides.setdefault("HF_HOME", str(local / "huggingface"))
    hf_home = Path(environ.get("HF_HOME") or (home_cache / "huggingface"))
    hf_probe = hf_home if hf_home.exists() else (hf_home.parent if hf_home.parent.exists() else home_cache.parent)
    if "HF_HOME" not in overrides and not writable(str(hf_probe), os.W_OK):
        overrides["HF_HOME"] = str(workdir / ".cache" / "huggingface")
    if "HF_HOME" in overrides:
        overrides["HF_HUB_CACHE"] = str(Path(overrides["HF_HOME"]) / "hub")
    return overrides


def build_command(
    backend: str,
    prefix: list[str],
    audio: Path,
    workdir: Path,
    language: str,
    model: str,
    initial_prompt: str = "",
) -> list[str]:
    """Assemble the backend argv. Every backend writes `<workdir>/<audio stem>.srt`."""
    audio_s = str(audio)
    if backend == "mlx":
        cmd = prefix + [
            audio_s, "--model", model, "--output-dir", str(workdir),
            "--output-format", "srt", "--verbose", "True",
        ]
        if language:
            cmd += ["--language", language]
        if initial_prompt:
            cmd += ["--initial-prompt", initial_prompt]
        return cmd
    if backend == "faster":
        out_srt = workdir / f"{audio.stem}.srt"
        return prefix + [audio_s, model, language, str(out_srt), initial_prompt]
    if backend == "openai":
        cmd = prefix + [
            audio_s, "--model", model, "--output_format", "srt",
            "--output_dir", str(workdir), "--fp16", "False", "--verbose", "True",
        ]
        if language:
            cmd += ["--language", language]
        if initial_prompt:
            cmd += ["--initial_prompt", initial_prompt]
        return cmd
    raise ValueError(f"unknown backend {backend!r}")


def run_with_budget(
    cmd: list[str],
    env: dict[str, str],
    budget_seconds: float,
    log,
    poll_seconds: float = 1.0,
) -> tuple[int, int]:
    """
    Run `cmd`, echoing its output to `log`.

    Returns (exit_code, segment_lines). Exit code 3 means the budget passed
    before any segment line (a line containing '-->') appeared and the process
    was killed. Once segments are flowing the budget no longer applies.
    """
    proc = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        bufsize=1, errors="replace",
    )
    state = {"segments": 0, "last_output": time.monotonic()}

    def pump():
        assert proc.stdout is not None
        for line in proc.stdout:
            state["last_output"] = time.monotonic()
            if "-->" in line:
                state["segments"] += 1
            log.write(line)
            log.flush()

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    started = time.monotonic()
    killed = False
    while proc.poll() is None:
        elapsed = time.monotonic() - started
        if elapsed > budget_seconds and state["segments"] == 0:
            proc.kill()
            killed = True
            break
        time.sleep(poll_seconds)
    thread.join(timeout=5)
    if killed:
        proc.wait()
        return 3, 0
    return proc.returncode, state["segments"]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio", help="audio file (wav/m4a/mp3)")
    parser.add_argument("--workdir", required=True, help="absolute working directory for outputs")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--backend", default="auto", choices=["auto", "mlx", "faster", "openai"])
    parser.add_argument("--model", default=None, help="backend-specific model name (default per backend)")
    parser.add_argument("--initial-prompt", default=None, help="text file with domain terms")
    parser.add_argument("--budget-minutes", type=float, default=10.0,
                        help="abort if no segment appears within this many minutes (default 10)")
    parser.add_argument("--out", default="audio.srt", help="final SRT name inside workdir")
    parser.add_argument("--dry-run", action="store_true", help="print the selected backend and command only")
    args = parser.parse_args(argv)

    workdir = Path(args.workdir).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    audio = Path(args.audio).resolve()
    system, machine = detect_platform()
    available = available_backends()
    try:
        backend, why = select_backend(system, machine, available, args.backend)
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    model = args.model or default_model(backend)
    prompt = Path(args.initial_prompt).read_text(encoding="utf-8").strip() if args.initial_prompt else ""
    prefix = available[backend] or []
    cmd = build_command(backend, prefix, audio, workdir, args.language, model, prompt)
    env = dict(os.environ)
    overrides = resolve_cache_env(workdir, env)
    env.update(overrides)

    print(f"backend={backend} ({why}) model={model} platform={system}/{machine}")
    if overrides:
        print("cache overrides: " + " ".join(f"{k}={v}" for k, v in overrides.items()))
    print("command: " + " ".join(repr(c) if " " in c or "\n" in c else c for c in cmd if c is not FASTER_RUNNER))
    if args.dry_run:
        return 0

    started = time.monotonic()
    code, segments = run_with_budget(cmd, env, args.budget_minutes * 60, sys.stdout)
    elapsed = time.monotonic() - started
    produced = workdir / f"{audio.stem}.srt"
    if code == 3:
        print(f"BUDGET EXCEEDED: no segment after {elapsed/60:.1f} min on backend={backend}; "
              f"rerun with --backend {'faster' if backend != 'faster' else 'openai'} or a smaller --model",
              file=sys.stderr)
        return 3
    if code != 0 or not produced.exists():
        print(f"ERROR: backend {backend} exited {code}; expected {produced}", file=sys.stderr)
        return 4
    target = workdir / args.out
    if target != produced:
        shutil.copyfile(produced, target)
    print(f"done backend={backend} model={model} elapsed={elapsed/60:.1f}min segments={segments} srt={target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
