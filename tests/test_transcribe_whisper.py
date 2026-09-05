import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import transcribe_whisper as transcribe


ALL = {"mlx": ["mlx_whisper"], "faster": ["python", "-c", "x"], "openai": ["whisper"]}


class BackendSelectionTests(unittest.TestCase):
    def test_apple_silicon_prefers_mlx(self):
        backend, why = transcribe.select_backend("darwin", "arm64", ALL)
        self.assertEqual(backend, "mlx")
        self.assertIn("Metal", why)

    def test_apple_silicon_without_mlx_falls_back_to_faster_then_openai(self):
        available = dict(ALL, mlx=None)
        self.assertEqual(transcribe.select_backend("darwin", "arm64", available)[0], "faster")
        available["faster"] = None
        self.assertEqual(transcribe.select_backend("darwin", "arm64", available)[0], "openai")

    def test_linux_never_selects_mlx(self):
        self.assertEqual(transcribe.select_backend("linux", "x86_64", ALL)[0], "faster")
        self.assertEqual(transcribe.select_backend("linux", "x86_64", dict(ALL, faster=None))[0], "openai")

    def test_requested_backend_must_be_installed(self):
        self.assertEqual(transcribe.select_backend("linux", "x86_64", ALL, "openai")[0], "openai")
        with self.assertRaises(RuntimeError):
            transcribe.select_backend("linux", "x86_64", dict(ALL, mlx=None), "mlx")

    def test_nothing_installed_is_an_error_with_install_hint(self):
        with self.assertRaises(RuntimeError) as ctx:
            transcribe.select_backend("linux", "x86_64", {"mlx": None, "faster": None, "openai": None})
        self.assertIn("pip install", str(ctx.exception))

    def test_default_models(self):
        self.assertIn("large-v3-turbo", transcribe.default_model("mlx"))
        self.assertEqual(transcribe.default_model("openai"), "small")


class CommandBuildingTests(unittest.TestCase):
    def setUp(self):
        self.audio = Path("/w/audio.wav")
        self.workdir = Path("/w")

    def test_mlx_command_writes_srt_into_workdir_with_progress(self):
        cmd = transcribe.build_command("mlx", ["mlx_whisper"], self.audio, self.workdir, "zh", "m", "术语")
        self.assertEqual(cmd[:2], ["mlx_whisper", "/w/audio.wav"])
        self.assertIn("--output-format", cmd)
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "srt")
        self.assertEqual(cmd[cmd.index("--output-dir") + 1], "/w")
        self.assertEqual(cmd[cmd.index("--verbose") + 1], "True")
        self.assertEqual(cmd[cmd.index("--initial-prompt") + 1], "术语")

    def test_openai_command_disables_fp16_and_uses_underscore_flags(self):
        cmd = transcribe.build_command("openai", ["whisper"], self.audio, self.workdir, "zh", "small")
        self.assertEqual(cmd[cmd.index("--fp16") + 1], "False")
        self.assertEqual(cmd[cmd.index("--output_format") + 1], "srt")
        self.assertNotIn("--initial_prompt", cmd)

    def test_faster_command_passes_output_path_to_runner(self):
        cmd = transcribe.build_command("faster", ["py", "-c", "RUN"], self.audio, self.workdir, "zh", "large-v3-turbo", "")
        self.assertEqual(cmd, ["py", "-c", "RUN", "/w/audio.wav", "large-v3-turbo", "zh", "/w/audio.srt", ""])


class CacheEnvTests(unittest.TestCase):
    def test_writable_home_cache_needs_no_override(self):
        overrides = transcribe.resolve_cache_env(Path("/w"), {}, writable=lambda p, m: True)
        self.assertEqual(overrides, {})

    def test_unwritable_home_cache_moves_caches_under_workdir(self):
        overrides = transcribe.resolve_cache_env(Path("/w"), {}, writable=lambda p, m: False)
        self.assertEqual(overrides["XDG_CACHE_HOME"], "/w/.cache")
        self.assertEqual(overrides["HF_HOME"], "/w/.cache/huggingface")
        self.assertEqual(overrides["HF_HUB_CACHE"], "/w/.cache/huggingface/hub")


class BudgetRunTests(unittest.TestCase):
    def test_budget_kills_silent_backend_and_returns_3(self):
        cmd = [sys.executable, "-c", "import time; time.sleep(30)"]
        log = io.StringIO()
        code, segments = transcribe.run_with_budget(cmd, dict(os.environ), budget_seconds=0.5, log=log, poll_seconds=0.1)
        self.assertEqual((code, segments), (3, 0))

    def test_segments_lift_the_budget(self):
        cmd = [sys.executable, "-c",
               "import time,sys; print('[00:00:00,000 --> 00:00:02,000] hi', flush=True); time.sleep(1.2); print('done')"]
        log = io.StringIO()
        code, segments = transcribe.run_with_budget(cmd, dict(os.environ), budget_seconds=0.3, log=log, poll_seconds=0.1)
        self.assertEqual(code, 0)
        self.assertEqual(segments, 1)
        self.assertIn("done", log.getvalue())


class DryRunTests(unittest.TestCase):
    def test_dry_run_reports_backend_without_running(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            audio.write_bytes(b"")
            captured = io.StringIO()
            real_stdout = sys.stdout
            sys.stdout = captured
            try:
                code = transcribe.main([str(audio), "--workdir", tmp, "--backend", "auto", "--dry-run"])
            finally:
                sys.stdout = real_stdout
            available = transcribe.available_backends()
            if any(available.values()):
                self.assertEqual(code, 0)
                self.assertIn("backend=", captured.getvalue())
                self.assertIn("command:", captured.getvalue())
            else:
                self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
