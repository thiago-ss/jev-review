# 04: Normalize review packet and provider adapter

**What to build:** A provider-independent seam that accepts structured pull-request metadata, diff evidence, model findings, checklist items, trusted checks, provenance, and configuration, validates required fields, and emits a normalized Review packet or an explicit missing-evidence result.

**Blocked by:** 01, 02, 03

**Status:** implemented locally; production activation gated

- [ ] Contract includes repository/PR/base/head/observed SHA identity and rejects ambiguity.
- [ ] Findings, risk bands, confidence, checklist, trusted checks, provenance, model/provider/policy versions, timestamps, and dry-run state normalize deterministically.
- [ ] Malformed, missing, unauthorized, or stale provider data becomes explicit missing evidence.
- [ ] Synthetic fixtures cover valid and invalid packets without requiring a target repository.
- [ ] Adapter contract leaves exact Jev API/provider choice configurable.

## Implementation evidence

See [final validation](../../../docs/evidence/validation.md). Checklist above is the original acceptance contract; production-dependent items remain subject to [production DoD](../../../docs/acceptance.md).
