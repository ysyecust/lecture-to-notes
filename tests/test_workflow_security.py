from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / ".github/workflows/contribution-check.yml"
PAGES = ROOT / ".github/workflows/pages.yml"


class WorkflowSecurityTests(unittest.TestCase):
    def test_contribution_check_uses_trusted_base_and_no_privileged_trigger(self):
        workflow = CHECK.read_text()
        for forbidden in ("pull_request_target", "workflow_run", "self-hosted", "secrets."):
            self.assertNotIn(forbidden, workflow)
        for required in (
            "permissions:\n  contents: read",
            "- content/inbox/*.pdf",
            "trusted/ci/pdf-sandbox.Dockerfile",
            "github.event.pull_request.base.sha",
            "github.event.pull_request.head.sha",
            "persist-credentials: false",
            "--network none",
            "--read-only",
            "--user 65532:65532",
            "--cap-drop ALL",
            "--security-opt no-new-privileges",
            "$GITHUB_EVENT_PATH:/event.json:ro",
        ):
            self.assertIn(required, workflow)

    def test_actions_are_pinned_to_full_commit_shas(self):
        for path in (CHECK, PAGES):
            for line in path.read_text().splitlines():
                if "uses:" not in line:
                    continue
                reference = line.split("uses:", 1)[1].strip()
                self.assertRegex(reference, r"^[^@]+@[0-9a-f]{40}$")

    def test_pages_deploys_only_on_trusted_main_and_validates_outputs(self):
        workflow = PAGES.read_text()
        for required in (
            "branches:\n      - main",
            "sudo apt-get install --yes zsh",
            "PYTHONPATH=. python3 -m unittest discover",
            "./scripts/build_site_container.sh",
            "qpdf --warning-exit-0 --check",
            "npm run test:e2e",
            "actions/deploy-pages@",
        ):
            self.assertIn(required, workflow)
        self.assertNotIn("pull_request:", workflow)


if __name__ == "__main__":
    unittest.main()
