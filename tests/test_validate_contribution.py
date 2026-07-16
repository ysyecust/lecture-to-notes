import tempfile
import unittest
from pathlib import Path

from scripts.validate_contribution import (
    MAX_FILE_BYTES,
    RIGHTS_MARKER,
    ContributionError,
    validate_delta,
)
from tests.pdf_factory import write_pdf


class ContributionPolicyTests(unittest.TestCase):
    def roots(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        base = root / "base"
        submission = root / "submission"
        base.mkdir()
        submission.mkdir()
        return temporary, base, submission

    def add_pdf(self, root: Path, relative: str = "content/inbox/lecture.pdf"):
        target = root / relative
        write_pdf(target)
        return target

    def test_accepts_pdf_only_addition_with_rights(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        self.add_pdf(submission)
        result = validate_delta(base, submission, RIGHTS_MARKER)
        self.assertEqual(["content/inbox/lecture.pdf"], result.added_pdfs)

    def test_rejects_code_change_beside_pdf(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        (base / "scripts").mkdir()
        (submission / "scripts").mkdir()
        (base / "scripts/app.py").write_text("safe", encoding="utf-8")
        (submission / "scripts/app.py").write_text("changed", encoding="utf-8")
        self.add_pdf(submission)
        with self.assertRaisesRegex(ContributionError, "only add PDFs"):
            validate_delta(base, submission, RIGHTS_MARKER)

    def test_rejects_missing_rights_checkbox(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        self.add_pdf(submission)
        with self.assertRaisesRegex(ContributionError, "rights declaration"):
            validate_delta(base, submission, "")

    def test_rejects_nested_or_uppercase_pdf(self):
        for relative in (
            "content/inbox/folder/a.pdf",
            "content/inbox/a.PDF",
            "CONTENT/INBOX/a.pdf",
        ):
            with self.subTest(relative=relative):
                temporary, base, submission = self.roots()
                try:
                    self.add_pdf(submission, relative)
                    with self.assertRaisesRegex(ContributionError, "only add PDFs"):
                        validate_delta(base, submission, RIGHTS_MARKER)
                finally:
                    temporary.cleanup()

    def test_rejects_modified_or_deleted_files(self):
        for action in ("modified", "deleted"):
            with self.subTest(action=action):
                temporary, base, submission = self.roots()
                try:
                    existing = self.add_pdf(base, "content/inbox/existing.pdf")
                    mirror = self.add_pdf(submission, "content/inbox/existing.pdf")
                    if action == "modified":
                        mirror.write_bytes(mirror.read_bytes() + b"changed")
                    else:
                        mirror.unlink()
                    self.add_pdf(submission, "content/inbox/new.pdf")
                    with self.assertRaisesRegex(ContributionError, "only add PDFs"):
                        validate_delta(base, submission, RIGHTS_MARKER)
                finally:
                    temporary.cleanup()

    def test_rejects_more_than_ten_files(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        for index in range(11):
            self.add_pdf(submission, f"content/inbox/{index:02d}.pdf")
        with self.assertRaisesRegex(ContributionError, "between 1 and 10"):
            validate_delta(base, submission, RIGHTS_MARKER)

    def test_rejects_file_above_25_mib(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        target = self.add_pdf(submission)
        with target.open("ab") as stream:
            stream.truncate(MAX_FILE_BYTES + 1)
        with self.assertRaisesRegex(ContributionError, "25 MiB"):
            validate_delta(base, submission, RIGHTS_MARKER)

    def test_rejects_existing_basename_case_insensitively(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        self.add_pdf(base, "content/courses/course/Lecture.pdf")
        self.add_pdf(submission, "content/courses/course/Lecture.pdf")
        self.add_pdf(submission, "content/inbox/lecture.pdf")
        with self.assertRaisesRegex(ContributionError, "basename conflicts"):
            validate_delta(base, submission, RIGHTS_MARKER)

    def test_rejects_symlink(self):
        temporary, base, submission = self.roots()
        self.addCleanup(temporary.cleanup)
        outside = Path(temporary.name) / "outside.pdf"
        write_pdf(outside)
        inbox = submission / "content/inbox"
        inbox.mkdir(parents=True)
        (inbox / "linked.pdf").symlink_to(outside)
        with self.assertRaisesRegex(ContributionError, "symlinks"):
            validate_delta(base, submission, RIGHTS_MARKER)


if __name__ == "__main__":
    unittest.main()
