---
title: GitHub API and app security
type: source
status: current
updated: 2026-09-16
sources: []
decisions: [../../../.scratch/jev-autonomous-review/map.md, ../../adr/0001-fail-closed-approval-boundary.md]
---

## Sources

- GitHub Docs, Choosing permissions for a GitHub App: https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/choosing-permissions-for-a-github-app
- GitHub Docs, Authorizing GitHub Apps: https://docs.github.com/en/apps/using-github-apps/authorizing-github-apps
- GitHub Docs, Permissions required for GitHub Apps: https://docs.github.com/en/rest/authentication/permissions-required-for-github-apps
- GitHub Docs, Pull request reviews REST API: https://docs.github.com/en/rest/pulls/reviews
- GitHub Docs, Webhook events and payloads: https://docs.github.com/en/webhooks/webhook-events-and-payloads
- GitHub Docs, GitHub Actions workflow permissions: https://docs.github.com/en/rest/actions/permissions
- Retrieved: 2026-09-16

## Documented facts

GitHub Apps have no permissions by default; selected permissions determine API access and webhook subscriptions. GitHub recommends minimum permissions, and insufficient permissions can produce a 403 response. Pull request review reads require pull-request permission; review mutations are a separate capability and must not be assumed from read access. Webhook deliveries include a globally unique delivery identifier and an HMAC SHA-256 signature when a secret is configured; GitHub recommends validating the SHA-256 signature. Webhook payloads have a documented 25 MB cap.

GitHub documents that enabling Actions to approve pull-request reviews can be a security risk. GitHub Apps can be restricted to selected repositories, and the intersection of app and user permissions limits actions when acting on a user's behalf.

## Jev implication

Baseline integration should read only the metadata, diff, reviews, and checks required for a Review packet; request minimum permissions; bind evidence to the exact head SHA; and keep approval capability disabled until deployment gates are explicitly configured. Jev uses trusted-branch scheduled polling/dispatch, with idempotent decision keys and revalidation before any write. A provider adapter must expose permission and API failures as missing evidence, causing fail-closed routing.

## Caveats

These docs establish API/security behavior, not Jev's deployment configuration or permission grant. Exact endpoint support and required permission levels must be verified against the selected adapter and GitHub installation. No live installation exists in this repository.
