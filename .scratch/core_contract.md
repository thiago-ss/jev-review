# Core interface contract

The core seam is pure Python and accepts mappings or typed dataclasses.

- `models.parse_pr(payload)` and `models.parse_review(payload)` validate all trust-boundary data and raise `ValidationError`; unknown enums, non-finite probabilities, omitted/truncated diffs, and contradictions fail closed.
- `models.Review` exposes `approve: bool`, `risk: RiskLevel`, `required_checklist_items: tuple[ChecklistItem, ...]`, `approve_confidence`, `risk_confidence`, `concerns`, and optional `suggestions`.
- `models.Review` retains provider-native distribution statistics in `native_confidences`; contradictory independent judgments remain representable and set `review.contradictory` for policy escalation.
- `policy.evaluate(pr, review, config, calibration=None)` returns `PolicyDecision(action, reasons)`; action is `AUTO_APPROVE`, `ESCALATE`, or `SHADOW`.
- Auto-approve requires exact SHA, allowlisted repo, trusted required CI all passing, limits, no sensitive files, no blockers, low risk, and high calibrated confidence for both approve/risk. Missing calibration defaults to escalation/shadow.
- `calibration.summarize(records)` computes empirical per-decision Brier/ECE/reliability and an exact binomial false-approval upper bound. `readiness(...)` requires explicit heldout/synthetic/selected/sample_id/timestamp/policy_id provenance, frozen model/prompt/schema/repository/policy identity, named checklist coverage, sample floors, quality bars, and freshness.
- Calibration records use explicit `selected` (no probability fallback); selected approvals are unique by sample id. Same sample id across fields is valid; duplicate `(sample_id, decision)` invalidates readiness.
- `policy.policy_fingerprint(config)` hashes static approval-affecting gates. Policy id must equal this fingerprint; live head SHA/check conclusions/model identity are excluded.
- `PolicyConfig.selection_threshold` equals `min_confidence`; selected calibration trials therefore use same confidence gate as evaluation.
- `owners.route_files(paths, codeowners, trusted_config)` uses only trusted CODEOWNERS/config mappings and conservative fallback; no model-generated usernames.
