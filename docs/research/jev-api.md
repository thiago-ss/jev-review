# Jev / TypeSafe API research

Research date: 2026-09-16. Sources are TypeSafe's first-party site, live developer docs, and the vendor's SDK repository. The docs are current as fetched on this date; re-check before pinning a production contract.

## Integration contract

| Item | Verified contract | Confidence |
| --- | --- | --- |
| HTTP endpoint | `POST https://api.typesafe.ai/v1/systemone` | High |
| Authentication | `Authorization: Bearer <API_KEY>`; JSON requests use `Content-Type: application/json` | High |
| API key | Create/manage from `https://console.typesafe.ai/`; SDK reads `TYPESAFE_API_KEY` | High |
| Model | Request `model` is required by HTTP docs; documented alias is `jev-latest`. Live synthetic smoke on 2026-09-16 returned concrete `model: "jev-1.13.0"` for that alias. | High |
| Request | Required `state` (`string \| object \| array`) and nonempty `questions` map; each key is returned unchanged in `answers` | High |
| Question types | `noul`, `choice`, `score`; each has required `type` and `instructions`, with type-specific `criteria` | High |
| Response | `{model, answers, usage}`; `usage` has `input_tokens` and `output_tokens` | High |
| Decision output | `choice` returns selected key, full probabilities, confidence; `score` returns weighted score, legend, probabilities, confidence; `noul` returns `noul` in `[0,1]` | High |
| Retryable service errors | `429` rate limit and `529` overload; use exponential backoff. SDK default retry policy also includes `408` and all `5xx` | High |
| Published quotas | No numeric request rate, token, question-count, payload-size, or context-window limit found in the API docs/SDK docs | High (absence from checked docs) |
| Availability | Public docs and console login are live. The marketing home still says “Join Waitlist,” while Quick Start tells users to create a key in the dashboard. Access therefore appears account-gated/early-access despite a working authenticated endpoint; provision a key before deployment. | Medium |

The authenticated model listing currently exposes Jev model metadata, including a release date, but no immutable version selector is documented. Bind calibration/evaluation records to the response's concrete `model` value and the exact request question schema; do not assume `jev-latest` is immutable. The live smoke evidence is synthetic and validates transport/schema only: [model discovery](../evidence/model-discovery.json) and [live wire smoke](../evidence/live-wire-smoke.json).

HTTP reference: [TypeSafe API reference](https://docs.typesafe.ai/api). Quick Start independently shows the endpoint, bearer header, cURL body, and response example: [Quick start](https://docs.typesafe.ai/introduction/quickstart).

## Wire format

Minimal request for a code review bot:

```json
{
  "state": {
    "repository": "org/repo",
    "pull_request": 123,
    "diff": "...unified diff...",
    "file_context": "...relevant surrounding code...",
    "policy": "Find correctness, security, and regression risks. Ignore style-only issues."
  },
  "model": "jev-latest",
  "questions": {
    "should_comment": {
      "type": "choice",
      "instructions": "What action should the review bot take for this change?",
      "criteria": {
        "comment": "A concrete correctness, security, or regression finding is supported by the supplied evidence",
        "approve": "No actionable finding is supported by the supplied evidence",
        "review": "Evidence is insufficient or ambiguous; route to human review"
      }
    },
    "severity": {
      "type": "score",
      "instructions": "How severe is the most important supported finding?",
      "criteria": ["No actionable finding", "Minor", "Major", "Critical"]
    },
    "has_security_risk": {
      "type": "noul",
      "instructions": "Does the supplied change introduce a security risk?",
      "criteria": {
        "true": "A concrete exploit, exposure, or security control bypass is supported",
        "false": "No security risk is supported by the supplied evidence"
      }
    }
  }
}
```

The bot should validate that selected `choice` values are members of its criteria, that probability maps cover the defined options/levels and sum to approximately 1, and that answer `type` matches the requested question. Those checks are client-side hardening; the API docs state the output shape but do not promise a separate schema-validation endpoint.

The HTTP response shape is:

```json
{
  "model": "jev-latest",
  "answers": {
    "should_comment": {
      "type": "choice",
      "choice": "review",
      "probabilities": {"comment": 0.31, "approve": 0.12, "review": 0.57},
      "confidence": 0.57
    },
    "severity": {
      "type": "score",
      "score": 1.2,
      "legend": {"0": "No actionable finding", "1": "Minor", "2": "Major", "3": "Critical"},
      "probabilities": {"0": 0.2, "1": 0.4, "2": 0.3, "3": 0.1},
      "confidence": 0.64
    },
    "has_security_risk": {"type": "noul", "noul": 0.18}
  },
  "usage": {"input_tokens": 1200, "output_tokens": 90}
}
```

Do not treat this example's numbers as expected behavior. The API reference says Choice probabilities are floats summing to 1; Score is probability-weighted and can fall between rubric levels; Noul is a yes probability.

Observed live behavior: two synthetic requests using `model: "jev-latest"` returned HTTP 200 and `model: "jev-1.13.0"`; the benign documentation typo received Noul approval probability `0.98` and low risk, while the synthetic SQL string-concatenation change received approval probability `0.01` and critical risk probability `0.99`. These are transport examples, not accuracy or calibration evidence.

## Confidence and calibration semantics

TypeSafe says calibration is a model-training goal called Reinforcement Learning for Calibrated Decisions (RLCD), and says every decision includes an uncertainty estimate. The operational docs make the narrower, implementable claim: Choice and Score `confidence` is a statistic derived from the returned distribution; the exact computation is not specified. Noul has no separate `confidence` field. Sources: [TypeSafe home](https://typesafe.ai/) and [Confidence](https://docs.typesafe.ai/confidence).

Use the full distribution when it matters. A concentrated distribution generally means higher confidence; a flat distribution means lower confidence. TypeSafe's example uses `< 0.5` as a “do not guess” floor and `> 0.9` before a high-stakes action, but explicitly says thresholds depend on domain, observed performance, and consequences. These values are examples, not universal calibration guarantees.

The review policy must own thresholds and actions. Jev should return native probabilities/confidence; policy code decides whether to approve, escalate, or shadow after applying locally held-out calibration and repository/CI checks. A Noul near 0.5 is ambiguous and should be routed according to that policy. Calibrate thresholds against labeled pull requests and measure false positives/negatives. Confidence indicates distribution concentration/uncertainty, not correctness, permission to act, or proof that a finding exists.

## SDKs and runtime choices

### Python

The official Python package is `typesafe-sdk`; current docs require Python `>=3.10`, read `TYPESAFE_API_KEY`, default base URL `https://api.typesafe.ai`, default model `jev-latest`, and default per-operation timeout `10.0` seconds. Both sync and async clients expose `system_one(state, questions, ...)`. Source: [Python SDK](https://docs.typesafe.ai/sdk/python), [Python constants](https://docs.typesafe.ai/sdk/python/api/constants), [Python client reference](https://docs.typesafe.ai/sdk/python/api/clients/sync/client).

```python
from typesafe_sdk import Choice, TypeSafeClient

with TypeSafeClient() as client:
    result = client.system_one(
        state={"diff": unified_diff},
        questions={
            "action": Choice(
                instructions="What should the review bot do?",
                criteria={
                    "comment": "Supported actionable finding",
                    "approve": "No actionable finding",
                    "review": "Insufficient evidence",
                },
            )
        },
    )
    answer = result.choices["action"]
    selected = answer.choice
    confidence = answer.confidence
```

The Python SDK's default `RetryPolicy` is `max_retries=2`, `backoff_initial=0.5s`, `backoff_max=5.0s`, `backoff_jitter=0.25`, status set `{408, 429} ∪ {500..599}`, honors `Retry-After`/`retry-after-ms`, and retries connection/timeout errors. Source: [RetryPolicy](https://docs.typesafe.ai/sdk/python/api/retries). The API docs specifically call out exponential backoff for `429` and `529`; the SDK's default all-5xx rule covers `529`.

### JavaScript / TypeScript

The official package is `@typesafe-ai/sdk`; current docs require Node.js 20 or newer, read `TYPESAFE_API_KEY`, and provide typed ESM/CommonJS/TypeScript declarations. Source: [JavaScript SDK docs](https://docs.typesafe.ai/sdk/javascript), [official SDK repository](https://github.com/typesafe-ai/typesafe-sdk-js).

```ts
import { choice, TypeSafeClient } from "@typesafe-ai/sdk";

const client = new TypeSafeClient();
const response = await client.systemOne({
  state: { diff: unifiedDiff },
  questions: {
    action: choice("What should the review bot do?", {
      comment: "Supported actionable finding",
      approve: "No actionable finding",
      review: "Insufficient evidence",
    }),
  },
});

const answer = response.answers.action;
```

For this repository's Python `>=3.9` compatibility target, direct HTTP is the lowest-risk integration: it avoids requiring the vendor SDK's Python `>=3.10` floor. If the project raises its floor, use the SDK for typed parsing and retry behavior. Keep API keys server-side/CI-side; never send them to a browser or expose them in GitHub comments/logs.

## Errors, observability, and limits

Documented HTTP errors are `401` (missing/invalid key), `422` (body/question validation), `429` (rate limit), and `529` (temporary overload). The Python SDK also exposes response status, JSON body, headers, endpoint, and the `x-typesafe-request-id` request ID on API errors. Source: [API errors](https://docs.typesafe.ai/api), [Python exceptions](https://docs.typesafe.ai/sdk/python/api/exceptions).

No numeric rate limit, maximum state size, maximum token count, maximum question count, concurrency limit, retention guarantee, region/SLA, or production pricing was found in the checked first-party API/SDK docs. Do not bake guessed values into the bot. Implement bounded local request size, timeout, retry/backoff, and concurrency; surface `429`/`529` as a non-blocking review-service failure. Record request IDs and token usage without recording secrets.

The marketing page currently advertises `$42` per billion input tokens, but this is a marketing claim without a linked pricing/contract page in the checked sources. Verify account-specific pricing before using it for budgeting: [TypeSafe home](https://typesafe.ai/).

## Recommended bot decomposition

Send one request containing the diff plus only relevant file context and policy. Fan out independent judgments in one call: action (`Choice`), severity (`Score`), and security risk (`Noul`). TypeSafe documents that questions in one request are evaluated independently and in parallel against the same state. Combine results in deterministic code, require evidence-backed findings before posting, and route low-confidence/ambiguous cases to a human. Source: [Introduction](https://docs.typesafe.ai/introduction), [Confidence](https://docs.typesafe.ai/confidence), [How to build with System One](https://docs.typesafe.ai/concepts/how-to-build-with-system-one).

Jev returns decisions, not review prose or line-specific comments. The bot must generate/render any GitHub comment itself from the diff and deterministic metadata, and should refuse to invent locations or explanations when the supplied state lacks evidence.
