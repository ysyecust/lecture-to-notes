import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = ROOT / "skills/lecture-to-notes/SKILL.md"
OPENAI_PATH = ROOT / "skills/lecture-to-notes/agents/openai.yaml"
ASSETS_PLACEHOLDER = "/ABSOLUTE/PATH/TO/lecture-to-notes/assets"
X_URL = "https://x.com/person/status/2075594420163092606/video/1"


def bash_blocks(markdown):
    return re.findall(r"```bash\n(.*?)\n```", markdown, re.DOTALL)


def install_skill(temporary_directory):
    install_root = Path(temporary_directory)
    installed_skill = install_root / "lecture-to-notes"
    shutil.copytree(ROOT / "skills/lecture-to-notes", installed_skill)

    assets = installed_skill / "assets"
    for helper in (ROOT / "scripts").glob("*.py"):
        shutil.copy2(helper, assets / helper.name)
    shutil.copy2(ROOT / "scripts/prepare_cover.sh", assets / "prepare_cover.sh")
    shutil.copytree(
        ROOT / "scripts/whisper_prompts",
        assets / "whisper_prompts",
        dirs_exist_ok=True,
    )
    return installed_skill, assets


def run_fresh_zsh(script, working_directory):
    zsh = shutil.which("zsh")
    if zsh is None:
        raise RuntimeError("zsh is required for the documented shell smoke tests")
    environment = {
        "HOME": str(working_directory),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    return subprocess.run(
        [zsh, "-f", "-c", script],
        cwd=working_directory,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


class XSupportDocumentationTests(unittest.TestCase):
    def setUp(self):
        self.readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.skill = SKILL_PATH.read_text(encoding="utf-8")
        self.openai = OPENAI_PATH.read_text(encoding="utf-8")

    def test_readme_and_skill_document_x_contract(self):
        for text in (self.readme, self.skill):
            self.assertIn("X/Twitter", text)
            self.assertIn("video_source.py", text)
            self.assertIn("check_srt_health.py", text)
            self.assertIn("x.com/", text)
            for sample in ("10%", "50%", "90%"):
                self.assertIn(sample, text)

        self.assertIn("/video/<n>", self.skill)
        self.assertIn("Whisper", self.skill)
        self.assertNotIn("| 智能课件裁剪 |", self.readme)

    def test_skill_and_agent_metadata_match_supported_workflow(self):
        frontmatter = self.skill.split("---", 2)[1]
        description = next(
            line for line in frontmatter.splitlines() if line.startswith("description:")
        )
        self.assertTrue(description.startswith("description: Use when"))
        self.assertIn("YouTube", description)
        self.assertIn("Bilibili", description)
        self.assertIn("X/Twitter", description)
        self.assertNotIn("Key features", description)
        self.assertNotIn("fallback", description.lower())

        self.assertIn("X(Twitter)", self.openai)
        self.assertIn("$lecture-to-notes", self.openai)
        self.assertIn("full-frame", self.openai)
        self.assertIn("contact-sheet", self.openai)
        self.assertIn("Whisper", self.openai)
        self.assertNotIn("smart-cropped", self.openai)
        self.assertNotIn("removing the lecturer", self.openai)

    def test_skill_uses_literal_shell_independent_asset_paths(self):
        self.assertIn(
            "resolve the absolute assets directory from the loaded skill.md",
            self.skill.lower(),
        )
        self.assertNotIn("$ASSETS", self.skill)
        self.assertNotIn("$SKILL_DIR", self.skill)
        self.assertNotIn("scripts/", self.skill)

        required_assets = {
            "video_source.py",
            "check_srt_health.py",
            "clean_subs.py",
            "transcribe_x_asr.py",
            "correct_srt.py",
            "llm_correct_srt.py",
            "verify_figures.py",
            "prepare_cover.sh",
            "smart_crop.py",
            "notes-template.tex",
            "whisper_prompts/nju_os.txt",
            "whisper_prompts/glossary_nju_os.json",
        }
        for relative_path in required_assets:
            self.assertIn(f"{ASSETS_PLACEHOLDER}/{relative_path}", self.skill)

    def test_bilibili_multipart_decision_precedes_acquisition(self):
        detect_command = (
            f'python3 "{ASSETS_PLACEHOLDER}/video_source.py" detect "<URL>"'
        )
        probe_command = f'python3 "{ASSETS_PLACEHOLDER}/video_source.py" probe "<URL>"'
        self.assertIn(detect_command, self.skill)
        self.assertIn(probe_command, self.skill)

        detect = self.skill.index(detect_command)
        enumerate_parts = self.skill.index("yt-dlp --flat-playlist --print")
        ask = self.skill.index("STOP and ask the user which part(s) to process")
        part_url = self.skill.index("?p=<n>")
        probe = self.skill.index(probe_command)
        subtitle_acquisition = self.skill.index("Subtitle Acquisition")

        self.assertLess(detect, enumerate_parts)
        self.assertLess(enumerate_parts, ask)
        self.assertLess(ask, part_url)
        self.assertLess(part_url, probe)
        self.assertLess(probe, subtitle_acquisition)
        self.assertNotIn("--no-playlist", self.skill[enumerate_parts:ask])
        self.assertIn("separate working directory and run", self.skill[ask:probe])

        phase_one = self.skill[self.skill.index("### Phase 1") :]
        first_acquisition_command = re.search(
            r"^(?:python3|yt-dlp) .+$", phase_one, re.MULTILINE
        )
        self.assertIsNotNone(first_acquisition_command)
        self.assertEqual(
            detect_command,
            first_acquisition_command.group(0),
        )

    def test_x_caption_commands_and_selection_are_deterministic(self):
        for label in ("manual", "automatic"):
            match = re.search(
                rf"# X/Twitter {label} caption tracks[^\n]*\n(?P<command>yt-dlp[^\n]+)",
                self.skill,
            )
            self.assertIsNotNone(match, label)
            command = match.group("command")
            self.assertIn("--no-playlist", command)
            self.assertIn("<URL>", command)
            self.assertIn('-o "x_caption.%(id)s.%(ext)s"', command)
            expected_flag = "--write-subs" if label == "manual" else "--write-auto-subs"
            self.assertIn(expected_flag, command)

        health_blocks = [
            block for block in bash_blocks(self.skill) if "# X_CAPTION_HEALTH_BLOCK" in block
        ]
        self.assertEqual(1, len(health_blocks))
        health_block = health_blocks[0]
        self.assertRegex(health_block, r'DURATION=.*metadata\.json')
        self.assertIn(
            "find . -maxdepth 1 -type f -name 'x_caption.*.srt' -print > x_caption_candidates.txt",
            health_block,
        )
        self.assertIn('if [ ! -s x_caption_candidates.txt ]; then', health_block)
        self.assertIn(
            "No X caption candidates; continue with local ASR fallback.", health_block
        )
        self.assertIn('while IFS= read -r srt; do', health_block)
        self.assertIn(
            f'python3 "{ASSETS_PLACEHOLDER}/check_srt_health.py" "$srt" --duration "$DURATION"',
            health_block,
        )
        self.assertIn('done < x_caption_candidates.txt', health_block)
        self.assertNotIn("for srt in x_caption.*.srt", self.skill)

        blocks_with_duration = [
            block for block in bash_blocks(self.skill) if "DURATION=" in block
        ]
        self.assertEqual([health_block], blocks_with_duration)
        self.assertIn("x_caption.<id>.<lang>.srt", self.skill)
        self.assertIn("selected_x_caption.txt", self.skill)
        self.assertNotIn("SELECTED_SRT", self.skill)
        self.assertNotIn("subs.srt", self.skill)

        for phrase in (
            "X audio → local ASR",
            "constant-offset alignment",
            "three-point audio/visual validation",
            "provenance disclosure",
        ):
            self.assertIn(phrase, self.skill)

    def test_skill_documents_four_stage_full_frame_workflow(self):
        self.assertIn(
            "Four-Stage Fallback: Manual CC → Automatic Captions → Local ASR → Visual-Only",
            self.skill,
        )
        self.assertNotIn("Three-Level Fallback", self.skill)
        self.assertIn("selected full-frame", self.skill)
        self.assertIn("`figures/` with semantic names", self.skill)
        self.assertIn("count passes density gate", self.skill)
        self.assertIn(
            "`figure_manifest.tsv` and `figure_verification.txt`", self.skill
        )
        self.assertIn("no automatic cropping", self.skill.lower())
        self.assertIn("optional and experimental", self.skill)


class PackagedSkillSmokeTests(unittest.TestCase):
    def test_literal_asset_references_exist_after_install(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            installed_skill, assets = install_skill(temporary_directory)
            installed_text = (installed_skill / "SKILL.md").read_text(encoding="utf-8")
            references = set(
                re.findall(
                    re.escape(ASSETS_PLACEHOLDER)
                    + r"/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)",
                    installed_text,
                )
            )
            self.assertTrue(references)
            for relative_path in sorted(references):
                self.assertTrue((assets / relative_path).exists(), relative_path)

    def test_documented_detector_runs_in_fresh_zsh_after_install(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            installed_skill, assets = install_skill(temporary_directory)
            installed_text = (installed_skill / "SKILL.md").read_text(encoding="utf-8")
            detect_blocks = [
                block
                for block in bash_blocks(installed_text)
                if "video_source.py" in block and 'detect "<URL>"' in block
            ]
            self.assertEqual(1, len(detect_blocks))
            command = detect_blocks[0].replace(ASSETS_PLACEHOLDER, str(assets))
            command = command.replace("<URL>", X_URL)

            completed = run_fresh_zsh(command, Path(temporary_directory))
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("x", completed.stdout.strip())

    def test_caption_health_block_handles_zero_candidates_in_fresh_zsh(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            installed_skill, assets = install_skill(temporary_directory)
            installed_text = (installed_skill / "SKILL.md").read_text(encoding="utf-8")
            health_blocks = [
                block
                for block in bash_blocks(installed_text)
                if "# X_CAPTION_HEALTH_BLOCK" in block
            ]
            self.assertEqual(1, len(health_blocks))
            command = health_blocks[0].replace(ASSETS_PLACEHOLDER, str(assets))

            workdir = Path(temporary_directory) / "zero-captions"
            workdir.mkdir()
            (workdir / "metadata.json").write_text(
                json.dumps({"duration": 100}), encoding="utf-8"
            )
            completed = run_fresh_zsh(command, workdir)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn(
                "No X caption candidates; continue with local ASR fallback.",
                completed.stdout,
            )

    def test_caption_health_block_checks_a_healthy_candidate_in_fresh_zsh(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            installed_skill, assets = install_skill(temporary_directory)
            installed_text = (installed_skill / "SKILL.md").read_text(encoding="utf-8")
            health_blocks = [
                block
                for block in bash_blocks(installed_text)
                if "# X_CAPTION_HEALTH_BLOCK" in block
            ]
            self.assertEqual(1, len(health_blocks))
            command = health_blocks[0].replace(ASSETS_PLACEHOLDER, str(assets))

            workdir = Path(temporary_directory) / "healthy-caption"
            workdir.mkdir()
            (workdir / "metadata.json").write_text(
                json.dumps({"duration": 100}), encoding="utf-8"
            )
            candidate = workdir / "x_caption.demo.en.srt"
            candidate.write_text(
                "1\n00:00:05,000 --> 00:00:15,000\nopening\n\n"
                "2\n00:00:45,000 --> 00:00:55,000\nmiddle\n\n"
                "3\n00:01:25,000 --> 00:01:35,000\nending\n",
                encoding="utf-8",
            )
            completed = run_fresh_zsh(command, workdir)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertIn('"healthy": true', completed.stdout)
            self.assertIn(
                "Structurally healthy candidate: ./x_caption.demo.en.srt",
                completed.stdout,
            )
