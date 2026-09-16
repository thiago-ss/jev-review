# Success criteria and definition of done

## North star

Maximize safe autonomous coverage while the one-sided 95% exact upper bound on false approvals stays ≤1%. Coverage means selected PRs / all eligible PRs in a fixed observation window; publish exclusions and abstentions. [Evaluation protocol](evidence/labeling-protocol.md).

## Product success criteria

| Criterion | Required evidence |
| --- | --- |
| Typed, actionable decisions | Validated Boolean approval, risk enum, named checklist outcomes, per-field probabilities and preserved vendor confidence |
| Safe approval boundary | Complete allowlisted PR, unchanged base/head, trusted fresh CI, low risk, no blockers, thresholds and matching calibrated evidence |
| Useful abstention | Structured reason codes/text, uncertain fields, relevant changed paths and trusted human routes; no fabricated line-level finding |
| Calibration | Held-out per-field Brier/ECE/reliability, enough support in deployed confidence bins, exact selected-approval error bound, no synthetic evidence admitted |
| Nontrivial utility | Report safe coverage and routing accuracy; an always-abstaining bot does not establish production usefulness |
| Operational safety | Dry-run zero writes, no PR code execution, no secret logging, bounded provider requests, stale-event rejection and replay reconciliation |

## Build DoD

- [x] Installable package, runnable offline example and authenticated Jev path.
- [x] Scheduled/dispatch automation template, disabled until trusted configuration exists.
- [x] Public-seam tests demonstrate both eligible approval and every major fail-closed class; dry-run has no writes.
- [x] Static typing and supported-runtime checks pass.
- [x] Real provider observations saved with synthetic labels, timestamps and model identity; failures retained.
- [x] Independent Standards and Spec reviews completed; blocking findings fixed and rechecked.
- [x] Research → decision map → spec → tickets → implementation → evidence links maintained in the LLM wiki.
- [x] No credential is tracked; remaining deployment gates explicitly recorded.

Checked completion and actual command results belong in [final validation evidence](evidence/validation.md), rather than assertions made before tests run.

## Production DoD

- [ ] Named repository, owner routes, required check App IDs and deployment identity verified.
- [ ] Protected trusted bot/config branch; stale review dismissal and required CI enforced by GitHub.
- [ ] Representative independent maintainer labels and adjudication available; untouched evaluation split preserved.
- [ ] Frozen model/prompt/schema/policy identity matches production; per-field calibration and selected-approval bound pass.
- [ ] Shadow observation confirms useful coverage and correct routing on real PRs.
- [ ] Explicit activation of writes and rollback/disable procedure verified.

Production DoD is blocked by missing repository/configuration and labeled data. Synthetic smoke tests cannot close those items.
