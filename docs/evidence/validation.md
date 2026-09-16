# Final local validation

Date: 2026-09-16. Result: **build validated; production activation blocked**. No live GitHub approval, comment, reviewer request, code edit or merge was performed.

## Reproducible checks

| Check | Observed result |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests -q` | 39 tests passed on Python 3.12.13 |
| `python3 -m unittest discover -s tests -q` | 39 tests passed on Python 3.9.6 |
| `.venv/bin/mypy jev_review` | All 9 source files passed |
| `.venv/bin/python -m compileall -q jev_review` | Passed |
| Editable package installation with dev dependencies | Passed using uv and Python 3.12 |
| `python -m jev_review review --input examples/review.json` | Valid structured audit; dry-run escalation, no writes |
| `python -m jev_review calibrate --input examples/calibration.json --config examples/calibration-config.json` | Synthetic example correctly reports `ready: false` |
| Workflow YAML parse | Passed; pinned checkout/setup-python revisions verified against upstream tags |
| `git diff --check` | Passed |
| Credential exclusion and exact-value source scan | Passed; local credential file ignored, mode 0600 |
| Local Markdown link and immutable source hash checks | Passed |

The test suite exercises the real provider parser, core policy/calibration, CLI orchestration and injected GitHub transport. It includes eligible active approval, shadow behavior, individual approval-gate mutations, malformed/contradictory data, synthetic/model-drift rejection, freshness and CI identity, changed heads, draft/incomplete PR metadata, approval-context mismatch, reviewer reconciliation, dry-run zero writes and ambiguous POST no-retry. Test-only calibration fixtures are hypothetical and are not production evidence.

## Real Jev observations

[Final integration artifact](live-final-integration-evaluation.json): ten authenticated calls against Jev, concrete model `jev-1.13.0`, prompt `review-v1`, schema `2`; ten completed, ten hand-authored approval labels matched, zero unsafe model approvals. Provider source hash matches the final implementation and did not change during execution. These are ten synthetic snippets, not representative PRs. No claim of production calibration, safe autonomous coverage or routing accuracy follows.

[Observation narrative](live-evaluation.md) preserves earlier results and the original failed request. [Labeling protocol](labeling-protocol.md) defines the representative evaluation still required. The exact one-sided 95% false-approval bound needs at least 299 independent selected approvals with zero errors to fall below 1%; per-field calibration gates must also pass.

## Implementer and reviewer evidence

All delegated implementers and reviewers used Luna with high reasoning, as requested.

- Research/provider implementer: [API research](../research/jev-api.md), [provider evidence](provider.md), [GitHub adapter evidence](github.md).
- Core implementer: [core evidence](core.md), including typed contracts, deterministic policy and calibration.
- Wiki/spec implementer: [wiki](../wiki/index.md), [spec](../../.scratch/jev-autonomous-review/spec.md) and runnable CLI/examples.
- Independent Standards reviewer: [initial findings and implemented fixes](standards-review.md).
- Independent Spec reviewer: [initial findings and implemented fixes](spec-review.md).
- Orchestrator integration: independent approval-gate acceptance tests, real provider experiments, supported-runtime/type checks and evidence reconciliation.

Initial review findings remain in the record; final regression checks include their fixes. Reviewers became implementers for their bounded remediations. This is agent-assisted review, not independent human certification.

## Remaining gates

1. Name the target repository and trusted fallback owners; verify deployment identity, required CI App IDs and branch protection.
2. Obtain representative maintainer labels and untouched held-out data. Freeze the full policy and actual model identity, then pass calibration and selected-approval gates.
3. Observe real repository PRs in shadow mode, measure routing/coverage, then explicitly activate writes and verify rollback.

The bot and workflow default to no writes. [Production DoD](../acceptance.md) remains unchecked. Research → wayfinder map → spec/tickets → implementation is recorded in the wiki and local skill provenance; no repository or human labels were invented to close these gates.
