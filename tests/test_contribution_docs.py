from pathlib import Path
import unittest

from scripts.validate_contribution import RIGHTS_MARKER


ROOT = Path(__file__).resolve().parents[1]


class ContributionDocsTests(unittest.TestCase):
    def test_pull_request_template_matches_enforced_policy(self):
        template = (ROOT / ".github/PULL_REQUEST_TEMPLATE/pdf-contribution.md").read_text()
        self.assertIn(RIGHTS_MARKER.replace("[x]", "[ ]"), template)
        self.assertIn("directly under `content/inbox/`", template)
        self.assertIn("25 MiB", template)
        self.assertIn("at most 10 PDFs and 100 MiB total", template)

    def test_contributor_guide_explains_trusted_publish_boundary(self):
        guide = (ROOT / "CONTRIBUTING.md").read_text()
        normalized = " ".join(guide.split())
        for fragment in (
            "unmerged content is never deployed",
            "isolated, unprivileged container",
            "Pages site is built only from merged `main` content",
            "not limits on the course library",
        ):
            self.assertIn(fragment, normalized)


if __name__ == "__main__":
    unittest.main()
