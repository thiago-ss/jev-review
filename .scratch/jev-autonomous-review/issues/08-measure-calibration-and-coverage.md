# 08: Measure calibration, coverage, and false approvals

**What to build:** An evaluation harness and artifact format that measures Jev's frozen policy/model/provider on representative held-out labels and reports safe coverage, abstention, false approvals, uncertainty bounds, routing quality, and subgroup/drift results.

**Blocked by:** 05, 06

**Status:** ready-for-agent

- [ ] Evaluation metadata freezes model/provider/prompt/config, policy version, repository/risk scope, label rubric, and dataset splits.
- [ ] Reports coverage, abstention, observed false approvals, routing quality, sample counts, and representative strata.
- [ ] Report can support the proposed 299 zero-error approvals evidence bar for a simple exact one-sided 95% ≤1% claim, while labeling it unmet until data exists.
- [ ] Calibration artifacts become invalid after model/provider/policy changes or detected drift.
- [ ] No benchmark or self-reported confidence is labeled calibration evidence.
