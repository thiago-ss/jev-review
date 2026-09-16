---
title: Jev autonomous review synthesis
type: synthesis
status: current
updated: 2026-09-16
sources: [../sources/karpathy-llm-wiki.md, ../sources/github-api-security.md, ../sources/calibration-selective-prediction.md, ../sources/jev-live-smoke.md]
decisions: [../../../CONTEXT.md, ../../../docs/adr/0001-fail-closed-approval-boundary.md, ../../../.scratch/jev-autonomous-review/spec.md]
---

## Synthesis

Jev should be a small decision system around a structured Review packet. TypeSafe Jev answers finite independent questions about action, risk, and checklist evidence; deterministic code owns normalization, routing, and the approval boundary. An explicit execution mode may then call GitHub approval or reviewer-request APIs. This combines the LLM Wiki pattern's durable source-linked synthesis with GitHub's least-privilege guidance and selective prediction's abstention posture.

## Decisions

- Local Markdown remains the tracker. Source code is now hosted at `thiago-ss/jev-review`; the review target is a separate deployment choice.
- Dry-run is default; no code edits, pushes, or merges are permitted. Approval/reviewer-request writes require explicit `--execute` plus gates.
- Approval requires unchanged head SHA, allowlisted repository, low risk, calibrated high confidence, and all trusted checks passing.
- Unknown, stale, conflicting, or missing evidence routes to human review.
- Provider is Jev at TypeSafe's documented `systemone` endpoint. A two-case authenticated synthetic smoke exists; provider returned model `jev-1.13.0`; no local calibration evidence exists yet.
- Research is persisted in this wiki with direct sources, linked decisions, and explicit caveats.

## Proposed evidence bar

Before live approval, freeze model/provider, prompt/config, policy version, repository/risk scope, and labels. Evaluate on representative held-out data. To claim a simple exact one-sided 95% upper bound of ≤1% false-approval rate after zero observed errors, collect at least 299 safe approvals; report coverage, errors, abstentions, subgroup results, and drift. If any assumption is not met, keep approval disabled and route.

## Open questions

- GitHub App installation tokens now provide the planned deployment identity; see [App research](../sources/github-app-installation.md). Registration and installation still require observed GitHub confirmation.
- Which repository owner and trusted-check allowlist will deployment configure?
- What labeling protocol defines a false approval and representative risk strata?
- How are model/provider versions and policy changes invalidating calibration handled?

## Caveats

No live GitHub data or calibration sample exists in this repository. The smoke artifact is synthetic endpoint evidence only; do not generalize it to model quality. Implementation evidence may grow as tickets land.
