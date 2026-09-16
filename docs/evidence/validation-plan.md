# Validation contract

Implementation baseline: `3b7ec1c`.

All implementation delegates use `gpt-5.6-luna` with `high` reasoning. Parent orchestrates and independently reruns checks. Agent completion messages are not sufficient evidence: record runnable commands, exit status, observed outputs, and limitations.

## Public seams

1. Structured input → validated decision → deterministic disposition and trusted owner routing.
2. Provider HTTP response → strict decision, preserving native probabilities; malformed responses fail closed.
3. GitHub snapshot → decision → fresh-head action plan; dry-run has zero writes, repeated work is idempotent.
4. Labeled evaluation records → calibration report and deployment eligibility.

The user delegated implementation and validation autonomously; these seams are selected under that authorization.

## Evidence levels

- Unit/contract evidence: deterministic examples and fake HTTP boundaries; proves implemented behavior only.
- Live provider smoke: real Jev response over synthetic PR data; proves endpoint/auth/schema compatibility, not real-world accuracy.
- Held-out evaluation: independently labeled target-repository PRs, separated from threshold fitting. Required before production approvals.
- Deployment validation: trusted repository identity, owner rules, CI identities, branch protection, secret provisioning and approved activation. No external review, reviewer request, merge or deployment is performed in this build session.

## Mandatory adversarial cases

Malformed/oversized output, NaN confidence, stale head, draft/closed PR, repo mismatch, missing/failed checks, missing/truncated patches, changed security/config files, PR-supplied instructions, untrusted owner names, empty calibration, synthetic calibration, mismatched model/prompt/schema/repo, duplicate processing and provider failure.

## Completion gates

Local runnable implementation, examples, passing tests, real provider smoke when credentials permit, independently reviewed diff, documented remaining deployment blockers. Never call a synthetic benchmark calibrated production evidence.
