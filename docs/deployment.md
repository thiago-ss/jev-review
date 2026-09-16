# Deployment runbook

Status: **not deployed**. No live GitHub approval, comment or reviewer request was made during development.

## Required configuration

Choose one target `OWNER/REPO`; configure the same exact identity in the allowlist. Supply trusted owner routes and fallback reviewers, required check names and GitHub App IDs, freshness limits, the bot login, and calibration artifacts. Do not treat PR labels, review text, supplied check names or suggested usernames as trusted policy.

Use `TYPESAFE_API_KEY` and a scoped `GITHUB_TOKEN` or GitHub App installation token. Keep both server-side, in repository/environment secrets. Reading requires access to contents, pull requests and checks; posting reviews/reviewer requests additionally requires pull-request write permission. Review exact permissions against the GitHub API and selected token type.

The included workflow uses a real GitHub App installation token. Follow the [App registration and setup guide](github-app.md). The controller's default `GITHUB_TOKEN` only checks out trusted bot code; a separately minted App token accesses the configured target. The workflow is disabled unless `JEV_ENABLED=true`; `JEV_EXECUTE=true` selects pull-request write permissions. Tokens are restricted to the configured installation owner/repository, which must match `JEV_REPOSITORY`.

App registration requests contents read, checks read and pull requests write. Each dry-run token is narrowed to reads. Store the App private key and Jev key as Actions secrets; store the App client ID and installation target as variables. Set `bot_login` from the actual App slug, not an invented bot username. GitHub App approvals do not automatically replace required human CODEOWNER reviews.

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

- Pilot target is `thiago-ss/jev-review`; fallback reviewer is repository owner `thiago-ss`. App registration and installation remain to be confirmed.
- GitHub deployment identity, permissions, required check App IDs and branch protection are unverified.
- Representative held-out labeled PR corpus is absent; production calibration and safe autonomous coverage remain unmeasured.

References: [GitHub reviews API](https://docs.github.com/en/rest/pulls/reviews), [review requests](https://docs.github.com/en/rest/pulls/review-requests), [secure Actions use](https://docs.github.com/en/actions/reference/security/secure-use).
