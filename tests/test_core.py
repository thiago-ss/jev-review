import unittest
from datetime import datetime, timedelta, timezone

from jev_review import *


SHA = "a" * 40


def pr_payload(**file_changes):
    return {
        "repository": "acme/widget", "number": 7, "base_sha": "b" * 40, "head_sha": SHA,
        "files": [{"path": path, "patch": "@@ -1 +1 @@\n-old\n+new\n", "additions": 1, "deletions": 1} for path in (file_changes or {"src/app.py": 1})],
    }


def review_payload(**overrides):
    result = {
        "approve": True, "risk": "low", "approve_confidence": .99, "risk_confidence": .99,
        "required_checklist_items": [{"name": "tests", "status": "pass", "confidence": .99}],
    }
    result.update(overrides)
    return result


class CoreTests(unittest.TestCase):
    def test_parse_rejects_truncated_missing_diff_and_nonfinite(self):
        with self.assertRaises(ValidationError): parse_pr(dict(pr_payload(), truncated=True))
        with self.assertRaises(ValidationError): parse_pr({**pr_payload(), "files": [{"path": "x.py"}]})
        with self.assertRaises(ValidationError): parse_review({**review_payload(), "approve_confidence": float("nan")})

    def test_contradiction_survives_parse_and_escalates(self):
        review = parse_review(review_payload(risk="critical"))
        self.assertTrue(review.contradictory)
        decision = evaluate(pr_payload(), review, PolicyConfig(mode="active"))
        self.assertEqual(decision.action, Action.ESCALATE)

    def test_policy_requires_every_gate(self):
        config = PolicyConfig(
            mode="active", allowlisted_repositories=frozenset({"acme/widget"}),
            required_checks_by_repo={"acme/widget": ("ci/test",)},
            passed_checks_by_repo={"acme/widget": frozenset({"ci/test"})},
            expected_head_sha_by_repo={"acme/widget": SHA},
        )
        d = evaluate(pr_payload(), review_payload(), config)
        self.assertEqual(d.action, Action.ESCALATE)
        self.assertIn("no calibration evidence", d.reasons)

    def test_policy_can_auto_approve_only_with_complete_evidence(self):
        config = PolicyConfig(
            mode="active", allowlisted_repositories=frozenset({"acme/widget"}),
            required_checks_by_repo={"acme/widget": ("ci/test",)},
            passed_checks_by_repo={"acme/widget": frozenset({"ci/test"})},
            expected_head_sha_by_repo={"acme/widget": SHA}, calibration_model_id="jev-1.13.0",
            calibration_prompt_version="p1", calibration_schema_version="s1",
        )
        policy_id = policy_fingerprint(config)
        config = PolicyConfig(**{**config.__dict__, "policy_id": policy_id})
        at = datetime.now(timezone.utc)
        records = [CalibrationRecord(.99, True, "approve", "jev-1.13.0", "p1", "s1", "acme/widget", True, False, at, True, "a" + str(i), policy_id) for i in range(299)]
        records += [CalibrationRecord(.99, True, kind, "jev-1.13.0", "p1", "s1", "acme/widget", True, False, at, False, kind + str(i), policy_id) for kind in ("risk", "checklist:correctness", "checklist:security", "checklist:tests") for i in range(30)]
        checklist = [{"name": name, "status": "pass", "confidence": .99} for name in ("correctness", "security", "tests")]
        decision = evaluate(pr_payload(), review_payload(required_checklist_items=checklist), config, summarize(records))
        self.assertEqual(decision.action, Action.AUTO_APPROVE)

    def test_calibration_exact_bound_and_readiness_rejects_synthetic(self):
        self.assertLess(false_approval_upper_bound(0, 299), .01)
        at = datetime.now(timezone.utc)
        records = [CalibrationRecord(.99, True, "approve", "jev-latest", "p1", "s1", "acme/widget", True, False, at, True, "a0", "policy-1")]
        records += [CalibrationRecord(.99, True, "risk", "jev-latest", "p1", "s1", "acme/widget", True, False, at, False, "r0", "policy-1")]
        records += [CalibrationRecord(.99, True, "checklist:tests", "jev-latest", "p1", "s1", "acme/widget", True, False, at, False, "c0", "policy-1")]
        records += [CalibrationRecord(.99, True, "approve", "jev-latest", "p1", "s1", "acme/widget", True, False, at, True, "a" + str(i), "policy-1") for i in range(1, 299)]
        report = summarize(records)
        ready, reasons = readiness(report, min_samples=299, min_samples_per_decision=1, model_id="jev-latest", prompt_version="p1", schema_version="s1", repository="acme/widget", policy_id="policy-1", required_decisions=("approve", "risk", "checklist:tests"), max_age_days=90)
        self.assertTrue(ready, reasons)
        synthetic = summarize([CalibrationRecord(.99, True, "approve", "jev-latest", "p1", "s1", "acme/widget", True, True, at, True, "s0", "policy-1")])
        self.assertFalse(readiness(synthetic, min_samples=1, min_samples_per_decision=1, policy_id="policy-1", required_decisions=("approve",), model_id="jev-latest", prompt_version="p1", schema_version="s1", repository="acme/widget", max_age_days=None)[0])

    def test_calibration_rejects_duplicate_labeled_sample_ids(self):
        at = datetime.now(timezone.utc)
        rows = [CalibrationRecord(.99, True, "approve", "m", "p", "s", "acme/widget", True, False, at, True, "same", "policy"), CalibrationRecord(.99, True, "approve", "m", "p", "s", "acme/widget", True, False, at, True, "same", "policy"), CalibrationRecord(.99, True, "risk", "m", "p", "s", "acme/widget", True, False, at, False, "same", "policy"), CalibrationRecord(.99, True, "checklist:tests", "m", "p", "s", "acme/widget", True, False, at, False, "same", "policy")]
        report = summarize(rows)
        self.assertFalse(readiness(report, min_samples=1, min_samples_per_decision=1, policy_id="policy", required_decisions=("approve", "risk", "checklist:tests"), model_id="m", prompt_version="p", schema_version="s", repository="acme/widget", max_age_days=None)[0])

    def test_exact_bound_stable_for_large_sample_and_future_rows_rejected(self):
        self.assertLess(false_approval_upper_bound(0, 10000), .001)
        now = datetime.now(timezone.utc)
        row = CalibrationRecord(.99, True, "approve", "m", "p", "s", "acme/widget", True, False, now + timedelta(days=1), True, "x", "policy")
        report = summarize([row])
        ready, reasons = readiness(report, min_samples=1, min_samples_per_decision=1, policy_id="policy", required_decisions=("approve",), model_id="m", prompt_version="p", schema_version="s", repository="acme/widget", max_age_days=90, now=now)
        self.assertFalse(ready)
        self.assertIn("future timestamp", reasons)

    def test_mapping_calibration_requires_explicit_provenance(self):
        with self.assertRaises(ValidationError):
            CalibrationRecord.from_mapping({"probability": .99, "label": True, "model_id": "m", "prompt_version": "p", "schema_version": "s", "repository": "acme/widget"})

    def test_selection_metrics_use_unique_explicit_pr_ids_and_optional_strata(self):
        now = datetime.now(timezone.utc)
        rows = [
            CalibrationRecord(.99, True, "approve", "m", "p", "s", "acme/widget", True, False, now, True, "pr-1", "policy", "security"),
            CalibrationRecord(.50, False, "approve", "m", "p", "s", "acme/widget", True, False, now, False, "pr-2", "policy", "security"),
            CalibrationRecord(.99, True, "risk", "m", "p", "s", "acme/widget", True, False, now, False, "pr-1", "policy", "security"),
        ]
        report = summarize(rows)
        self.assertEqual((report.candidate_prs, report.selected_prs), (2, 1))
        self.assertAlmostEqual(report.coverage, .5)
        self.assertAlmostEqual(report.abstention_rate, .5)
        self.assertEqual(report.selected_error_rate, 0.0)
        self.assertAlmostEqual(report.strata["security"]["coverage"], .5)

    def test_codeowners_only_routes_trusted_entries(self):
        rules = parse_codeowners("*.py @team-python @jev-model\n", {"@team-python"})
        self.assertEqual(route_files(("app.py",), rules), ("@team-python",))


if __name__ == "__main__":
    unittest.main()
