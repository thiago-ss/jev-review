# 07: Integrate GitHub trigger and trusted checks

**What to build:** A configurable GitHub adapter and trusted-branch scheduled Actions polling/dispatch path that obtains pull-request metadata/diff/review/check evidence, feeds the normalized packet, and performs approval or reviewer-request writes only in explicit execution mode after the deterministic policy passes.

**Blocked by:** 04, 05, 06

**Status:** ready-for-agent

- [ ] Deployment configuration requires explicit target repository, owner routes, auth, trusted-check allowlist, freshness, and mode.
- [ ] Trusted-branch scheduled polling/dispatch is isolated behind provider adapter and documents retry/idempotency behavior; a single CLI path supports review, GitHub review, and poll modes.
- [ ] Approval and reviewer-request mutations are impossible unless `--execute`, target config, and policy decision permit them.
- [ ] Trusted checks require configured identity, passing conclusion, exact evaluated SHA, and freshness.
- [ ] Permission/API failures route safely and cannot produce approval.
- [ ] GitHub reads handle open/draft state, app/check identity, diff truncation, exact SHA revalidation, and idempotent decision keys.
- [ ] No target is hard-coded; synthetic adapter remains runnable.
