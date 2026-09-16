import json
import base64
from dataclasses import replace
from datetime import datetime, timezone
import unittest
from urllib.parse import urlparse

from jev_review.calibration import CalibrationRecord, summarize
from jev_review.github import ApprovalContext, GitHubClient, GitHubError, ReviewPlan
from jev_review.models import ChecklistItem, ChecklistStatus, Review, RiskLevel
from jev_review.policy import Action, PolicyConfig, PolicyDecision, policy_fingerprint


SHA = "a" * 40
HEAD = "b" * 40


class FakeGitHub:
    def __init__(self, pull=None, reviews=None):
        self.calls = []
        self.pull = pull or {"state": "open", "draft": False, "merged_at": None, "title": "T", "body": "B", "base": {"sha": SHA}, "head": {"sha": HEAD}}
        self.reviews = reviews or []
        self.check_completed_at = "2099-01-01T00:00:00Z"
        self.check_runs = None
        self.requested = {"users": [], "teams": []}
        self.pull_count = 0
        self.latest_pull = None

    def __call__(self, request, timeout):
        self.calls.append((request.method, request.full_url, json.loads(request.data.decode()) if request.data else None))
        path = urlparse(request.full_url).path
        if path.endswith("/pulls/1"):
            self.pull_count += 1
            if self.pull_count > 1 and self.latest_pull is not None:
                return 200, {}, json.dumps(self.latest_pull).encode()
            return 200, {}, json.dumps(self.pull).encode()
        if path.endswith("/pulls/1/files"):
            return 200, {}, json.dumps([{"filename": "src/a.py", "status": "modified", "patch": "@@ -1 +1 @@\n-x\n+y", "additions": 1, "deletions": 1}]).encode()
        if path.endswith("/check-runs"):
            runs = self.check_runs if self.check_runs is not None else [{"name": "ci", "head_sha": HEAD, "status": "completed", "conclusion": "success", "app": {"id": 7}, "completed_at": self.check_completed_at}]
            return 200, {}, json.dumps({"check_runs": runs}).encode()
        if path.endswith("/reviews"):
            return 200, {}, json.dumps(self.reviews).encode()
        if path.endswith("/requested_reviewers"):
            if request.method == "GET":
                return 200, {}, json.dumps(self.requested).encode()
            return 201, {}, b'{}'
        if "/contents/" in path:
            if path.endswith("/.github/CODEOWNERS"):
                return 200, {}, json.dumps({"encoding": "base64", "content": base64.b64encode(b"*.py @alice\n").decode()}).encode()
            return 404, {}, b'{"message":"Not Found"}'
        if path.endswith("/user"):
            return 200, {}, b'{"login":"jev-bot"}'
        if request.method == "POST":
            return 201, {}, b'{}'
        raise AssertionError("unexpected " + request.full_url)


class GitHubTests(unittest.TestCase):
    def test_snapshot_requires_exact_app_and_sha(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        self.assertEqual(snap.pull_request.head_sha, HEAD)
        self.assertEqual(snap.pull_request.passed_checks, ("ci",))

        fake.pull["head"]["sha"] = "c" * 40
        self.assertEqual(client.snapshot("o/r", 1, {"ci": [7]}).pull_request.passed_checks, ())

    def test_snapshot_collects_bounded_check_run_evidence(self):
        fake = FakeGitHub()
        fake.check_runs = [{
            "name": "ci",
            "head_sha": HEAD,
            "status": "completed",
            "conclusion": "success",
            "app": {"id": 7},
            "completed_at": "2099-01-01T00:00:00Z",
            "details_url": "https://github.com/o/r/actions/runs/12/job/34",
            "output": {"title": "CI title", "summary": "S" * 1000},
        }]
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        evidence = client.snapshot("o/r", 1, {"ci": [7]}).check_evidence
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["name"], "ci")
        self.assertEqual(evidence[0]["status"], "completed")
        self.assertEqual(evidence[0]["conclusion"], "success")
        self.assertEqual(evidence[0]["head_sha"], HEAD)
        self.assertEqual(evidence[0]["app_id"], 7)
        self.assertEqual(evidence[0]["completed_at"], "2099-01-01T00:00:00Z")
        self.assertEqual(evidence[0]["details_url"], "https://github.com/o/r/actions/runs/12/job/34")
        self.assertTrue(evidence[0]["trusted"])
        self.assertEqual(evidence[0]["title"], "CI title")
        self.assertEqual(evidence[0]["summary"], "S" * 320)

    def test_missing_or_untrusted_check_metadata_never_claims_passed(self):
        for runs in (
            [],
            [{"name": "ci", "head_sha": HEAD, "status": "completed", "conclusion": "success", "app": {"id": 99}}],
            [{"name": "ci", "status": "completed", "conclusion": "success", "app": {"id": 7}}],
        ):
            with self.subTest(runs=runs):
                fake = FakeGitHub()
                fake.check_runs = runs
                client = GitHubClient("token", api_url="https://example.test", transport=fake)
                snap = client.snapshot("o/r", 1, {"ci": [7]})
                self.assertEqual(snap.pull_request.passed_checks, ())
                self.assertEqual(len(snap.check_evidence), 1)
                self.assertFalse(snap.check_evidence[0]["trusted"])

    def test_draft_and_missing_patch_fail_closed(self):
        fake = FakeGitHub({"state": "open", "draft": True, "merged_at": None, "base": {"sha": SHA}, "head": {"sha": HEAD}})
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        with self.assertRaises(GitHubError):
            client.snapshot("o/r", 1)

    def test_missing_reviewability_metadata_fails_closed(self):
        pull = {"state": "open", "base": {"sha": SHA}, "head": {"sha": HEAD}}
        client = GitHubClient("token", api_url="https://example.test", transport=FakeGitHub(pull))
        with self.assertRaises(GitHubError):
            client.snapshot("o/r", 1)

    def test_missing_latest_reviewability_metadata_fails_closed(self):
        fake = FakeGitHub()
        fake.latest_pull = {"state": "open", "base": {"sha": SHA}, "head": {"sha": HEAD}}
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        with self.assertRaises(GitHubError):
            client.snapshot("o/r", 1)

    def test_freshness_override_cannot_disable_stale_checks(self):
        fake = FakeGitHub()
        fake.check_completed_at = "2000-01-01T00:00:00Z"
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        self.assertEqual(client.snapshot("o/r", 1, {"ci": [7]}, None).pull_request.passed_checks, ())
        with self.assertRaises(GitHubError):
            client.snapshot("o/r", 1, {"ci": [7]}, float("nan"))

    def test_pending_latest_check_does_not_fall_back_to_old_success(self):
        fake = FakeGitHub()
        fake.check_runs = [
            {"id": 1, "name": "ci", "head_sha": HEAD, "status": "completed", "conclusion": "success", "app": {"id": 7}, "completed_at": "2099-01-01T00:00:00Z"},
            {"id": 2, "name": "ci", "head_sha": HEAD, "status": "in_progress", "conclusion": None, "app": {"id": 7}, "started_at": "2099-01-02T00:00:00Z"},
        ]
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        self.assertEqual(client.snapshot("o/r", 1, {"ci": [7]}).pull_request.passed_checks, ())


    def test_dry_run_has_no_post_and_marker_is_idempotent(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake, bot_login="jev-bot")
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        plan = client.build_plan(snap, "escalate", trusted_reviewers=(), summary="finding")
        result = client.execute(plan, dry_run=True)
        self.assertFalse(result.skipped)
        self.assertFalse(any(method == "POST" for method, _, _ in fake.calls))

        fake.reviews = [{"body": plan.body, "user": {"login": "jev-bot"}}]
        result = client.execute(plan, dry_run=False)
        self.assertTrue(result.skipped)
        self.assertFalse(any(method == "POST" for method, _, _ in fake.calls))

    def test_untrusted_reviewer_rejected(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        with self.assertRaises(GitHubError):
            client.build_plan(snap, "escalate", reviewers=["attacker"], trusted_reviewers=["team"])

    def test_approval_requires_typed_policy_context_and_cannot_be_forged(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake, bot_login="jev-bot")
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        with self.assertRaises(GitHubError):
            client.build_plan(snap, "auto_approve", allowlisted_repositories=["o/r"])

        forged = ReviewPlan("o/r", 1, SHA, HEAD, "APPROVE", "body", "marker", required_checks=("ci",), trusted_check_app_ids={"ci": (7,)}, allowlisted_repositories=("o/r",))
        with self.assertRaises(GitHubError):
            client.execute(forged, dry_run=False)

    def test_approval_rejects_plan_or_context_check_mismatch(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake, bot_login="jev-bot")
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        review = Review(True, RiskLevel.LOW, (ChecklistItem("tests", ChecklistStatus.PASS, .99),), .99, .99)
        policy = PolicyConfig(mode="active", allowlisted_repositories=frozenset({"o/r"}), required_checks_by_repo={"o/r": ("ci",)}, passed_checks_by_repo={"o/r": frozenset({"ci"})}, expected_head_sha_by_repo={"o/r": HEAD})
        policy = replace(policy, policy_id=policy_fingerprint(policy))
        record = CalibrationRecord(.99, True, "approve", "m", "p", "s", "o/r", True, False, datetime.now(timezone.utc), True, "sample", policy.policy_id)
        context = ApprovalContext(review, policy, summarize([record]))
        decision = PolicyDecision(Action.AUTO_APPROVE, (), True)
        plan = client.build_plan(snap, decision, allowlisted_repositories=["o/r"], approval_context=context)
        forged = replace(plan, required_checks=())
        with self.assertRaises(GitHubError):
            client.execute(forged, dry_run=False)

    def test_ambiguous_post_is_not_retried(self):
        fake = FakeGitHub()
        posts = []

        def transport(request, timeout):
            if request.method == "POST":
                posts.append(request.full_url)
                raise OSError("connection dropped after write")
            return fake(request, timeout)

        client = GitHubClient("token", api_url="https://example.test", transport=transport, bot_login="jev-bot")
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        plan = client.build_plan(snap, "escalate", allowlisted_repositories=["o/r"])
        with self.assertRaises(GitHubError):
            client.execute(plan, dry_run=False)
        self.assertEqual(len(posts), 1)

    def test_marker_present_recovers_missing_reviewer_request(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake, bot_login="jev-bot")
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        plan = client.build_plan(snap, "escalate", reviewers=["alice"], trusted_reviewers=["alice"], allowlisted_repositories=["o/r"])
        fake.reviews = [{"body": plan.body, "user": {"login": "jev-bot"}}]
        result = client.execute(plan, dry_run=False)
        self.assertTrue(result.skipped)
        posts = [call for call in fake.calls if call[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertTrue(posts[0][2]["team_reviewers"] == [] and posts[0][2]["reviewers"] == ["alice"])

    def test_completed_owner_review_satisfies_request_after_pending_request_disappears(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake, bot_login="jev-bot")
        snap = client.snapshot("o/r", 1, {"ci": [7]})
        plan = client.build_plan(snap, "escalate", reviewers=["alice"], trusted_reviewers=["alice"], allowlisted_repositories=["o/r"])
        fake.reviews = [
            {"body": plan.body, "user": {"login": "jev-bot"}},
            {"user": {"login": "alice"}, "commit_id": HEAD, "state": "APPROVED"},
        ]
        result = client.execute(plan, dry_run=False)
        self.assertTrue(result.skipped)
        self.assertFalse(any(method == "POST" for method, _, _ in fake.calls))

    def test_codeowners_read_at_base_sha_routes_trusted_owner(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        snap = client.snapshot("o/r", 1)
        self.assertEqual(client.reviewers_for_snapshot(snap, ["@alice"]), ("@alice",))


if __name__ == "__main__":
    unittest.main()
