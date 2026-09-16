---
title: GitHub App registration and installation tokens
type: source
status: current
updated: 2026-09-16
sources: []
decisions: [../../../.scratch/jev-autonomous-review/issues/10-github-app-installation.md]
---

Primary sources checked 2026-09-16:

- [GitHub App manifest registration](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest)
- [Official installation-token Action](https://github.com/actions/create-github-app-token)

GitHub's manifest flow predefines permissions, sends the owner through registration, then returns a temporary code for server-side conversion into app credentials. Its state parameter protects the callback against cross-site request forgery. App registration and repository installation are separate steps.

The official Action mints an installation token for a chosen owner/repository and explicit permissions, then revokes it during cleanup by default. Tokens expire after one hour. The app's installation must already hold requested permissions.

## Jev decision

Use manifest registration plus the existing Actions scheduler. Disable webhooks for this polling deployment. Keep the private key in a trusted controller repository's secret store; scope each job token to the selected target repository. A dry run requests only reads even though the installation grants pull-request writes for later review publication. Preserve the existing calibration and approval gates.

## Limits

This is a privately operated app, not a hosted multi-tenant marketplace service. Each additional target needs explicit trusted configuration. Registration alone does not start reviews, and installation alone does not establish model safety.
