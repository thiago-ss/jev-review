# Core interface contract

The core seam is pure Python and accepts mappings or typed dataclasses.

- `models.parse_pr(payload)` and `models.parse_review(payload)` validate all trust-boundary data and raise `ValidationError`; unknown enums, non-finite probabilities, omitted/truncated diffs, and contradictions fail closed.
- `models.Review` exposes `approve: bool`, `risk: RiskLevel`, `required_checklist_items: tuple[ChecklistItem, ...]`, `approve_confidence`, `risk_confidence`, `concerns`, and optional `suggestions`.
- `models.Review` retains provider-native distribution statistics in `native_confidences`; contradictory independent judgments remain representable and set `review.contradictory` for policy escalation.
- `policy.evaluate(pr, review, config, calibration=None)` returns `PolicyDecision(action, reasons)`; action is `AUTO_APPROVE`, `ESCALATE`, or `SHADOW`.
- Auto-approve requires exact SHA, allowlisted repo, trusted required CI all passing, limits, no sensitive files, no blockers, low risk, and high calibrated confidence for both approve/risk. Missing calibration defaults to escalation/shadow.
- `calibration.summarize(records)` computes empirical Brier/ECE/reliability, exact/binomial and Wilson false-approval upper bounds. `readiness(...)` rejects synthetic, insufficient, stale, mixed-identity, or non-held-out evidence.
- Calibration records can carry explicit `selected` and `sample_id`; selected approvals use the frozen selection threshold and duplicate IDs invalidate readiness.
- `owners.route_files(paths, codeowners, trusted_config)` uses only trusted CODEOWNERS/config mappings and conservative fallback; no model-generated usernames.
