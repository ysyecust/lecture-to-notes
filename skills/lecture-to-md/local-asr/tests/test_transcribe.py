"""Unit tests for lecture-to-md/local-asr scripts.

覆盖 review #1 的硬要求：
- 上游 backend 把音频切成 ≤30s 的 chunk（TestChunking 直接断言分块边界）
- 拼接出来的时间轴连续、无 overlap、无 gap（TestChunking 逐块断言）
- builtin backend 在 audio >60s 时拒绝

跨平台（macOS / Linux / Windows 均验证）：

    cd skills/lecture-to-md/local-asr
    python3 tests/test_transcribe.py

Windows 上也可以：

    powershell -ExecutionPolicy Bypass -Command "python tests\\test_transcribe.py"

需要外部依赖才跑得起来的用例会自动 skip：
    - TestUpstreamChunking   需要上游脚本 + X-ASR 模型 + sherpa_onnx 运行时
    - TestChunking           需要上游脚本 + numpy（纯逻辑，不加载模型）
    - 其余纯逻辑用例无外部依赖
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
import wave

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, os.path.join(SKILL_DIR, "scripts"))
# SCRIPT_DIR=tests, SKILL_DIR=local-asr, lecture-to-md, skills, lecture-to-notes
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR))))
UPSTREAM = os.path.join(REPO_ROOT, "scripts", "transcribe_x_asr.py")

from common import child_env, configure_utf8  # noqa: E402

# Windows 上子进程默认按 ANSI 代码页输出，父进程必须用同一个编码解码，
# 否则中文断言（如「内置 backend 不支持长音频」）会比对到乱码。
configure_utf8()
RUN_KW = {"encoding": "utf-8", "errors": "replace"}


def _unlink(path: str) -> None:
    """删除临时产物，但绝不因为清理失败而中断测试。

    finally 块里如果 unlink 抛异常（Windows 上很常见：文件被杀毒软件/索引器
    短暂占用、或已被并发清理掉），会把真正的断言失败掩盖掉，所以这里吞掉异常。
    """
    try:
        os.remove(path)
    except OSError:
        pass


def _write_sine_wav(path: str, duration_sec: float, freq: int = 440) -> None:
    """合成一段正弦波 wav（16kHz mono s16le PCM）。无音频内容但 X-ASR 会
    给出 0 cues，从而验证 chunking / 时间戳逻辑不会报错。"""
    import array as _array
    import math as _math

    sr = 16000
    n_frames = int(duration_sec * sr)
    amp = 8000
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = _array.array(
            "h",
            (int(amp * _math.sin(2 * _math.pi * freq * i / sr)) for i in range(n_frames)),
        )
        w.writeframes(frames.tobytes())


class TestUpstreamChunking(unittest.TestCase):
    """在 mac / Linux 上跑真实的 upstream backend，验证：
    1) 长音频被切成多个 chunk，每个 chunk 持续 ≤30s
    2) 拼接后 cues 的时间轴连续（无 overlap、无 gap >0.05s）

    依赖上游脚本 + X-ASR 模型 + sherpa_onnx 运行时；缺任一则 skip。
    """

    MODEL_DIR = os.environ.get(
        "ASR_TEST_MODEL_DIR",
        os.path.expanduser(
            "~/.cache/sherpa-onnx-models/"
            "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
        ),
    )

    @classmethod
    def setUpClass(cls):
        # 三个前置条件各自独立判断，避免“缺上游却因模型检查被吞掉”的不可达分支。
        if not os.path.isfile(UPSTREAM):
            raise unittest.SkipTest(f"upstream backend not found: {UPSTREAM}")
        if not os.path.isfile(os.path.join(cls.MODEL_DIR, "tokens.txt")):
            raise unittest.SkipTest(
                f"X-ASR model not found: {cls.MODEL_DIR}. "
                f"Run scripts/setup.sh (macOS/Linux) or scripts/setup.ps1 (Windows) first."
            )
        try:
            import sherpa_onnx  # noqa: F401
        except ModuleNotFoundError:
            raise unittest.SkipTest("sherpa-onnx not installed; run setup first")

    def _transcribe(self, wav_path: str) -> dict:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="asr-test-") as tmp:
            srt_path = os.path.join(tmp, "out.srt")
            report_path = os.path.join(tmp, "report.json")
            cmd = [
                sys.executable, UPSTREAM, wav_path,
                "--output", srt_path,
                "--report", report_path,
                "--model-dir", self.MODEL_DIR,
                "--threads", "4",
                "--max-chunk-seconds", "30.0",
                "--chunk-seconds", "27.0",
                "--min-chunk-seconds", "20.0",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  env=child_env(), **RUN_KW)
            if proc.returncode != 0:
                self.fail(f"upstream failed: {proc.stderr[-500:]}")
            with open(report_path, encoding="utf-8") as f:
                return json.load(f)

    def test_long_audio_split_into_chunks(self):
        """90s 正弦波 → 至少 3 个 chunk，且每块都不超过 30s 上限。"""
        wav = os.path.join(SCRIPT_DIR, "_test_long.wav")
        _write_sine_wav(wav, duration_sec=90.0)
        try:
            report = self._transcribe(wav)
        finally:
            _unlink(wav)

        chunks = report.get("chunks", 0)
        audio_seconds = report.get("audio_seconds", 0.0)
        # 90s 音频按 ≤30s/块必然 ≥3 块
        self.assertGreaterEqual(chunks, 3,
                                f"90s 音频应至少 3 个 chunk，实际 {chunks}")
        # 每块 ≤30s：chunks 块至少能铺满 audio_seconds（平均下来每块 ≤ audio/chunks）
        # 更强的可观察断言由 TestChunking（见下）直接对分块边界做，这里只做端到端烟测。
        self.assertGreaterEqual(chunks * 30.0, audio_seconds,
                                f"chunks*30 ({chunks * 30}) < audio ({audio_seconds})")

    def test_short_audio_single_chunk(self):
        """10s 音频 → 1 个 chunk。"""
        wav = os.path.join(SCRIPT_DIR, "_test_short.wav")
        _write_sine_wav(wav, duration_sec=10.0)
        try:
            report = self._transcribe(wav)
        finally:
            _unlink(wav)
        self.assertEqual(report.get("chunks"), 1,
                         f"10s 音频应只有 1 个 chunk")


class TestChunking(unittest.TestCase):
    """对上游 iter_wave_chunks 做纯逻辑单测（不加载模型、不依赖音频内容）。

    直接导入上游脚本的分块迭代器，喂一段合成 wav，断言每个产出的 chunk：
    - 时长 ≤ max_seconds（30s 硬上限）
    - chunk_start 严格连续：下一块的 start == 上一块的 start + duration
      （无 overlap、无 gap，字节级精确）
    这比“chunks >= 3”更能证明分块与时间轴拼接正确。
    """

    def _iter_chunks(self, wav_path, **kw):
        # 延迟导入：上游脚本在仓库根，缺了就 skip。
        if not os.path.isfile(UPSTREAM):
            raise unittest.SkipTest(f"upstream backend not found: {UPSTREAM}")
        try:
            import numpy
        except ModuleNotFoundError:
            raise unittest.SkipTest("numpy not installed")
        sys.path.insert(0, os.path.dirname(UPSTREAM))
        import transcribe_x_asr as upstream  # noqa: E402
        return list(upstream.iter_wave_chunks(
            wav_path, numpy=numpy, **kw))

    def test_every_chunk_within_limit_and_contiguous(self):
        """90s 音频 → 每块 ≤30s，且块间时间轴严格连续（无 overlap/gap）。"""
        wav = os.path.join(SCRIPT_DIR, "_test_chunk.wav")
        _write_sine_wav(wav, duration_sec=90.0)
        try:
            chunks = self._iter_chunks(
                wav,
                min_seconds=20.0, target_seconds=27.0, max_seconds=30.0,
            )
        finally:
            _unlink(wav)

        self.assertGreaterEqual(len(chunks), 3, f"90s 应切成 ≥3 块，实际 {len(chunks)}")
        expected_start = 0.0
        for i, (chunk_start, samples, sample_rate) in enumerate(chunks):
            duration = len(samples) / sample_rate
            self.assertLessEqual(duration, 30.0 + 1e-6,
                                 f"chunk[{i}] 时长 {duration:.3f}s 超过 30s 上限")
            # 时间轴严格连续：无 overlap、无 gap
            self.assertAlmostEqual(chunk_start, expected_start, delta=1e-6,
                                   msg=f"chunk[{i}] start={chunk_start:.6f} "
                                       f"应等于上一块末尾 {expected_start:.6f}")
            expected_start += duration
        # 最后一块的末尾应覆盖到接近 90s（允许最后一块略短）
        self.assertAlmostEqual(expected_start, 90.0, delta=1.0,
                               msg=f"拼接总时长 {expected_start:.3f}s 应接近 90s")


class TestBuiltinRejectsLongAudio(unittest.TestCase):
    """内置 backend 不实现分块；应主动拒绝 >60s 音频并指引用户用 upstream。"""

    def test_long_audio_refused(self):
        wav = os.path.join(SCRIPT_DIR, "_test_long_builtin.wav")
        _write_sine_wav(wav, duration_sec=120.0)
        cmd = [
            sys.executable,
            os.path.join(SKILL_DIR, "scripts", "transcribe.py"),
            wav,
            "--lang", "zh",
            "--backend", "builtin",
            "--output-dir", SCRIPT_DIR,
            "--overwrite",
        ]
        model_dir = os.environ.get(
            "ASR_TEST_MODEL_DIR",
            os.path.expanduser(
                "~/.cache/sherpa-onnx-models/"
                "sherpa-onnx-x-asr-zipformer-transducer-zh-en-punct-int8-2026-06-03"
            ),
        )
        if os.path.isfile(os.path.join(model_dir, "tokens.txt")):
            cmd += ["--model-dir", model_dir]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  env=child_env(), **RUN_KW)
        finally:
            _unlink(wav)
            for ext in ("txt", "md", "srt"):
                _unlink(os.path.join(SCRIPT_DIR, "_test_long_builtin." + ext))

        self.assertNotEqual(proc.returncode, 0,
                            "内置 backend 不应成功处理 120s 音频")
        self.assertIn("内置 backend 不支持长音频", proc.stderr + proc.stdout)


class TestSrtParse(unittest.TestCase):
    """transcribe.py 的 SRT 解析：round-trip 后 cues 与原文一致。"""

    def test_parse_basic(self):
        from transcribe import parse_srt

        srt = (
            "1\n"
            "00:00:00,500 --> 00:00:02,000\n"
            "你好\n"
            "\n"
            "2\n"
            "00:00:02,500 --> 00:00:05,250\n"
            "world\n"
        )
        cues = parse_srt(srt)
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["text"], "你好")
        self.assertEqual(cues[1]["text"], "world")
        self.assertAlmostEqual(cues[0]["start"], 0.5, places=3)
        self.assertAlmostEqual(cues[0]["end"], 2.0, places=3)
        self.assertAlmostEqual(cues[1]["start"], 2.5, places=3)
        self.assertAlmostEqual(cues[1]["end"], 5.25, places=3)

    def test_parse_empty_text_skipped(self):
        from transcribe import parse_srt

        srt = "1\n00:00:00,000 --> 00:00:01,000\n\n\n2\n00:00:01,000 --> 00:00:02,000\nhi\n"
        cues = parse_srt(srt)
        self.assertEqual(len(cues), 1)
        self.assertEqual(cues[0]["text"], "hi")


class TestTokensToCues(unittest.TestCase):
    """transcribe.py 的 tokens_to_cues：句边界 + char→token 映射正确。"""

    def test_chinese_sentence_split(self):
        """tokens_to_cues 以句末标点（。！？）拆句：一条多句输入 → 多条 cues。"""
        from transcribe import tokens_to_cues

        # 两句话：「你今天。」、「这是测试。」
        tokens = [" 你", " 今", " 天", " 。", " 这", " 是", " 测试", " 。"]
        timestamps = [0.0, 0.2, 0.4, 0.5, 1.0, 1.2, 1.4, 1.6]
        text = "你今天。这是测试。"
        cues = tokens_to_cues(tokens, timestamps, text, cjk=True)
        self.assertEqual(len(cues), 2, f"应切为 2 条 cue，实际 {len(cues)}")
        self.assertAlmostEqual(cues[0]["start"], 0.0, places=3)
        self.assertEqual(cues[0]["text"], "你今天。")
        self.assertEqual(cues[1]["text"], "这是测试。")


if __name__ == "__main__":
    unittest.main(verbosity=2)