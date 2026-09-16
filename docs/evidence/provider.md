# Provider validation evidence

Implementation: [jev_review/provider.py](/Users/thiago/dev/jev-review/jev_review/provider.py).

The adapter uses only Python standard library HTTP (`urllib`) and accepts an injected transport for deterministic tests. This matches the repository's Python 3.9 compatibility target while the official Python SDK currently documents Python >=3.10.

Local contract checks:

```text
.venv/bin/python -m unittest discover -s tests -v
Ran 3 tests ... OK
```

The tests cover bearer auth and endpoint construction, preserving native probabilities/request IDs, rejecting malformed probability maps, and failing once on non-retryable HTTP 422.

Provider behavior:

- Sends `POST /v1/systemone` with `state`, `model`, and typed `questions`.
- Reads `TYPESAFE_API_KEY`; default model is `jev-latest`, base URL is `https://api.typesafe.ai`, timeout is 10 seconds, and default retry count is 2.
- Retries 408, 429, and 5xx (including documented 529 overload) with bounded exponential backoff and `Retry-After`/`Retry-After-Ms` when provided.
- Rejects non-object JSON, missing fields, unknown answer types, NaN/infinite/out-of-range values, probability maps that do not sum to 1, and mismatched Score legend/probability keys.
- `review(pr)` asks only finite typed questions: approval/risk Choices and correctness/security/tests Nouls. It does not ask Jev to generate review prose or usernames. It maps Noul probabilities to local checklist statuses and puts the selected Choice probabilities into core confidence fields; callers of `evaluate()` retain native Choice/Score `confidence` and all distributions.

Official contract sources:

- [TypeSafe API reference](https://docs.typesafe.ai/api) — endpoint, auth, request/response fields, answer types, errors, retry guidance.
- [TypeSafe Confidence](https://docs.typesafe.ai/confidence) — confidence is derived from Choice/Score distributions; Noul has no separate confidence; thresholds are domain/risk dependent.
- [TypeSafe Python SDK constants](https://docs.typesafe.ai/sdk/python/api/constants) — API base URL, model, and timeout defaults.

No live provider smoke is recorded here because an authenticated response contains account-specific data and this adapter's fake transport tests establish the wire contract. Root may run the authorized synthetic smoke separately; it proves endpoint/auth/schema compatibility only, not review accuracy or calibration.
