# Wayfinder map: Jev autonomous review

## Destination

A concise, implementable spec and dependency-ordered tickets for a dry-run-first autonomous Jev review bot, with a deterministic fail-closed approval boundary, structured human routing, and a calibration evidence plan. The path is clear enough for implementers while deployment-specific identity and provider choices remain explicit gates.

## Notes

Domain: pull-request review safety and routing. Consult `CONTEXT.md`, relevant ADRs, `docs/wiki/`, `to-spec`, `to-tickets`, and `domain-modeling`. User authorized autonomous synthesis; do not pause for interviews or approvals. No remote or target repository is configured. All implementation tickets target Luna at high reasoning effort.

## Decisions so far

- [Research GitHub API and app security](./issues/01-research-github-api-security.md): minimum permissions, SHA binding, and disabled approval capability are deployment constraints; see [source synthesis](../../docs/wiki/sources/github-api-security.md).
- [Research calibration and selective prediction](./issues/02-research-calibration-selective-prediction.md): confidence is not calibration; abstention and held-out evidence are required; proposed zero-error 95% ≤1% bar is 299 approvals; see [source synthesis](../../docs/wiki/sources/calibration-selective-prediction.md).
- [Choose fail-closed approval boundary](./issues/03-choose-fail-closed-approval-boundary.md): deterministic gates own approval; see [ADR-0001](../../docs/adr/0001-fail-closed-approval-boundary.md).

## Not yet specified

- Exact deployment authentication, rate limits, and polling schedule.
- Target repository/owner, trusted-check names, risk taxonomy details, and deployment secret/configuration process.
- Labeling rubric, representative sampling frame, drift window, and recalibration cadence.

## Out of scope

- Autonomous code edits, commits, pushes, merges, or owner assignment side effects.
- Any live GitHub deployment until target identity, least-privilege installation, and calibration evidence gates are configured.
- Claiming production accuracy, calibration, or a completed false-approval bound from design documents.
