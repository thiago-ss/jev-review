# Independent spec review

Baseline `3b7ec1c`; reviewed `3b7ec1c...dd427bb` plus current worktree delta. Local repros used no network.

Initial validation captured 22 tests with 1 policy happy-path failure after the gate changes. Findings below record the pre-fix state; integration remediations are now present in the worktree.

- **P1 — CLI cannot carry a valid policy identity.** The spec says, “Live approval is reachable only when repository is allowlisted … and no evidence is missing or stale” (line 17). `_policy_config` omits `policy_id` (and current CLI JSON config therefore always builds `PolicyConfig(policy_id="")`) at [`jev_review/cli.py:59-85`](/Users/thiago/dev/jev-review/jev_review/cli.py:59). Repro: supplying a computed fingerprint still prints `config policy_id=''`; `review --input examples/review.json` reports `policy identity is missing or does not match configuration`. This blocks every active approval through the CLI.

- **P1 — Decision/audit output is incomplete.** The contract says, “Required fields: policy action; evaluated change identity; gate results with pass/fail/unknown and reason … owner route when escalated; audit id; generated time; dry-run marker” (line 68). JSON review returns only action/approve/reasons/PR/review/dry-run/execution at [`jev_review/cli.py:147-163`](/Users/thiago/dev/jev-review/jev_review/cli.py:147); GitHub output is similarly partial at [`jev_review/cli.py:250-260`](/Users/thiago/dev/jev-review/jev_review/cli.py:250). It cannot reconstruct a decision or archive required provenance.

- **P1 — Autonomous scheduling is absent.** The spec says, “GitHub integration uses trusted-branch scheduled Actions polling/dispatch” (line 56). There is no `.github/workflows/` file; only manually invoked `github`/`poll` subcommands exist at [`jev_review/cli.py:298-314`](/Users/thiago/dev/jev-review/jev_review/cli.py:298). No autonomous workflow can run.

## Resolution

CLI now propagates and checks the frozen policy fingerprint, emits a structured audit envelope, and ships a disabled scheduled/dispatch workflow. Regression tests cover the policy identity, audit fields, active approval path and provider-failure routing. Final aggregate checks and remaining production gates are recorded in [validation.md](validation.md). Review fixes were implemented by the Luna high reviewer; no live GitHub writes were used as evidence.
