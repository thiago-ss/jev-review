# 10: Register and run as an installable GitHub App

**Status:** App registered and installed; real shadow workflow verified; approval writes disabled
**Requested outcome:** Create a real GitHub App with predefined permissions; install it on selected repositories and run the existing reviewer under that identity.

## Contract

- Registration uses GitHub's manifest flow with repository contents read, checks read, and pull requests write; metadata read is implicit. No contents write, administration, organization membership, or user OAuth access.
- Webhooks remain disabled. The existing trusted-branch Actions scheduler supplies the runtime and mints short-lived installation tokens scoped to one configured target repository.
- Dry-run jobs explicitly request read-only installation permissions; live jobs request pull-request write. Neither token is used to checkout or execute PR code.
- Registration credentials stay in ignored owner-only local files and Actions secrets; no private key, temporary code or client secret appears in logs or version control.
- Setup prepares trusted configuration and disables execution and scheduling while secrets/configuration are staged. Missing calibration remains a normal abstention, not a missing-file failure.
- Repository selection and any GitHub authentication/installation authorization belong to the account owner. No registration or installation is claimed before GitHub confirms it.
- Existing approval policy is unchanged. Installation supplies identity, not statistical calibration evidence.

## Evidence

Tests and observed GitHub state will be recorded in `docs/evidence/github-app.md`. Rollout instructions live in `docs/github-app.md`.
