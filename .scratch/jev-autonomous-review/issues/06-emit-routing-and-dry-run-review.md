# 06: Emit structured routing and dry-run review

**What to build:** A review result that presents Jev's typed Decision, findings, risk, confidence, checklist, provenance, and an actionable owner route for non-approvals while preserving dry-run behavior and optional output-only suggestions.

**Blocked by:** 04, 05

**Status:** implemented locally; production activation gated

- [ ] Approval, abstention, and human-review outputs share a documented auditable shape.
- [ ] Human route preserves finding locations/rationale/evidence, risk, confidence, checklist, urgency, and suggested trusted owners.
- [ ] Suggestions are clearly marked output-only and cannot edit files, push commits, merge, or assign owners; approval/reviewer-request writes require explicit execution mode and policy gates.
- [ ] Dry-run is default and integration test asserts zero external mutations.
- [ ] Synthetic low-risk pass and uncertain/high-risk route are reproducible.

## Implementation evidence

See [final validation](../../../docs/evidence/validation.md). Checklist above is the original acceptance contract; production-dependent items remain subject to [production DoD](../../../docs/acceptance.md).
