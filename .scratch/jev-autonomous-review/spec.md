# Jev autonomous review spec

## Problem Statement

Pull-request review work repeats across repositories, while model confidence and review quality are difficult to audit. Jev needs an autonomous research-to-review workflow that improves safe coverage without turning an uncalibrated model, stale check, mutable SHA, or missing repository configuration into an approval.

## Solution

Jev accepts structured pull-request metadata and diff evidence, asks finite independent Jev questions, produces a typed review packet, and evaluates it through a deterministic fail-closed policy. It emits `AUTO_APPROVE`, `ESCALATE`, or `SHADOW`, each with risk, checklist, confidence, evidence provenance, and policy gates. It routes non-approvals to trusted owners with a structured breakdown. Dry-run is default. Optional suggestions are output-only. Approval and reviewer-request mutations are available only behind explicit `--execute`, configured target/auth, and every policy/calibration gate; Jev never edits, pushes, merges, or assigns work.

## North star and success criteria

Safe autonomous coverage with a bounded false-approval rate, calibrated confidence, and high-quality owner routing.

- Dry-run produces reproducible decisions and zero external side effects.
- Every decision binds to repository, pull request, base SHA, head SHA, policy version, model/provider version, evidence timestamps, and trusted-check conclusions.
- Live approval is reachable only when repository is allowlisted, head SHA is unchanged, packet is low risk, confidence passes calibrated policy, all trusted checks pass for that exact SHA, and no evidence is missing or stale.
- Human route includes findings, locations, severity/risk, confidence, rationale, provenance, checklist, urgency, and suggested trusted owners.
- Proposed evidence gate: with representative held-out labels and zero observed false approvals, at least 299 safe approvals are needed for a simple exact one-sided 95% upper bound of ≤1%; report coverage, abstentions, errors, and strata. This evidence is not yet available.

## User Stories

1. As a repository owner, I want Jev to review a pull request from structured metadata and diff evidence, so that review work starts from a reproducible input.
2. As a repository owner, I want Jev to research relevant repository context, so that findings are grounded in local conventions.
3. As a repository owner, I want each finding to include location, rationale, severity, risk, confidence, and provenance, so that a human can audit it.
4. As a repository owner, I want a checklist of expected checks and review concerns, so that omissions are visible.
5. As a safety operator, I want model confidence separated from calibration evidence, so that self-reported certainty cannot unlock approval.
6. As a safety operator, I want deterministic gates to evaluate the packet, so that provider wording cannot bypass policy.
7. As a safety operator, I want missing, stale, conflicting, or untrusted evidence to fail closed, so that uncertainty becomes abstention or routing.
8. As a repository owner, I want approval bound to an unchanged head SHA, so that Jev cannot approve code it did not evaluate.
9. As a repository owner, I want approval restricted to an allowlisted repository, so that configuration mistakes cannot broaden authority.
10. As a repository owner, I want approval restricted to low-risk packets, so that high-consequence changes receive human review.
11. As a repository owner, I want only configured trusted checks to count, so that arbitrary green statuses cannot satisfy policy.
12. As a repository owner, I want trusted checks to match the evaluated SHA and freshness policy, so that stale evidence cannot unlock approval.
13. As a repository owner, I want dry-run as the default, so that deployment can observe behavior safely.
14. As a repository owner, I want structured output for approvals, abstentions, and routes, so that downstream systems can render or archive it.
15. As a trusted owner, I want uncertain work routed with a concise breakdown, so that I can act without reconstructing Jev's analysis.
16. As a trusted owner, I want routing to recommend owners without mutating assignments, so that external ownership remains deliberate.
17. As a safety operator, I want policy and model versions recorded, so that calibration evidence remains tied to the system evaluated.
18. As a safety operator, I want held-out representative labels, so that false-approval claims reflect deployment conditions.
19. As a safety operator, I want coverage, abstention, false-approval, and routing metrics, so that increased automation does not hide risk.
20. As a safety operator, I want calibration invalidated after model/provider/policy changes, so that old evidence cannot silently authorize new behavior.
21. As a repository owner, I want API and authentication failures represented as missing evidence, so that outages route safely.
22. As a repository owner, I want duplicate events to be idempotent, so that retries do not create conflicting decisions.
23. As a repository owner, I want read-only minimum permissions by default, so that credential compromise has a smaller blast radius.
24. As an operator, I want synthetic fixtures for missing deployment context, so that the full decision path is testable before onboarding a repository.
25. As an operator, I want a structured audit record, so that each decision can be reconstructed later.

## Implementation Decisions

- Use Python standard library for the initial small CLI/core; integrate Jev via its documented HTTP `systemone` contract.
- Use the shared normalized Review contract in `.scratch/core_contract.md`: parsed PR plus parsed Review (`approve`, risk, checklist, concerns, suggestions, confidence fields).
- Define typed policy actions `AUTO_APPROVE`, `ESCALATE`, and `SHADOW`; include dry-run, reasons, gate results, route, and audit identifiers.
- Define deterministic policy predicates for repository allowlist, unchanged SHA, low-risk classification, calibrated confidence, trusted-check identity/conclusion/SHA/freshness, configuration completeness, and dry-run side effects.
- Provider output is advisory and must be normalized/validated before policy evaluation. Unknown fields may be preserved in provenance but cannot satisfy a gate.
- GitHub integration uses trusted-branch scheduled Actions polling/dispatch through a provider adapter; exact endpoint details are recorded in `docs/research/jev-api.md`.
- Minimum GitHub permissions are required. Approval/reviewer-request capability stays disabled unless `--execute` and explicit deployment configuration are present.
- Store calibration artifacts with dataset/version scope, policy/model/provider versions, labels, thresholds, sample counts, error/coverage metrics, and invalidation conditions.
- Test external behavior at the policy-evaluator seam, then adapter contract and synthetic integration seam. Avoid tests coupled to model prompts or internal helper layout.
- No code edits, pushes, merges, or owner assignment side effects. Approval/reviewer-request API writes are allowed only in explicit execution mode after all gates pass.

### Review packet contract

Required fields: parsed PR identity (repository, number, base/head/observed SHA, author, base branch, changed files/diff); parsed Review (`approve`, risk, checklist, approve/risk confidence, concerns, optional suggestions); Jev/provider/model/policy metadata; trusted checks; calibration reference; configuration snapshot; and `dry_run`.

### Decision contract

Required fields: policy action; evaluated change identity; gate results with pass/fail/unknown and reason; risk/checklist/confidence summary plus calibration-evidence reference or `not-verified`; concerns/suggestions; owner route when escalated; audit id; generated time; dry-run marker. `AUTO_APPROVE` is invalid if any required gate is unknown or failed.

## Testing Decisions

- Unit-test pure policy behavior with adversarial packets: SHA changed, repository not allowlisted, high/critical risk, confidence high but calibration absent, stale/mismatched checks, duplicate event, missing metadata, and dry-run.
- Contract-test provider normalization with synthetic success, timeout, permission error, malformed payload, pagination, and retry cases.
- Integration-test one synthetic low-risk pass and one synthetic route/abstain path end to end, asserting no external mutation in dry-run.
- Calibration evaluation must use a held-out representative label set, frozen model/provider/policy metadata, and report coverage, abstention, false approvals, intervals, and strata. Do not call benchmarks calibration evidence.
- Test routing output for preservation of finding provenance, risk, confidence, checklist, urgency, and owner recommendation.

## Out of Scope

- Live target repository onboarding and production credentials in this documentation session.
- Autonomous source edits, code generation, commits, pushes, merges, labels, comments, or owner assignment. Approval/reviewer-request mutation remains execution-gated.
- Any claim that confidence is calibrated before held-out empirical evaluation.
- A universal statistical guarantee across repositories or risk strata.
- Full RAG/vector database infrastructure; the initial wiki is Markdown and index driven.

## Further Notes

Research decisions and caveats live in `docs/wiki/`. The local tracker map and tickets are the execution handoff. Deployment must supply repository identity, owner routes, trusted checks, auth, retention, calibration evidence, and explicit `--execute` before enabling live approval.
