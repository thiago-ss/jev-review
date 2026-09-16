# 03: Choose fail-closed approval boundary

**Type:** grilling
**Status:** resolved
**Blocked by:** 01, 02

## Question

Which conditions must be deterministic prerequisites for Jev approval?

## Answer

Approval requires all of: allowlisted repository; exact unchanged head SHA; low risk; calibrated high-confidence evidence for the frozen model/provider/policy scope; complete, fresh, trusted checks passing on that SHA; complete configuration; and explicit live mode. Any unknown, stale, conflicting, or failed gate yields `request-human-review` or `abstain`. The boundary is recorded in [ADR-0001](../../../docs/adr/0001-fail-closed-approval-boundary.md).
