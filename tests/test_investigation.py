import unittest

from jev_review.investigation import MAX_DIFF_BYTES, MAX_FILES, investigate
from jev_review.models import ChangedFile, PullRequest
from jev_review.provider import JevProviderError


def make_pr(files=None):
    if files is None:
        files = (ChangedFile("src/app.py", "@@ -1 +1 @@\n-old\n+new\n", 1, 1),)
    return PullRequest("acme/widget", 7, "b" * 40, "a" * 40, tuple(files), title="Change", body="Context")


def answer(choice, labels):
    probabilities = {label: (1.0 if label == choice else 0.0) for label in labels}
    return {"type": "choice", "choice": choice, "probabilities": probabilities, "confidence": 1.0}


def result(files, verdict="approve", risk="low", failure="none", check="none", request_id="req-1", model="model-1"):
    answers = {"verdict": answer(verdict, ("approve", "hold", "review")), "risk": answer(risk, ("low", "medium", "high", "critical"))}
    for index in range(len(files)):
        answers["failure_" + str(index)] = answer(failure, ("none", "correctness", "security", "regression", "test_gap", "context_missing"))
        answers["next_check_" + str(index)] = answer(check, ("unit_boundary", "authorization", "integration", "secret_scan", "manual_context", "none"))
    return {"request_id": request_id, "model": model, "usage": {"input_tokens": 11, "output_tokens": 5}, "answers": answers}


class FakeProvider:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def evaluate(self, state, questions):
        self.calls.append((state, questions))
        response = self.responses[len(self.calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response


class InvestigationTests(unittest.TestCase):
    def test_three_distinct_bounded_perspectives_and_mapping(self):
        pr = make_pr()
        provider = FakeProvider([result(pr.files, request_id="c"), result(pr.files, request_id="s"), result(pr.files, request_id="v")])
        report = investigate(pr, provider)

        self.assertEqual(len(provider.calls), 3)
        self.assertEqual([call[0]["perspective"] for call in provider.calls], ["correctness", "security", "verification"])
        self.assertEqual(len({call[1]["verdict"]["instructions"] for call in provider.calls}), 3)
        self.assertEqual(report["version"], "xray-v1")
        self.assertTrue(report["advisory"])
        self.assertIn("no independence claim", report["correlation_note"])
        self.assertEqual(report["pr"]["files"][0]["path"], "src/app.py")
        self.assertEqual(report["perspectives"]["correctness"]["provenance"]["version"], "xray-v1")
        self.assertEqual(set(report["perspectives"]["correctness"]["provenance"]["questions"]), {"verdict", "risk", "failure_0", "next_check_0"})
        self.assertEqual(report["perspectives"]["correctness"]["answers"]["verdict"]["selected_probability"], 1.0)
        self.assertEqual(report["perspectives"]["security"]["answers"]["verdict"]["probabilities"]["review"], 0.0)
        self.assertEqual(report["perspectives"]["verification"]["files"]["src/app.py"]["failure"]["choice"], "none")

    def test_errors_preserved_without_fake_pass(self):
        pr = make_pr()
        provider = FakeProvider([result(pr.files), JevProviderError("provider unavailable"), result(pr.files, check="unit_boundary")])
        report = investigate(pr, provider)

        security = report["perspectives"]["security"]
        self.assertEqual(security["status"], "error")
        self.assertIn("provider unavailable", security["errors"])
        self.assertNotIn("answers", security)
        self.assertEqual(report["global"]["verdict"]["choice"], "review")
        self.assertIsNone(report["global"]["verdict"]["selected_probability"])
        self.assertIn("perspective_error:security", report["evidence_gaps"])

    def test_disagreement_and_proposals_are_deterministic(self):
        pr = make_pr()
        provider = FakeProvider([
            result(pr.files, verdict="approve", failure="none", check="none"),
            result(pr.files, verdict="hold", risk="high", failure="security", check="secret_scan"),
            result(pr.files, verdict="review", failure="test_gap", check="unit_boundary"),
        ])
        report = investigate(pr, provider)

        self.assertEqual(report["global"]["verdict"]["choice"], "review")
        self.assertEqual(report["disagreement"]["verdict"], ["correctness", "security", "verification"])
        self.assertEqual(report["disagreement"]["files"][0]["path"], "src/app.py")
        self.assertEqual({item["check"] for item in report["recommended_checks"]}, {"secret_scan", "unit_boundary"})
        self.assertTrue(all(item["executed"] is False for item in report["recommended_checks"]))
        self.assertIn("src/app.py:test_gap", report["evidence_gaps"])

    def test_file_limit_reviews_first_eight_and_marks_unreviewed(self):
        files = tuple(ChangedFile("f" + str(i) + ".py", "@@ -1 +1 @@\n-a\n+b\n", 1, 1) for i in range(MAX_FILES + 1))
        provider = FakeProvider([result(files[:MAX_FILES]) for _ in range(3)])
        report = investigate(make_pr(files), provider)

        self.assertEqual(len(provider.calls), 3)
        self.assertFalse(report["scope_complete"])
        self.assertEqual(report["unreviewed_files"], ["f8.py"])
        self.assertEqual(report["global"]["verdict"]["choice"], "review")
        self.assertIsNone(report["global"]["risk"]["choice"])
        self.assertTrue(all(item["status"] == "ok" for item in report["perspectives"].values()))

    def test_diff_limit_marks_scope_incomplete(self):
        patch = "x" * (MAX_DIFF_BYTES + 1)
        # ChangedFile validates a patch but does not impose a size limit.
        file = ChangedFile("large.txt", patch, 0, 0)
        provider = FakeProvider([])
        report = investigate(make_pr((file,)), provider)

        self.assertFalse(report["scope_complete"])
        self.assertEqual(provider.calls, [])
        self.assertEqual(report["scope"]["diff_bytes"], MAX_DIFF_BYTES + 1)
        self.assertEqual(report["global"]["verdict"]["choice"], "review")
        self.assertIn("scope_incomplete", report["evidence_gaps"])


if __name__ == "__main__":
    unittest.main()
