import os
from unittest import TestCase, mock

from jev_review.calibration import CalibrationRecord, summarize
from jev_review.github import GitHubError
from jev_review.models import ChangedFile, ChecklistItem, ChecklistStatus, Concern, PullRequest, Review, RiskLevel
from jev_review.policy import Action, PolicyConfig, PolicyDecision
from jev_review.presentation import MAX_MARKDOWN_CHARS, render_review
from jev_review.provider import JevResult


SHA = "a" * 40
HEAD = "b" * 40


def make_pr(path="src/example.py"):
    return PullRequest(
        "thiago-ss/jev-review",
        2,
        SHA,
        HEAD,
        (ChangedFile(path, "@@ -1 +1 @@\n-old\n+new\n", 1, 1),),
        ("CI / test", "lint"),
        ("CI / test",),
        "title",
        "body",
        False,
        "author",
        "main",
        HEAD,
    )


def make_review(*, concerns=(), suggestions=()):
    return Review(
        True,
        RiskLevel.LOW,
        tuple(ChecklistItem(name, ChecklistStatus.PASS, confidence) for name, confidence in (("correctness", .98), ("security", .94), ("tests", .91))),
        .93,
        .97,
        tuple(concerns),
        tuple(suggestions),
        {"approval": .88, "risk": .91},
    )


class PresentationTests(TestCase):
    def test_visual_review_contains_trace_commit_ci_confidence_and_raw_evidence(self):
        provider = JevResult("jev-1.13.0", {"approval": {"probabilities": {"approve": .93}}}, {"input_tokens": 10, "output_tokens": 5}, "req-1")
        with mock.patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "thiago-ss/jev-review", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"}, clear=False):
            body = render_review(make_pr(), make_review(), PolicyDecision(Action.SHADOW, ("shadow mode",)), PolicyConfig(mode="shadow"), provider, ("@maintainers",), "not-verified")

        self.assertIn("## Jev / Review receipt", body)
        self.assertIn("SHADOW", body)
        self.assertIn("Model answer", body)
        self.assertIn("uncalibrated", body)
        self.assertIn("#########", body)
        self.assertIn("Exact head commit `" + HEAD + "`", body)
        self.assertIn("https://github.com/thiago-ss/jev-review/commit/" + HEAD, body)
        self.assertIn("https://github.com/thiago-ss/jev-review/actions/runs/123/attempt/2", body)
        self.assertIn("CI / test", body)
        self.assertIn("PASS", body)
        self.assertIn("Raw structured evidence", body)
        self.assertIn("jev-1.13.0", body)
        self.assertIn("&#64;maintainers", body)

    def test_ascii_receipt_links_real_jobs_without_inventing_test_counts(self):
        evidence = ({"name": "CI / test", "details_url": "https://github.com/thiago-ss/jev-review/actions/runs/12/job/34", "completed_at": "2026-09-16T18:00:00Z", "app_id": 15368},)
        body = render_review(make_pr(), make_review(), PolicyDecision(Action.ESCALATE, ("no calibration",)), PolicyConfig(), check_evidence=evidence)
        self.assertIn("[#########.]", body)
        self.assertIn("[Job logs](https://github.com/thiago-ss/jev-review/actions/runs/12/job/34)", body)
        self.assertIn("not executed tests", body)
        self.assertIn("NOT VERIFIED", body)
        self.assertIn("Review scope / 1 files / +1 -1", body)
        self.assertFalse(any(0x1F000 <= ord(c) <= 0x1FAFF or c in "✅❌⚠❔" for c in body))
        bad = render_review(make_pr(), make_review(), PolicyDecision(Action.SHADOW, ()), PolicyConfig(), check_evidence=({"name": "CI / test", "details_url": "https://evil.example/steal"},))
        self.assertNotIn("evil.example", bad)

    def test_untrusted_markdown_and_mentions_are_inert(self):
        concern = Concern("close ](https://evil.example) <script>alert(1)</script> @everyone", "src/[bad].py", 7, RiskLevel.HIGH)
        review = make_review(concerns=(concern,), suggestions=("`rm -rf` [unsafe] @all",))
        with mock.patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "other/repo", "GITHUB_RUN_ID": "not-a-run"}, clear=False):
            body = render_review(make_pr("src/[bad].py"), review, PolicyDecision(Action.ESCALATE, ("reason ](https://evil.example)",)), PolicyConfig(), None, ("@evil",))

        self.assertNotIn("](https://evil.example)", body.split("```json")[0])
        import json
        raw = json.loads(body.split("```json\n", 1)[1].split("\n```", 1)[0])
        self.assertEqual(raw["review"]["concerns"][0]["message"], concern.message)
        self.assertNotIn("<script>", body)
        self.assertNotIn("@everyone", body)
        self.assertNotIn("@evil", body)
        self.assertIn("&#64;everyone", body)
        self.assertIn("&#64;evil", body)
        self.assertIn("src/&#91;bad&#93;.py", body)

    def test_invalid_actions_context_does_not_create_fake_run_link(self):
        with mock.patch.dict(os.environ, {"GITHUB_SERVER_URL": "https://attacker.example", "GITHUB_REPOSITORY": "thiago-ss/jev-review", "GITHUB_RUN_ID": "123"}, clear=False):
            body = render_review(make_pr(), make_review(), PolicyDecision(Action.SHADOW, ()), PolicyConfig())
        self.assertNotIn("actions/runs", body)
        self.assertIn("Exact head commit", body)  # static github.com link remains valid for validated repo/SHA.

    def test_provider_failure_never_invents_review_fields(self):
        error = GitHubError("provider response contained @secret and <bad>")
        body = render_review(make_pr(), None, PolicyDecision(Action.ESCALATE, ("provider unavailable",)), PolicyConfig(), error)
        self.assertIn("Provider", body)
        self.assertIn("unavailable", body)
        self.assertIn("no model-derived finding was fabricated", body)
        self.assertIn("No typed decision available", body)
        self.assertNotIn("Risk |", body)
        self.assertNotIn("| Approval |", body)
        self.assertIn("&#64;secret", body)
        self.assertIn("&lt;bad&gt;", body)

    def test_calibration_requires_passed_policy_and_reference(self):
        body = render_review(make_pr(), make_review(), PolicyDecision(Action.ESCALATE, ()), PolicyConfig(), calibration_ref="calibration.json")
        self.assertIn("uncalibrated", body)
        self.assertIn("policy evidence is not verified", body)

        verified = render_review(make_pr(), make_review(), PolicyDecision(Action.SHADOW, ()), PolicyConfig(), calibration_ref="calibration.json")
        self.assertIn("calibrated", verified)
        self.assertIn("calibration.json", verified)

    def test_output_is_bounded_for_large_structured_evidence(self):
        suggestions = tuple("s" * 320 for _ in range(12))
        body = render_review(make_pr("x" * 100 + ".py"), make_review(suggestions=suggestions), PolicyDecision(Action.ESCALATE, ("r" * 320,)), PolicyConfig(), None)
        self.assertLessEqual(len(body), MAX_MARKDOWN_CHARS)
        self.assertIn("Advisory suggestions", body)


if __name__ == "__main__":
    import unittest

    unittest.main()
