"""共用工具：ffprobe/ffmpeg 探测与抽音频、纯文本写出、跨平台 PATH 兜底。

本模块只依赖标准库 + ffmpeg/ffprobe，可被任意 python3 直接导入。
跨平台（macOS / Linux / Windows）共用——见 `require()` 的路径兜底列表。
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _candidate_dirs() -> list[str]:
    """按当前平台返回常见二进制目录，按优先级排序。"""
    system = platform.system().lower()
    candidates: list[str] = []
    if system == "darwin":
        candidates += ["/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"]
    elif system == "linux":
        candidates += [
            "/usr/local/bin", "/usr/bin",
            os.path.expanduser("~/.local/bin"),
            "/snap/bin",
        ]
    elif system == "windows":
        # Windows：依赖 PATH；这里只是兜底，常见安装位置
        candidates += [
            os.path.expandvars(r"%ProgramFiles%\ffmpeg\bin"),
            os.path.expandvars(r"%ProgramFiles%\ImageMagick"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python"),
        ]
    return [p for p in candidates if p and os.path.isdir(p)]


def require(cmd: str) -> str:
    """查找命令；跨平台兜底：PATH 找不到时按平台常见目录挨个找。"""
    path = shutil.which(cmd)
    if path is None:
        for cand in _candidate_dirs():
            full = os.path.join(cand, cmd + (".exe" if platform.system().lower() == "windows" else ""))
            if os.path.exists(full) and os.access(full, os.X_OK):
                return full
    if path is None:
        sys.exit(
            f"[asr] 缺少命令: {cmd}。\n"
            f"  macOS:   brew install ffmpeg\n"
            f"  Linux:   sudo apt install ffmpeg  (Debian/Ubuntu)\n"
            f"  Windows: winget install Gyan.FFmpeg  (PowerShell)\n"
            f"装完后确保 {cmd} 在 PATH 中，或把它放进上面列出的常见目录。"
        )
    return path


def probe(path: str) -> dict:
    """返回时长(秒)与流信息。失败时抛出 RuntimeError。

    优先 ffprobe；若不可用或报「不支持的选项」（如 imageio_ffmpeg 送的
    johnvansickle 静态 build），回退到 Python stdlib `wave`（仅 wav 路径）。
    """
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            out = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-show_entries", "stream=codec_type", "-of", "json", path],
                capture_output=True, text=True, check=True,
            ).stdout
            data = json.loads(out)
            duration = 0.0
            try:
                duration = float(data.get("format", {}).get("duration") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
            codec_types = [s.get("codec_type") for s in data.get("streams", [])]
            return {
                "duration": duration,
                "has_video": "video" in codec_types,
                "has_audio": "audio" in codec_types,
            }
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass  # 下面走 wave 兜底

    # wave 兜底：仅适用于 wav；其它格式会报错
    import wave as _wave
    try:
        with _wave.open(path, "rb") as w:
            n_frames = w.getnframes()
            sr = w.getframerate()
            duration = n_frames / sr if sr else 0.0
            n_channels = w.getnchannels()
        return {
            "duration": duration,
            "has_video": False,
            "has_audio": True,
            "has_audio_fallback_wave": True,  # 标记：未走 ffprobe
        }
    except Exception as exc:
        raise RuntimeError(
            f"ffprobe 不可用且 wave 模块读不出 {path}: {exc}"
        )


def extract_audio(src: str, dst_wav: str, sample_rate: int = 16000) -> str:
    """把任意音视频转成 16kHz 单声道 PCM wav（sherpa-onnx 只吃 16k 音频）。"""
    ffmpeg = require("ffmpeg")
    cmd = [
        ffmpeg, "-y", "-v", "error", "-i", src,
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
        dst_wav,
    ]
    subprocess.run(cmd, check=True)
    if not os.path.exists(dst_wav) or os.path.getsize(dst_wav) == 0:
        raise RuntimeError(f"ffmpeg 抽音频失败: {src}")
    return dst_wav


def is_plain_wav(path: str) -> bool:
    """粗判：16k 单声道 PCM。不确定就返回 False，交给 ffmpeg 统一转，成本很低。"""
    try:
        with open(path, "rb") as f:
            head = f.read(44)
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            return False
        channels = int.from_bytes(head[22:24], "little")
        rate = int.from_bytes(head[24:28], "little")
        return channels == 1 and rate == 16000
    except Exception:
        return False


def prepare_audio(src: str, workdir: str | None = None) -> tuple[str, str]:
    """返回 (wav路径, 工作目录)。已经是 16k 单声道 wav 时直接复用原文件。"""
    if os.path.splitext(src)[1].lower() == ".wav" and is_plain_wav(src):
        return src, ""
    workdir = workdir or tempfile.mkdtemp(prefix="asr-audio-")
    os.makedirs(workdir, exist_ok=True)
    dst = os.path.join(workdir, "audio_16k_mono.wav")
    extract_audio(src, dst)
    return dst, workdir


def fmt_ts_short(seconds: float) -> str:
    """秒数 → HH:MM:SS 或 MM:SS（用于日志/进度提示）。"""
    if seconds < 0:
        seconds = 0.0
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def fmt_ts_srt(seconds: float) -> str:
    """秒数 → SRT/VTT 时间戳 HH:MM:SS,mmm（毫秒 3 位）。"""
    if seconds < 0:
        seconds = 0.0
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_plain_txt(text: str, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.strip() + "\n")
    return path


def write_plain_md(text: str, path: str, title: str = "转写稿", source: str = "") -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {title}", ""]
    if source:
        lines += [f"> 源文件：`{source}`", ""]
    for para in re.split(r"\n\s*\n", text.strip()):
        if para.strip():
            lines.append(para.strip())
            lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def cleanup_dir(path: str) -> None:
    if path and os.path.isdir(path) and os.path.basename(path).startswith("asr-audio-"):
        shutil.rmtree(path, ignore_errors=True)


def detect_default_provider() -> str:
    """根据当前平台自动选 provider。

    - macOS Apple Silicon（M1+）→ coreml（若 sherpa-onnx 支持；不支持则 transcribe.py 兜底为 cpu）
    - Linux 且检测到 CUDA → cuda
    - 其它 → cpu

    注意：coreml provider 需要 sherpa-onnx 版本支持且模型本身未禁用；当前 X-ASR int8 release
    没有官方 coreml 编译产物，transcribe.py 会在加载失败时自动 fallback 到 cpu 并打印警告。
    """
    system = platform.system().lower()
    machine = platform.machine().lower()  # 'arm64' / 'x86_64' / 'amd64'
    if system == "darwin" and machine in ("arm64", "aarch64"):
        return "coreml"
    if system == "linux":
        # 检测 NVIDIA：是否存在 nvidia-smi，或 torch / onnxruntime 能见到 CUDA。
        if shutil.which("nvidia-smi"):
            return "cuda"
    return "cpu"


def resolve_model_dir(explicit: str | None = None) -> str:
    """定位 X-ASR 模型目录：CLI 参数 > 环境变量 > 默认缓存目录。"""
    if explicit:
        if not os.path.isdir(explicit):
            sys.exit(f"[asr] 找不到模型目录: {explicit}\n先跑 bash scripts/setup.sh 下载。")
        return os.path.abspath(explicit)
    env_dir = os.environ.get("ASR_MODEL_DIR")
    if env_dir and os.path.isdir(env_dir):
        return os.path.abspath(env_dir)
    default = os.path.expanduser(
        "~/.cache/sherpa-onnx-models/"
        "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
    )
    if os.path.isdir(default):
        return default
    sys.exit(
        f"[asr] 模型未下载。先跑 bash scripts/setup.sh（Windows 见 SKILL.md 「Windows 设置」）。\n"
        f"或者 --model <dir> 指向已解压好的 X-ASR 目录。"
    )


def find_model_files(model_dir: str) -> tuple[str, str, str, str]:
    """在模型目录里找 encoder / decoder / joiner / tokens 四件套。

    sherpa-onnx 各版本文件名形如：
            encoder-epoch-99-avg-1.onnx   /   encoder.onnx
            decoder-epoch-99-avg-1.onnx   /   decoder.onnx
            joiner-epoch-99-avg-1.onnx    /   joiner.onnx
            tokens.txt
    本函数取目录下第一个匹配的 *.onnx，避免写死 epoch 数字。
    """
    if not os.path.isdir(model_dir):
        sys.exit(f"[asr] 模型目录不存在: {model_dir}")

    def _pick(prefix: str) -> str:
        for entry in sorted(os.listdir(model_dir)):
            if entry.startswith(prefix) and entry.endswith(".onnx"):
                return os.path.join(model_dir, entry)
        sys.exit(f"[asr] 模型目录里没有 {prefix}*.onnx: {model_dir}")

    encoder = _pick("encoder")
    decoder = _pick("decoder")
    joiner = _pick("joiner")
    tokens = os.path.join(model_dir, "tokens.txt")
    if not os.path.isfile(tokens):
        sys.exit(f"[asr] 模型目录里没有 tokens.txt: {model_dir}")
    return encoder, decoder, joiner, tokens
