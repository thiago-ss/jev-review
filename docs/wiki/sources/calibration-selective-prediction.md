---
title: Calibration and selective prediction
type: source
status: current
updated: 2026-09-16
sources: []
decisions: [../../../.scratch/jev-autonomous-review/map.md]
---

## Sources

- Guo, Pleiss, Sun, Weinberger, On Calibration of Modern Neural Networks (ICML 2017): https://proceedings.mlr.press/v70/guo17a.html
- Angelopoulos et al., Conformal Risk Control (arXiv 2208.02814): https://arxiv.org/abs/2208.02814
- El-Yaniv and Wiener, On the Foundations of Noise-Free Selective Classification (JMLR 2010): https://www.jmlr.org/papers/v11/el-yaniv10a.html
- Retrieved: 2026-09-16

## Documented facts

Calibration is an empirical relationship between predicted confidence and observed correctness; a confidence score alone does not establish it. Guo et al. study calibration of modern neural networks and temperature scaling as a post-hoc method. Selective classification explicitly allows a system to abstain on uncertain inputs, trading coverage for lower retained risk. Conformal risk control provides finite-sample risk-control results under its assumptions; the guarantee depends on the chosen loss, calibration data, and exchangeability-style conditions.

## Jev implication

Jev must separate `confidence` from `calibration evidence`, route when uncertainty or risk is outside policy, and report coverage plus false-approval risk on representative held-out labels. A deployment claim of one-sided 95% false-approval rate at or below 1% needs an explicit frozen policy/model/version, representative labels, and sufficient zero-error approvals; the baseline acceptance target is 299 safe approvals because `(1 - 0.95)^(1/299) ≈ 1%` for the simple zero-error upper-bound calculation. This is a proposed evidence bar, not observed data or a universal statistical guarantee.

## Caveats

Research results do not establish that an LLM's self-reported confidence is calibrated, that pull-request labels are exchangeable, or that 299 examples cover every repository/risk subgroup. Stratified monitoring and conservative abstention remain necessary. Exact confidence intervals and subgroup policy need implementation-time statistical review.
