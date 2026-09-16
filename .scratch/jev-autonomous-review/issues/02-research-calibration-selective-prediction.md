# 02: Research calibration and selective prediction

**Type:** research
**Status:** resolved
**Blocked by:** None (can start immediately)

## Question

What evidence can support confidence-based autonomous approvals, and when should Jev abstain or route to a human?

## Answer

Confidence is not calibration evidence. Selective prediction supports abstention to trade coverage for lower retained risk; calibration and conformal risk-control claims depend on held-out data and assumptions. Jev must freeze model/provider/policy/version scope, evaluate representative held-out labels, report coverage/abstention/errors/subgroups, and route whenever evidence is missing or outside policy. Proposed future evidence bar: at least 299 representative zero-error safe approvals for a simple exact one-sided 95% upper bound of ≤1% false-approval rate; this is not observed evidence. See [Calibration and selective prediction](../../../docs/wiki/sources/calibration-selective-prediction.md).
