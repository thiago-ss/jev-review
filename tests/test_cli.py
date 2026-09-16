import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jev_review.github import ExecutionResult, GitHubSnapshot, ReviewPlan
from jev_review.models import ChangedFile, ChecklistItem, ChecklistStatus, PullRequest, Review, RiskLevel
from jev_review.provider import JevResult
from jev_review.cli import _github_one


SHA = "a" * 40


def packet():
    return {
        "pr": {
            "repository": "acme/widget", "number": 1, "base_sha": "b" * 40, "head_sha": SHA,
            "files": [{"path": "README.md", "patch": "@@ -1 +1 @@\n-old\n+new\n", "additions": 1, "deletions": 1}],
        },
        "review": {
            "approve": True, "risk": "low", "approve_confidence": .99, "risk_confidence": .99,
            "required_checklist_items": [{"name": "tests", "status": "pass", "confidence": .99}],
        },
        "config": {
            "allowlisted_repositories": ["acme/widget"],
            "required_checks_by_repo": {"acme/widget": ["ci/test"]},
            "passed_checks_by_repo": {"acme/widget": ["ci/test"]},
            "expected_head_sha_by_repo": {"acme/widget": SHA},
        },
    }


class CliTests(unittest.TestCase):
    def test_review_defaults_to_shadow_and_emits_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            json.dump(packet(), handle)
            handle.flush()
            result = subprocess.run([sys.executable, "-m", "jev_review", "review", "--input", handle.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual(body["action"], "escalate")
        self.assertTrue(body["dry_run"])
        self.assertIn("no calibration evidence", body["reasons"])

    def test_review_execute_changes_mode_but_still_has_no_external_write(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as handle:
            json.dump(packet(), handle)
            handle.flush()
            result = subprocess.run([sys.executable, "-m", "jev_review", "review", "--input", handle.name, "--execute"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertEqual(body["action"], "escalate")
        self.assertFalse(body["dry_run"])

    def test_invalid_json_fails_with_nonzero_status(self):
        result = subprocess.run([sys.executable, "-m", "jev_review", "review", "--input", "/does/not/exist"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid JSON input", result.stderr)

    def test_github_path_connects_snapshot_jev_policy_and_dry_run(self):
        pr = PullRequest("acme/widget", 1, "b" * 40, SHA, (ChangedFile("README.md", "@@ -1 +1 @@\n-old\n+new\n", 1, 1),), ("ci",), ("ci",))
        snapshot = GitHubSnapshot(pr, "open", False, False, ("ci",), {"ci": (7,)})
        review = Review(True, RiskLevel.LOW, (ChecklistItem("tests", ChecklistStatus.PASS, .99),), .99, .99)

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def snapshot(self, *args, **kwargs):
                return snapshot

            def build_plan(self, snapshot, decision, *args, **kwargs):
                return ReviewPlan("acme/widget", 1, "b" * 40, SHA, "NONE", "body", "marker")

            def execute(self, plan, dry_run=True):
                return ExecutionResult(dry_run, True, ())

        class FakeProvider:
            def __init__(self, *args, **kwargs):
                pass

            def review_with_result(self, _pr):
                return review, JevResult("jev-1.13.0", {}, {"input_tokens": 1, "output_tokens": 1})

        config = {"allowlisted_repositories": ["acme/widget"], "trusted_checks": {"ci": [7]}}
        with patch("jev_review.github.GitHubClient", FakeClient), patch("jev_review.provider.JevProvider", FakeProvider):
            result = _github_one("acme/widget", 1, execute=False, config_raw=config)
        self.assertEqual(result["provider_model"], "jev-1.13.0")
        self.assertTrue(result["execution"]["dry_run"])

    def test_calibrate_command_reports_readiness_and_metrics(self):
        records = [{"probability": .99, "label": True, "decision": "approve", "model_id": "jev-1.13.0", "prompt_version": "p1", "schema_version": "s1", "repository": "acme/widget", "policy_id": "pol-1", "sample_id": "a" + str(i), "heldout": True, "synthetic": False, "selected": True, "observed_at": "2026-09-16T12:00:00+00:00"} for i in range(299)]
        records += [{"probability": .99, "label": True, "decision": kind, "model_id": "jev-1.13.0", "prompt_version": "p1", "schema_version": "s1", "repository": "acme/widget", "policy_id": "pol-1", "sample_id": kind + str(i), "heldout": True, "synthetic": False, "selected": False, "observed_at": "2026-09-16T12:00:00+00:00"} for kind in ("risk", "checklist:correctness", "checklist:security", "checklist:tests") for i in range(30)]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json") as data, tempfile.NamedTemporaryFile(mode="w", suffix=".json") as config:
            json.dump(records, data)
            json.dump({"repository": "acme/widget", "model_id": "jev-1.13.0", "prompt_version": "p1", "schema_version": "s1", "policy_id": "pol-1", "max_age_days": None}, config)
            data.flush(); config.flush()
            result = subprocess.run([sys.executable, "-m", "jev_review", "calibrate", "--input", data.name, "--config", config.name], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        body = json.loads(result.stdout)
        self.assertTrue(body["ready"], body["reasons"])
        self.assertIn("brier", body["report"])


if __name__ == "__main__":
    unittest.main()
