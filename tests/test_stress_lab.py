import json
from pathlib import Path
import tempfile
import unittest

from jev_review import stress_lab
from jev_review.models import parse_pr


class _Result:
    model = "jev-test"
    request_id = "req-test"
    usage = {"input_tokens": 12, "output_tokens": 8}

    def __init__(self, expected):
        disposition = expected["disposition"]
        failure = expected["dominant_failure_class"]
        self.answers = {
            "disposition": {
                "type": "choice", "choice": disposition,
                "probabilities": {name: (0.8 if name == disposition else 0.1) for name in ("approve", "hold", "review")},
                "confidence": 0.8,
            },
            "dominant_failure_class": {
                "type": "choice", "choice": failure,
                "probabilities": {name: (0.5 if name == failure else 0.1) for name in ("none", "auth", "bounds", "data_integrity", "secret", "insufficient")},
                "confidence": 0.5,
            },
            "security": {"type": "noul", "noul": 0.9 if expected["security"] else 0.1},
            "correctness": {"type": "noul", "noul": 0.9 if expected["correctness"] else 0.1},
        }


class _Provider:
    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def evaluate(self, state, questions):
        self.calls.append((state, questions))
        if len(self.calls) == self.fail_at:
            raise RuntimeError("ts_live_super_secret_should_not_appear")
        return _Result(next(f["expected"] for f in stress_lab._FIXTURES if f["state"] is state))


class StressLabTests(unittest.TestCase):
    def test_default_offline_keeps_all_fixtures_without_provider_calls(self):
        provider = _Provider()
        with tempfile.TemporaryDirectory() as directory:
            report = stress_lab.run_experiment(Path(directory) / "evidence.json", provider=provider)
        self.assertEqual(len(stress_lab._FIXTURES), 10)
        self.assertEqual(report["summary"]["offline"], 10)
        self.assertEqual(report["summary"]["api_calls"], 0)
        self.assertEqual(provider.calls, [])
        self.assertTrue(all(row["synthetic"] and row["production_calibration"] is False for row in report["fixtures"]))

    def test_fixtures_parse_with_matching_diff_counts_and_no_labels_in_state(self):
        for fixture in stress_lab._FIXTURES:
            parsed = parse_pr(fixture["state"])
            self.assertEqual(len(parsed.files), 1)
            self.assertEqual(parsed.files[0].additions, fixture["state"]["files"][0]["additions"])
            self.assertEqual(parsed.files[0].deletions, fixture["state"]["files"][0]["deletions"])
            self.assertNotIn("expected", json.dumps(fixture["state"], sort_keys=True))
        for pair_id in ("auth-ownership", "bounds", "monetary-precision", "logging-secret"):
            titles = {fixture["state"]["title"] for fixture in stress_lab._FIXTURES if fixture["pair_id"] == pair_id}
            self.assertEqual(titles, {"Synthetic stress fixture"})

    def test_live_is_one_call_per_fixture_and_records_raw_answers(self):
        provider = _Provider()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            report = stress_lab.run_experiment(path, live=True, provider=provider)
            written = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(provider.calls), 10)
        self.assertEqual(report["summary"]["api_calls"], 10)
        self.assertEqual(report["summary"]["completed"], 10)
        self.assertEqual(report["summary"]["expected_label_matches"], 10)
        self.assertEqual(written["fixtures"][0]["request_id"], "req-test")
        self.assertEqual(written["fixtures"][0]["raw_answers"]["disposition"]["choice"], "approve")

    def test_live_failure_is_retained_and_key_never_enters_evidence(self):
        provider = _Provider(fail_at=4)
        secret = "ts_live_super_secret_should_not_appear"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            report = stress_lab.run_experiment(path, live=True, provider=provider, dotenv=Path(directory) / ".env")
            output = path.read_text(encoding="utf-8")
        failed = [row for row in report["fixtures"] if row["status"] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertEqual(report["summary"]["attempted"], 10)
        self.assertIn("RuntimeError", output)
        self.assertNotIn(secret, output)


if __name__ == "__main__":
    unittest.main()
