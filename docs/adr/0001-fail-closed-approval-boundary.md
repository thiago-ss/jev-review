# Fail-closed approval boundary

**Status:** accepted

Jev may emit an approval only from a deterministic policy evaluator after every identity, SHA, repository, risk, confidence, calibration, and trusted-check gate passes; an external approval mutation additionally requires explicit `--execute` and deployment configuration. Missing or stale evidence yields abstention or human routing, because a false approval has a materially higher cost than a missed autonomous approval and the boundary must remain auditable independently of the LLM provider.

**Considered options:** allow the model to approve directly; use a score-only threshold; require a deterministic gate over normalized evidence. The first two make model uncertainty and provenance opaque; the last gives a reviewable, provider-independent safety boundary.

**Consequences:** dry-run is the default; calibration evidence and allowlists are deployment prerequisites; provider changes require reevaluation; Jev never edits, pushes, or merges code, while approval/reviewer-request API mutations are explicit execution-mode side effects.
