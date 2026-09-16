import json
import unittest

from jev_review.provider import JevProvider, JevProviderError


def response(answers):
    return json.dumps({
        "model": "jev-latest",
        "answers": answers,
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }).encode()


class ProviderTests(unittest.TestCase):
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
