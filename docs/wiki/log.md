# Wiki log

## [2026-09-16] initialize | Jev autonomous review

- Created index, schema, conventions, overview, source pages, and synthesis.
- Recorded GitHub API/security and calibration research as documented inputs.
- Marked all empirical calibration and deployment observations `Not verified`.

## [2026-09-16] evidence | Jev live-wire synthetic smoke

- Linked authenticated two-case smoke artifact.
- Recorded provider-returned model `jev-1.13.0`; preserved distinction between request alias and calibration identity.
- Kept calibration status `Not verified`.

## [2026-09-16] integration | Build and evidence

- Implemented typed provider, fail-closed policy, calibration harness, trusted owner routing, GitHub adapter, CLI and disabled automation.
- Luna high implementers and independent Standards/Spec reviewers supplied fixes and evidence.
- Final real Jev run: ten synthetic cases, ten matching approval labels, zero unsafe model approvals; retained original failed request.
- Linked [acceptance](../acceptance.md), [validation](../evidence/validation.md) and [live observations](../evidence/live-evaluation.md).
- Production remains blocked on repository/owners/check identity and representative held-out human labels.

## [2026-09-16] implementation | Installable GitHub App

- User requested a real GitHub App with predefined installation permissions.
- Added [source research](sources/github-app-installation.md) and [implementation contract](../../.scratch/jev-autonomous-review/issues/10-github-app-installation.md).
- Registration, installation and workflow activation are separate observable states; no account authorization or completed live run is inferred from local tests.

- Local App implementation validation: 65 tests on Python 3.9/3.12, all 11 typed source files pass; [evidence](../evidence/github-app.md). Browser registration form rendered. GitHub sign-in/installation remain owner actions.

- Corrected App manifest after real GitHub validation rejected its inactive localhost webhook. Omitted webhook configuration; verified GitHub now renders the creation form. Local callback remains loopback-only.

- App installed and configured for `thiago-ss/jev-review`. Real scoped-token shadow review succeeded on pilot PR #1; exact structured output archived in [pilot evidence](../evidence/github-app-pilot.json). Trusted CI passed; confidence/calibration prevented approval. Pilot closed unmerged; hourly read-only polling remains enabled.

## Evidence comments by default

- User authorized default PR comments with visual review evidence and an Actions run link.
- Added a separate comment-only publication mode: model evaluation remains in shadow, while comments may be posted to allowlisted unchanged PRs. Approval and reviewer-request writes still require explicit full execution.
- Native GitHub Markdown presents risk, confidence and checklist/CI evidence; raw evidence stays collapsible. Scheduler comments default on after scheduling is enabled; `JEV_COMMENTS=false` opts out.
