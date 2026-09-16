# Standards/security review

Reviewed snapshot: `dd427bbdd71684b1c6acc338e5a80263d16cd3b0`, baseline `3b7ec1c3ae1e387076de8a397250406eef521688`, via `git diff 3b7ec1c...dd427bb`. Sources: `AGENTS.md`, `docs/evidence/validation-plan.md`, `docs/adr/0001-fail-closed-approval-boundary.md`.

Initial findings (resolved below):

1. **Hard, P1 — configured freshness can disable stale-check protection.** `jev_review/cli.py:198-200` passes `config_raw.get("check_freshness_seconds")` to `snapshot`; an omitted key becomes `None`, and `github._stale` treats `None` as “never stale” (`jev_review/github.py:355-360`). Thus a complete policy/calibration config with a 2000 check can still produce `passed_checks` and reach an approval. Reproduction: `GitHubClient(...).snapshot("o/r", 1, {"ci": [7]}, None)` returned `("ci",)` for `completed_at=2000-01-01`, while `86400` rejected it. Require a finite, positive freshness value (or fail closed) and preserve the snapshot default only when no override is explicitly requested.

2. **Hard, P1 — incomplete PR metadata is treated as safe.** `jev_review/github.py:140-141,165-168` rejects only `draft is True` and `merged_at is not None`; missing `draft`/`merged_at` fields are accepted as non-draft/unmerged. A fake open PR omitting both fields passed `snapshot()` and produced a reviewable `PullRequest`. The validation contract requires unknown/missing evidence to fail closed. Require `draft` to be a boolean and `merged_at` to be present (null allowed), with malformed state rejected.

3. **Hard, P1 — adapter write seam does not enforce policy/allowlist.** `jev_review/github.py:214-228,230-264` accepts `decision="auto_approve"` as sufficient to build an APPROVE plan; `execute()` checks SHA/checks but never checks policy action provenance, repository allowlist, calibration, or `--execute`. Direct use can POST an approval with only a snapshot and raw string: `build_plan(snapshot, "auto_approve"); execute(plan, dry_run=False)` did so in a local fake transport. Make write authorization a validated policy capability, or require and verify all deployment gates in the adapter.

Judgement calls: `_read_limited` is duplicated in provider/GitHub (possible Duplicated Code); `cli.py` owns JSON, calibration, GitHub, and polling flows (possible Divergent Change). These are maintainability smells, not hard violations.

Initial validation: GitHub/provider tests — 8 passed; diff check — clean.

## Resolution evidence

Owned fixes add typed `ApprovalContext`, require policy re-evaluation against the fresh snapshot before APPROVE, enforce an allowlisted repository before any POST, normalize omitted freshness to 86400 seconds while rejecting non-finite/non-positive overrides, and reject missing/non-boolean `draft` or missing `merged_at` on both reads. Re-evaluation binds fresh passed checks and trusted-check context; completed owner reviews satisfy prior requests. Regression coverage includes stale override, pending latest checks, forged/raw approval plans, ambiguous POST no-retry, and reviewer recovery. `.venv/bin/python -m unittest discover -s tests -v` — 39 passed; `.venv/bin/mypy jev_review/github.py` — clean; `git diff --check` — clean.

CLI passes `allowlisted_repositories` and `ApprovalContext` when constructing plans. Owned scope has no unresolved findings.
