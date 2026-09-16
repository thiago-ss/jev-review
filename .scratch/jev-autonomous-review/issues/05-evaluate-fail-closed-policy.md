# 05: Evaluate deterministic fail-closed policy

**What to build:** A pure policy evaluator that turns one normalized Review packet and configuration snapshot into an auditable Decision, approving only when every configured gate passes and otherwise abstaining or requesting human review.

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] Typed outcomes are `approve`, `request-human-review`, and `abstain` with gate-by-gate reasons.
- [ ] Approval fails closed for changed SHA, non-allowlisted repository, high/critical risk, absent calibration evidence, stale/mismatched/untrusted checks, incomplete config, or non-live mode.
- [ ] Decision records evaluated identity, policy/model/provider versions, confidence/calibration status, evidence timestamps, and dry-run marker.
- [ ] Adversarial unit tests prove each gate and combinations of unknown evidence prevent approval.
- [ ] Pure evaluator has no network or mutation side effects.
