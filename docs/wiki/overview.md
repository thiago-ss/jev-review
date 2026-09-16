# Overview

## North star

Safe autonomous review coverage: increase the fraction of low-risk, well-evidenced pull requests Jev can handle while bounding false approvals, preserving calibrated confidence, and routing uncertain or risky work to trusted owners.

## Current scope

Jev accepts structured pull-request metadata and diff evidence, asks finite independent review questions, produces a typed approve/risk/checklist review, and routes uncertain work with a structured breakdown. Approval is deterministic and fail closed. Dry-run is default. Suggestions are optional and output-only. Approval or reviewer-request mutations require explicit `--execute`, target configuration, and every policy/calibration gate; Jev never edits, pushes, or merges code.

## Success criteria

- Zero approval side effects in dry-run.
- Every Decision names the evaluated head SHA, repository allowlist result, risk result, trusted checks, confidence/calibration state, and policy outcome.
- Live approval is possible only for unchanged SHA, allowlisted repository, low-risk packet, passing trusted checks, and calibrated high-confidence policy evidence.
- A claimed one-sided 95% upper bound of false-approval rate at or below 1% requires representative held-out labels and at least 299 safe approvals with zero observed errors under the frozen policy/model/version. This is a future acceptance requirement, not current evidence.
- Human routes preserve findings, uncertainty, provenance, suggested owner, urgency, and a reproducible reason for abstention.

## Observed evidence

An authenticated smoke artifact records two synthetic Jev calls returning HTTP 200 from `systemone`; the provider reported model `jev-1.13.0`. One documentation typo was low risk/high safe signal; one SQL concatenation change was critical risk/low safe signal. This validates only those request/response paths. It is not calibration evidence.

## Non-goals

No target-repository onboarding is assumed. No generalized code modification agent, merge bot, issue tracker integration, autonomous ownership change, or provider-specific calibration claim is included in this baseline.
