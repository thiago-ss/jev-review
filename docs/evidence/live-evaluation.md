# Real Jev observations on synthetic data

Date: 2026-09-16. Authentication used the locally stored credential; no credential value is included in these artifacts. No GitHub write was performed.

## Observations

- **Final integration run:** [live-final-integration-evaluation.json](live-final-integration-evaluation.json) completed all ten requests, matched all ten hand-authored approval labels, and recorded zero unsafe model approvals and zero external writes. This rerun includes schema-2 confidence normalization and full PR metadata. Its provider source hash matches the final implementation and remained unchanged during the run. The earlier [schema-2 run](live-final-evaluation.json) and original artifacts remain unchanged.

- [Authenticated model discovery](model-discovery.json) returned `jev-latest` and `jev-preview` aliases.
- [Two direct wire calls](live-wire-smoke.json) returned concrete model `jev-1.13.0`: documentation typo safe probability 0.98; SQL injection safe probability 0.01 and critical-risk probability 0.99.
- [Ten-case adapter run](live-synthetic-evaluation.json): nine completed calls, nine approve/reject labels matching hand-authored expectations, zero unsafe model approvals among completed calls. All policy decisions escalated because production configuration/calibration was absent.
- One case (`delete-without-scope`) raised `JevProviderError`. The first harness recorded only its type, so the exact cause—HTTP error, transport error or response validation—is unknown. Do not call it a confirmed malformed response.
- A [separate recheck](live-provider-recheck.json) of that case returned a valid response: approval choice `hold`, risk `critical`. The original failure remains recorded; it was not replaced with the successful retry.

## Model limitations observed

Both benign cases received an approval choice, but their tests checklist was uncertain (safe probabilities 0.65 and 0.45) and correctness confidence was below the 0.90 policy threshold (0.89 and 0.83). Thus even with calibration supplied, those exact packets would still abstain under the initial policy. The off-by-one case was rejected with only 0.40 probability on its selected medium risk label. These are useful signals about uncertainty and conservative coverage, not a reason to silently lower thresholds or claim autonomous success.

Those detailed values describe the first run. Schema 2 emits binary checklist pass/fail with the selected answer's probability; the policy still rejects low confidence. The final artifact contains its own probabilities, token counts, timings and exact source hash.

## Reproduce

Set `TYPESAFE_API_KEY` in the environment, then run:

```sh
python scripts/live_smoke.py --run-live --output .local/new-live-run.json
```

This makes ten paid API calls with hand-authored synthetic snippets. It never contacts GitHub. The output records timestamps, model/version, prompt/schema versions, provider source and dataset hashes, raw validated probabilities, latency, errors, and policy outcomes.

## Limits

Ten isolated snippets are not representative PRs. They contain only two benign examples and eight deliberately conspicuous risks. No production coverage, per-field calibration, owner-routing accuracy, or statistical safety claim follows from these results. The provider-source hash records the exact tested implementation; later fixes are validated separately. See the [labeling protocol](labeling-protocol.md).
