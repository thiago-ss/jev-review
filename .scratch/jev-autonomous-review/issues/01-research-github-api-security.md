# 01: Research GitHub API and app security

**Type:** research
**Status:** resolved
**Blocked by:** None (can start immediately)

## Question

Which GitHub API, app-permission, webhook, and check/review constraints must shape Jev's provider boundary and live approval gate?

## Answer

GitHub documents minimum app permissions, selected-repository restriction, signed webhook delivery validation, distinct read versus mutation capabilities, and a security risk in enabling Actions to approve reviews. Jev selects trusted-branch scheduled polling/dispatch for this implementation; it treats API/auth failures as missing evidence, binds all evidence to the observed head SHA, uses minimum read permissions, and keeps approval capability disabled until deployment configuration explicitly enables it. See [GitHub API and app security](../../../docs/wiki/sources/github-api-security.md).
