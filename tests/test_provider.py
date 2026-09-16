import json
import unittest

from jev_review.provider import JevProvider, JevProviderError
from jev_review.models import ChangedFile, PullRequest


def response(answers):
    return json.dumps({
        "model": "jev-latest",
        "answers": answers,
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }).encode()


class ProviderTests(unittest.TestCase):
    def test_review_maps_boolean_confidence_to_approve_proposition(self):
        answers = {
            "approval": {"type": "choice", "choice": "review", "probabilities": {"approve": .2, "hold": .3, "review": .5}, "confidence": .5},
            "risk": {"type": "choice", "choice": "low", "probabilities": {"low": 1.0, "medium": 0.0, "high": 0.0, "critical": 0.0}, "confidence": 1.0},
            "correctness": {"type": "noul", "noul": .6},
            "security": {"type": "noul", "noul": .6},
            "tests": {"type": "noul", "noul": .6},
        }
        pr = PullRequest("acme/widget", 1, "b" * 40, "a" * 40, (ChangedFile("README.md", "@@ -1 +1 @@\n-old\n+new\n", 1, 1),))
        provider = JevProvider("test", transport=lambda request, timeout: (200, {}, response(answers)))
        review, _ = provider.review_with_result(pr)
        self.assertFalse(review.approve)
        self.assertAlmostEqual(review.approve_confidence, .8)
        self.assertTrue(all(item.status.value == "pass" for item in review.required_checklist_items))

    def test_valid_response_preserves_native_values(self):
        def transport(request, timeout):
            self.assertEqual(request.full_url, "https://example.test/v1/systemone")
            self.assertEqual(request.get_header("Authorization"), "Bearer test")
            return 200, {"x-typesafe-request-id": "req-1"}, response({
                "decision": {"type": "choice", "choice": "approve", "probabilities": {"approve": 0.8, "hold": 0.2}, "confidence": 0.7},
            })

        result = JevProvider("test", base_url="https://example.test", transport=transport).evaluate(
            "diff", {"decision": {"type": "choice", "instructions": "choose", "criteria": {"approve": None, "hold": None}}}
        )
        self.assertEqual(result.request_id, "req-1")
        self.assertEqual(result.answers["decision"]["probabilities"]["approve"], 0.8)

    def test_malformed_probability_fails_closed(self):
        provider = JevProvider("test", transport=lambda request, timeout: (200, {}, response({
            "decision": {"type": "choice", "choice": "approve", "probabilities": {"approve": 2.0}, "confidence": 1.0},
        })))
        with self.assertRaises(JevProviderError):
            provider.evaluate("diff", {"decision": {"type": "choice"}})

    def test_provider_error_does_not_retry_non_retryable(self):
        calls = []

        def transport(request, timeout):
            calls.append(1)
            return 422, {}, b'{"message":"bad question"}'

        with self.assertRaises(JevProviderError) as raised:
            JevProvider("test", retries=2, transport=transport).evaluate("diff", {"q": {"type": "noul", "instructions": "is this valid?"}})
        self.assertEqual(raised.exception.status, 422)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
