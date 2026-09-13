import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release_notes

RELEASE = ROOT / ".github/workflows/release.yml"
TESTS = ROOT / ".github/workflows/tests.yml"

NOTES = """# Release notes

## v1.1.0 — 2026-10-01 — Second release

- Added a thing.

## v1.0.0 — 2026-09-13 — First release

- First.

### Compatibility

- None.

## 2026-09-11 — Dated entry before versions

- Old.
"""


def fake_repo(tmp, version="1.1.0", notes=NOTES):
    root = Path(tmp)
    (root / "VERSION").write_text(version + "\n", encoding="utf-8")
    (root / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    return root


def run(*argv):
    out = io.StringIO()
    with redirect_stdout(out):
        code = release_notes.main(list(argv))
    return code, out.getvalue()


class RepositoryVersionTests(unittest.TestCase):
    def test_version_file_matches_release_notes(self):
        version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, release_notes.SEMVER)
        self.assertEqual(release_notes.check(ROOT), [])
        self.assertEqual(release_notes.check(ROOT, f"v{version}"), [])
        self.assertTrue(release_notes.find_section(ROOT, f"v{version}")["body"])


class ReleaseNotesTests(unittest.TestCase):
    def test_sections_keep_subsections_and_stop_at_next_heading(self):
        found = release_notes.sections(NOTES)
        self.assertEqual([s["version"] for s in found], ["1.1.0", "1.0.0"])
        self.assertIn("### Compatibility", found[1]["body"])
        self.assertNotIn("Dated entry", found[1]["body"])
        self.assertEqual(found[0]["title"], "Second release")

    def test_problems_are_reported(self):
        cases = (
            ("1.1.0", NOTES, "v1.0.0", "does not match VERSION"),
            ("1.1", NOTES, None, "VERSION must hold MAJOR.MINOR.PATCH"),
            ("1.2.0", NOTES, None, "newest RELEASE_NOTES.md section is v1.1.0"),
            ("1.0.0", NOTES.replace("v1.1.0", "v0.9.0"), None, "newest RELEASE_NOTES.md section is v0.9.0"),
            ("1.1.0", NOTES.replace("v1.0.0", "v1.2.0"), None, "sections must run newest first"),
            ("1.1.0", NOTES.replace("- Added a thing.", ""), None, "section is empty"),
            ("1.1.0", NOTES.replace("2026-10-01", "Oct 1"), None, "is not YYYY-MM-DD"),
            ("1.1.0", NOTES.replace("v1.0.0 — 2026-09-13 — First release", "v1.1.0 — 2026-09-13 — Again"), None, "duplicate section"),
        )
        for version, notes, tag, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as tmp:
                problems = release_notes.check(fake_repo(tmp, version, notes), tag)
                self.assertTrue(any(expected in p for p in problems), problems)

    def test_cli_check_notes_and_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = fake_repo(tmp)
            code, out = run("--root", str(root), "check", "--tag", "v1.1.0")
            self.assertEqual(code, 0, out)
            self.assertIn("PASS VERSION 1.1.0 matches RELEASE_NOTES.md and tag v1.1.0", out)
            self.assertEqual(run("--root", str(root), "check", "--tag", "v1.0.0")[0], 1)
            body = root / "body.md"
            self.assertEqual(run("--root", str(root), "notes", "v1.0.0", "--out", str(body))[0], 0)
            text = body.read_text(encoding="utf-8")
            self.assertIn("- First.", text)
            self.assertIn("### Compatibility", text)
            self.assertNotIn("Old.", text)
            code, out = run("--root", str(root), "title", "v1.1.0")
            self.assertEqual((code, out.strip()), (0, "v1.1.0 — Second release"))
            self.assertEqual(run("--root", str(root), "notes", "v9.9.9")[0], 1)


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_runs_for_version_tags_and_checks_before_publishing(self):
        workflow = RELEASE.read_text(encoding="utf-8")
        for forbidden in ("pull_request", "workflow_run", "self-hosted", "secrets."):
            self.assertNotIn(forbidden, workflow)
        steps = (
            'release_notes.py check --tag "$GITHUB_REF_NAME"',
            'git merge-base --is-ancestor "$GITHUB_SHA" origin/main',
            "PYTHONPATH=. python3 -m unittest discover -s tests",
            'gh release create "$GITHUB_REF_NAME" --verify-tag',
        )
        for required in ('tags:\n      - "v*.*.*"', "permissions:\n  contents: read", "contents: write",
                         "fetch-depth: 0", "persist-credentials: false", *steps):
            self.assertIn(required, workflow)
        positions = [workflow.index(step) for step in steps]
        self.assertEqual(positions, sorted(positions))

    def test_pull_request_checks_run_when_release_files_change(self):
        workflow = TESTS.read_text(encoding="utf-8")
        for path in ('- "VERSION"', '- ".github/workflows/release.yml"'):
            self.assertEqual(workflow.count(path), 2, path)


if __name__ == "__main__":
    unittest.main()
