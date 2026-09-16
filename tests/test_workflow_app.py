import re
import unittest
from pathlib import Path


WORKFLOW = (Path(__file__).parents[1] / ".github" / "workflows" / "jev-review.yml").read_text(encoding="utf-8")
VALIDATE_WORKFLOW = (Path(__file__).parents[1] / ".github" / "workflows" / "validate.yml").read_text(encoding="utf-8")
APP_ACTION = "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1"
CHECKOUT_ACTION = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
PYTHON_ACTION = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"


class GitHubAppWorkflowTests(unittest.TestCase):
    def test_workflow_mints_scoped_app_tokens_for_both_modes(self):
        self.assertEqual(WORKFLOW.count(APP_ACTION), 2)
        self.assertEqual(WORKFLOW.count("client-id: ${{ vars.JEV_APP_CLIENT_ID }}"), 2)
        self.assertEqual(WORKFLOW.count("private-key: ${{ secrets.JEV_APP_PRIVATE_KEY }}"), 2)
        self.assertEqual(WORKFLOW.count("owner: ${{ vars.JEV_APP_INSTALLATION_OWNER }}"), 2)
        self.assertEqual(WORKFLOW.count("repositories: ${{ vars.JEV_APP_INSTALLATION_REPOSITORY }}"), 2)

    def test_permissions_are_explicit_and_mode_specific(self):
        self.assertEqual(WORKFLOW.count("permission-contents: read"), 2)
        self.assertEqual(WORKFLOW.count("permission-checks: read"), 2)
        self.assertEqual(WORKFLOW.count("permission-pull-requests: read"), 1)
        self.assertEqual(WORKFLOW.count("permission-pull-requests: write"), 1)
        # Default workflow tokens are only needed for trusted bot checkout.
        self.assertIn("permissions:\n  contents: read\n\nenv:", WORKFLOW)
        self.assertNotIn("checks: read", WORKFLOW.split("env:", 1)[0])
        self.assertNotIn("pull-requests: write", WORKFLOW.split("jobs:", 1)[0])

    def test_api_steps_use_app_output_and_never_default_token(self):
        self.assertEqual(WORKFLOW.count("GITHUB_TOKEN: ${{ steps.app-token.outputs.token }}"), 2)
        self.assertNotIn("GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}", WORKFLOW)
        self.assertEqual(WORKFLOW.count("persist-credentials: false"), 2)

    def test_target_preflight_binds_configured_repo_to_app_scope(self):
        expected = (
            r"test \"\$JEV_REPOSITORY\" = \"\$JEV_APP_INSTALLATION_OWNER/"
            r"\$JEV_APP_INSTALLATION_REPOSITORY\""
        )
        self.assertEqual(len(re.findall(expected, WORKFLOW)), 2)
        self.assertEqual(WORKFLOW.count("Validate scoped App target"), 2)

    def test_pilot_validation_workflow_has_secret_free_trusted_checks(self):
        self.assertIn("pull_request:", VALIDATE_WORKFLOW)
        self.assertIn("branches: [main]", VALIDATE_WORKFLOW)
        self.assertIn("contents: read", VALIDATE_WORKFLOW)
        self.assertIn('python-version: ["3.9", "3.12"]', VALIDATE_WORKFLOW)
        self.assertIn("timeout-minutes: 15", VALIDATE_WORKFLOW)
        self.assertIn("python -m pip install --disable-pip-version-check -e .", VALIDATE_WORKFLOW)
        self.assertIn("python -m unittest discover -s tests -q", VALIDATE_WORKFLOW)
        self.assertIn("python -m pip install --disable-pip-version-check 'mypy==2.3.1'", VALIDATE_WORKFLOW)
        self.assertIn("python -m mypy jev_review", VALIDATE_WORKFLOW)
        self.assertEqual(VALIDATE_WORKFLOW.count("if: matrix.python-version == '3.12'"), 2)
        self.assertNotIn("secrets.", VALIDATE_WORKFLOW)
        self.assertEqual(VALIDATE_WORKFLOW.count(CHECKOUT_ACTION), 1)
        self.assertEqual(VALIDATE_WORKFLOW.count(PYTHON_ACTION), 1)
        for action in re.findall(r"uses:\s+([^\s]+)", VALIDATE_WORKFLOW):
            self.assertRegex(action, r"@[0-9a-f]{40}$", action)


if __name__ == "__main__":
    unittest.main()
