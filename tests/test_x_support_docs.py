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
X_URL = "https://x.com/person/status/2075594420163092606/video/1"


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
        self.assertIn("X/Twitter", self.openai)
        self.assertIn("full-frame", self.openai)
        self.assertIn("contact-sheet", self.openai)
        self.assertIn("Whisper", self.openai)
        self.assertNotIn("smart-cropped", self.openai)
        self.assertNotIn("removing the lecturer", self.openai)

    def test_skill_uses_only_installed_asset_paths(self):
        self.assertIn('SKILL_DIR="<absolute directory containing the loaded SKILL.md>"', self.skill)
        self.assertIn('ASSETS="$SKILL_DIR/assets"', self.skill)
        self.assertNotIn("scripts/", self.skill)

        required_assets = {
            "video_source.py",
            "check_srt_health.py",
            "clean_subs.py",
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
            self.assertIn(f"$ASSETS/{relative_path}", self.skill)

    def test_bilibili_multipart_decision_precedes_acquisition(self):
        detect = self.skill.index('python3 "$ASSETS/video_source.py" detect "<URL>"')
        enumerate_parts = self.skill.index('yt-dlp --flat-playlist --print')
        ask = self.skill.index("STOP and ask the user which part(s) to process")
        part_url = self.skill.index("?p=<n>")
        probe = self.skill.index('python3 "$ASSETS/video_source.py" probe "<URL>"')
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
            'python3 "$ASSETS/video_source.py" detect "<URL>"',
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

        self.assertRegex(self.skill, r'DURATION=.*metadata\.json')
        self.assertIn("x_caption.<id>.<lang>.srt", self.skill)
        self.assertIn("for srt in x_caption.*.srt; do", self.skill)
        self.assertIn(
            'python3 "$ASSETS/check_srt_health.py" "$srt" --duration "$DURATION"',
            self.skill,
        )
        self.assertIn('healthy_candidates+=("$srt")', self.skill)
        self.assertIn('SELECTED_SRT="<one explicitly accepted x_caption path>"', self.skill)
        self.assertNotIn("subs.srt", self.skill)

        for phrase in (
            "X audio → Whisper",
            "constant-offset alignment",
            "three-point audio/visual validation",
            "provenance disclosure",
        ):
            self.assertIn(phrase, self.skill)

    def test_skill_documents_four_stage_full_frame_workflow(self):
        self.assertIn(
            "Four-Stage Fallback: Manual CC → Automatic Captions → Whisper → Visual-Only",
            self.skill,
        )
        self.assertNotIn("Three-Level Fallback", self.skill)
        self.assertIn("selected full-frame", self.skill)
        self.assertIn("Selected full-frame figure assets", self.skill)
        self.assertIn("no automatic cropping", self.skill.lower())
        self.assertIn("optional and experimental", self.skill)


class PackagedSkillSmokeTests(unittest.TestCase):
    def test_documented_asset_references_exist_and_detector_runs_after_install(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
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

            installed_text = (installed_skill / "SKILL.md").read_text(encoding="utf-8")
            references = set(
                re.findall(
                    r"\$ASSETS/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)",
                    installed_text,
                )
            )
            self.assertTrue(references)
            for relative_path in sorted(references):
                self.assertTrue((assets / relative_path).exists(), relative_path)

            completed = subprocess.run(
                [sys.executable, "-S", str(assets / "video_source.py"), "detect", X_URL],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertEqual("x", completed.stdout.strip())
