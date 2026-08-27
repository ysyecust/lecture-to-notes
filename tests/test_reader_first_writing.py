import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/lecture-to-notes/SKILL.md"
REFERENCE = ROOT / "skills/lecture-to-notes/references/reader-first-writing.md"
OPENAI = ROOT / "skills/lecture-to-notes/agents/openai.yaml"
README = ROOT / "README.md"


class ReaderFirstWritingTests(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL.read_text(encoding="utf-8")
        self.reference = REFERENCE.read_text(encoding="utf-8")
        self.openai = OPENAI.read_text(encoding="utf-8")
        self.readme = README.read_text(encoding="utf-8")

    def test_skill_routes_to_self_contained_reader_first_reference(self):
        self.assertIn(
            "[references/reader-first-writing.md](references/reader-first-writing.md)",
            self.skill,
        )
        self.assertIn("The reference is self-contained", self.skill)
        self.assertTrue(REFERENCE.is_file())
        self.assertIn("reader-first-writing.md", self.readme)

    def test_source_profile_makes_density_gates_content_adaptive(self):
        for mode in ("technical-slide", "conceptual-talk", "mixed"):
            self.assertIn(mode, self.skill)
        for field in (
            "audience",
            "central_question",
            "reader_outcome",
            "visual_teaching_atoms",
            "formula_teaching_atoms",
        ):
            self.assertIn(field, self.skill)
        self.assertIn("never invent", self.skill.lower())
        self.assertIn("low-value talking-head screenshots", self.skill)

    def test_reference_preserves_claim_boundaries_and_improves_flow(self):
        required = (
            "Protect the source",
            "reader's argument map",
            "speech into authored teaching prose",
            "one main job",
            "natural technical Chinese",
            "speaker's claim",
            "note writer's synthesis",
            "Revise in separate passes",
            "automated phrase search",
        )
        for phrase in required:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.reference)

    def test_agent_metadata_promises_reader_first_output(self):
        self.assertIn("reader-first", self.openai)
        self.assertIn("source-faithful", self.openai)
        self.assertIn("without transcript or quota filler", self.openai)

    def test_conceptual_talk_gate_does_not_require_invented_visuals_or_math(self):
        match = re.search(
            r"```bash\npython3 - <<'PY'\n(.*?)\nPY\n",
            self.skill,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "pre-delivery Python gate must remain executable")

        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            (workdir / "figures").mkdir()
            sections = "\n".join(f"\\section{{问题{i}}}" for i in range(5))
            (workdir / "notes.tex").write_text(
                sections + "\n" + "讲" * 3000,
                encoding="utf-8",
            )
            (workdir / "metadata.json").write_text(
                json.dumps({"duration": 3600}),
                encoding="utf-8",
            )
            (workdir / "lecture_profile.json").write_text(
                json.dumps(
                    {
                        "mode": "conceptual-talk",
                        "audience": "first-time reader",
                        "central_question": "Why does the argument matter?",
                        "reader_outcome": "Explain the argument and its boundary",
                        "visual_teaching_atoms": 0,
                        "formula_teaching_atoms": 0,
                    }
                ),
                encoding="utf-8",
            )
            (workdir / "teaching_atoms.tsv").write_text(
                "atom\tstatus\tevidence\n核心论证\tok\tnotes.tex\n",
                encoding="utf-8",
            )
            (workdir / "numerical_claims.tsv").write_text(
                "claim\tvalue\tsource_time\tin_notes\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                ["python3", "-c", match.group(1)],
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("need_figures>=0", completed.stdout)
            self.assertIn("need_math>=0", completed.stdout)
            self.assertIn("OVERALL PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
