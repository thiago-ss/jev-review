# Deployment runbook

Status: **not deployed**. No live GitHub approval, comment or reviewer request was made during development.

## Required configuration

Choose one target `OWNER/REPO`; configure the same exact identity in the allowlist. Supply trusted owner routes and fallback reviewers, required check names and GitHub App IDs, freshness limits, the bot login, and calibration artifacts. Do not treat PR labels, review text, supplied check names or suggested usernames as trusted policy.

Use `TYPESAFE_API_KEY` and a scoped `GITHUB_TOKEN` or GitHub App installation token. Keep both server-side, in repository/environment secrets. Reading requires access to contents, pull requests and checks; posting reviews/reviewer requests additionally requires pull-request write permission. Review exact permissions against the GitHub API and selected token type.

The included workflow is disabled unless `JEV_ENABLED=true`; `JEV_EXECUTE=true` selects its separate write-permission job. Set `JEV_REPOSITORY` and create trusted `config/production.json`. A workflow's default `GITHUB_TOKEN` is scoped to its repository: run the bot there, or provision a target-scoped GitHub App/token for cross-repository operation. Verify the repository/organization setting permitting Actions to approve PRs and whether the bot's approval satisfies the desired branch rules. Do not assume that an API approval replaces required human CODEOWNER review.

The bundled workflow runs in the configured target repository and passes its token to the adapter. For a separate target repository, supply an installation token through the deployment environment and keep the workflow checkout on this bot repository's default branch.

## Rollout

1. Run local tests and inspect the acceptance evidence.
2. Configure a protected bot default branch and trusted workflow. Never checkout or execute the PR head with bot credentials. Lock down changes to bot code, policy, calibration and ownership configuration. Restrict any deployment environment holding write secrets to that trusted branch; a branch checkout alone cannot protect a workflow definition that an authorized repository writer modifies.
3. Run `github` and `poll` in dry-run using read-only permissions. Inspect structured decisions, model versions, owner routes, missing patches, CI identity and freshness failures.
4. Collect and adjudicate representative labels using the [evaluation protocol](evidence/labeling-protocol.md). Freeze configuration before the held-out evaluation. Resolve every failed readiness gate.
5. Require branch protection to dismiss stale approvals after new commits and require current trusted checks. The adapter binds reviews to `commit_id` and rechecks state, but GitHub's review creation API is not a transaction spanning head/base/check reads and review publication.
6. Enable write permissions and explicit `--execute` only after deployment review. Start with one allowlisted repository and serialized polling. Monitor false approvals, abstentions, route failures and model drift.

## Operation and recovery

- Disable writes by removing `--execute` or revoking pull-request write permission. Stop scheduling to stop provider requests as well.
- GitHub request outcomes can be uncertain after a transport failure. Reconcile server-side review markers before retrying; do not blindly replay POSTs.
- Preserve JSON audit records with access controls appropriate for source code. Set retention according to the target repository's policy; public examples contain synthetic data only.
- A changed concrete Jev model, question set, schema, policy or repository invalidates prior evidence. Return to shadow operation until re-evaluated.
- Missing/binary/truncated diffs and unsupported ownership patterns must route or fail closed; they are not evidence of safety.

## Current blockers

- Target repository and trusted human owners are unspecified.
- GitHub deployment identity, permissions, required check App IDs and branch protection are unverified.
- Representative held-out labeled PR corpus is absent; production calibration and safe autonomous coverage remain unmeasured.

References: [GitHub reviews API](https://docs.github.com/en/rest/pulls/reviews), [review requests](https://docs.github.com/en/rest/pulls/review-requests), [secure Actions use](https://docs.github.com/en/actions/reference/security/secure-use).
