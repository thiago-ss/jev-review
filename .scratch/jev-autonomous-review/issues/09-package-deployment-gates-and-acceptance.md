# 09: Package deployment gates and acceptance evidence

**What to build:** A deployment and acceptance package that documents configuration gates, least-privilege permissions, dry-run rollout, synthetic checks, audit retention, and the evidence required before enabling live approval for an allowlisted repository.

**Blocked by:** 07, 08

**Status:** implemented locally; production activation gated

- [ ] Deployment checklist requires target repository identity, trusted checks, owner routes, auth, mode, retention, and rollback/disable control.
- [ ] CLI supports `review --input`, `github --repo --pr`, and scheduled `poll`; `--dry-run` is default and `--execute` is required for approval/reviewer-request writes.
- [ ] Dry-run observation precedes any live approval capability.
- [ ] Live approval remains disabled when calibration evidence, representative labels, or configuration is absent.
- [ ] Acceptance record links policy/model/provider versions, test results, calibration report, and audit examples.
- [ ] Documentation states Jev's prohibited side effects and fail-closed behavior.

## Implementation evidence

See [final validation](../../../docs/evidence/validation.md). Checklist above is the original acceptance contract; production-dependent items remain subject to [production DoD](../../../docs/acceptance.md).
