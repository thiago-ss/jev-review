import json
import base64
import unittest
from urllib.parse import urlparse

from jev_review.github import GitHubClient, GitHubError


SHA = "a" * 40
HEAD = "b" * 40


class FakeGitHub:
    def __init__(self, pull=None, reviews=None):
        self.calls = []
        self.pull = pull or {"state": "open", "draft": False, "merged_at": None, "title": "T", "body": "B", "base": {"sha": SHA}, "head": {"sha": HEAD}}
        self.reviews = reviews or []

    def __call__(self, request, timeout):
        self.calls.append((request.method, request.full_url, json.loads(request.data.decode()) if request.data else None))
        path = urlparse(request.full_url).path
        if path.endswith("/pulls/1"):
            return 200, {}, json.dumps(self.pull).encode()
        if path.endswith("/pulls/1/files"):
            return 200, {}, json.dumps([{"filename": "src/a.py", "status": "modified", "patch": "@@ -1 +1 @@\n-x\n+y", "additions": 1, "deletions": 1}]).encode()
        if path.endswith("/check-runs"):
            return 200, {}, json.dumps({"check_runs": [{"name": "ci", "head_sha": HEAD, "status": "completed", "conclusion": "success", "app": {"id": 7}, "completed_at": "2099-01-01T00:00:00Z"}]}).encode()
        if path.endswith("/reviews"):
            return 200, {}, json.dumps(self.reviews).encode()
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

    def test_draft_and_missing_patch_fail_closed(self):
        fake = FakeGitHub({"state": "open", "draft": True, "merged_at": None, "base": {"sha": SHA}, "head": {"sha": HEAD}})
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        with self.assertRaises(GitHubError):
            client.snapshot("o/r", 1)


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

    def test_codeowners_read_at_base_sha_routes_trusted_owner(self):
        fake = FakeGitHub()
        client = GitHubClient("token", api_url="https://example.test", transport=fake)
        snap = client.snapshot("o/r", 1)
        self.assertEqual(client.reviewers_for_snapshot(snap, ["@alice"]), ("@alice",))


if __name__ == "__main__":
    unittest.main()
