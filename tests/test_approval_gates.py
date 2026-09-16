"""Independent acceptance checks; in-memory labels are test fixtures only."""
from dataclasses import replace
from datetime import datetime, timezone
import unittest

from jev_review.calibration import CalibrationRecord, summarize
from jev_review.models import parse_pr, parse_review
from jev_review.policy import Action, PolicyConfig, evaluate, policy_fingerprint


class ApprovalGateAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pr = parse_pr({
            "repository": "acceptance/test", "number": 1,
            "base_sha": "b" * 40, "head_sha": "a" * 40,
            "files": [{"path": "README.md", "patch": "@@ -1 +1 @@\n-tyop\n+typo\n", "additions": 1, "deletions": 1}],
        })
        cls.review = parse_review({
            "approve": True, "risk": "low", "approve_confidence": .99, "risk_confidence": .99,
            "required_checklist_items": [{"name": name, "status": "pass", "confidence": .99}
                                         for name in ("correctness", "security", "tests")],
        })
        config = PolicyConfig(
            mode="active", allowlisted_repositories=frozenset({cls.pr.repository}),
            required_checks_by_repo={cls.pr.repository: ("ci",)},
            passed_checks_by_repo={cls.pr.repository: frozenset({"ci"})},
            expected_head_sha_by_repo={cls.pr.repository: cls.pr.head_sha},
            calibration_model_id="test-model", calibration_prompt_version="test-prompt", calibration_schema_version="test-schema",
        )
        cls.config = replace(config, policy_id=policy_fingerprint(config))
        # These hypothetical trusted labels exist only inside tests. They are
        # never persisted as deployable evidence or reported as real samples.
        cls.records = [CalibrationRecord(
            .99, True, field, "test-model", "test-prompt", "test-schema", cls.pr.repository,
            True, False, datetime.now(timezone.utc), field == "approve", "test-pr-" + str(i), cls.config.policy_id,
        ) for i in range(299) for field in ("approve", "risk", "checklist:correctness", "checklist:security", "checklist:tests")]
        cls.report = summarize(cls.records)

    def test_positive_active_and_shadow_paths(self):
        self.assertEqual(evaluate(self.pr, self.review, self.config, self.report).action, Action.AUTO_APPROVE)
        shadow = evaluate(self.pr, self.review, replace(self.config, mode="shadow"), self.report)
        self.assertEqual(shadow.action, Action.SHADOW)
        self.assertFalse(shadow.approve)

    def test_each_approval_gate_blocks_a_previously_eligible_review(self):
        cases = [
            ("wrong repo", replace(self.pr, repository="other/repo"), self.review, self.config, "repository is not allowlisted"),
            ("stale head", replace(self.pr, head_sha="c" * 40), self.review, self.config, "head SHA is not exact trusted SHA"),
            ("CI failure", self.pr, self.review, replace(self.config, passed_checks_by_repo={}), "trusted required CI is not passing"),
            ("risk", self.pr, replace(self.review, risk="high"), self.config, "risk is not low"),
            ("reject", self.pr, replace(self.review, approve=False), self.config, "review did not approve"),
            ("confidence", self.pr, replace(self.review, approve_confidence=.89), self.config, "decision confidence below threshold"),
            ("checklist confidence", self.pr, replace(self.review, required_checklist_items=tuple(replace(i, confidence=.89) for i in self.review.required_checklist_items)), self.config, "checklist confidence below threshold"),
            ("checklist fail", self.pr, replace(self.review, required_checklist_items=tuple(replace(i, status="fail") for i in self.review.required_checklist_items)), self.config, "required checklist has blocker or uncertainty"),
            ("sensitive path", replace(self.pr, files=(replace(self.pr.files[0], path="auth/login.py"),)), self.review, self.config, "sensitive path changed"),
            ("renamed secret", replace(self.pr, files=(replace(self.pr.files[0], previous_path=".env"),)), self.review, self.config, "sensitive path changed"),
        ]
        for name, pr, review, config, reason in cases:
            with self.subTest(name=name):
                result = evaluate(pr, review, config, self.report)
                self.assertEqual(result.action, Action.ESCALATE)
                self.assertIn(reason, result.reasons)

    def test_synthetic_labels_and_model_drift_never_qualify(self):
        synthetic = summarize([replace(row, synthetic=True) for row in self.records])
        result = evaluate(self.pr, self.review, self.config, synthetic)
        self.assertIn("calibration: synthetic evidence", result.reasons)
        drifted = evaluate(self.pr, self.review, replace(self.config, calibration_model_id="new-model"), self.report)
        self.assertIn("calibration: evidence identity mismatch", drifted.reasons)


if __name__ == "__main__":
    unittest.main()
