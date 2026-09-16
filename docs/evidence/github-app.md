# GitHub App implementation evidence

Date: 2026-09-16. Pilot selected by user: `thiago-ss/jev-review`; fallback reviewer: `thiago-ss`.

## Verified locally

- 65 tests passed on Python 3.12.13 and Python 3.9.6.
- `mypy jev_review scripts/register_github_app.py scripts/configure_github_app.py`: all 11 source files passed.
- Editable package installation and both workflow YAML parses passed; `git diff --check` passed.
- Official `actions/create-github-app-token` tag `v3.2.0` verified as `bcd2ba49218906704ab6c1aa796996da409d3eb1`.
- Registration tests exercise host/origin rejection, callback state/expiry/replay, Unicode rejection, credential preflight, bounded conversion, private storage, and secret-free public output.
- Setup tests exercise registration export parsing, disabled-first staging, stdin-only secret upload, conflicting config rejection, invalid input and sanitized failure behavior.
- Workflow tests verify explicit single-target token scope, dry-run read-only permissions, live pull-request-write permissions, and secret-free validation CI.
- Orchestrator independently exercised registration conversion → private export → setup config → Actions staging with injected HTTP/CLI responses. Correct app identity/variables reached staging; no real credentials or external mutations were used in this test.
- Browser rendering of the actual localhost registration form confirmed visible predefined permissions and its GitHub continuation button.

## Delegated implementation

Luna high agents implemented registration, setup and workflow independently. The workflow implementer also reviewed the registration/setup trust boundaries. Integration fixes included preserving the client ID, disabling scheduling before credential updates, matching variable names, rejecting callback replay/invalid Unicode, and avoiding Python 3.9 installation of a type checker requiring Python 3.10+.

## External state and remaining gate

The GitHub browser session was signed out. No App registration, repository installation, installation-token API request, or live bot review is claimed from local tests. The localhost registration helper is the owner handoff; credentials will exist only after GitHub returns a successful callback. Setup then stages secrets and disabled variables, the trusted config must be pushed, and a real dry-run workflow must be observed.

The existing authenticated Jev evaluation remains documented in [live observations](live-evaluation.md). This change does not alter the provider or approval policy and does not supply production calibration evidence. See the [App setup guide](../github-app.md).

## Observed GitHub CI

[Validation run 35116487259](https://github.com/thiago-ss/jev-review/actions/runs/35116487259) completed successfully for implementation commit `17960da55393cd27b542bcbf4380b36575897b5e`. Both `test (3.9)` and `test (3.12)` completed successfully; GitHub API reported App ID `15368` for both. The 3.12 job also passed mypy. GitHub emitted non-fatal Node 20 deprecation annotations for existing pinned checkout/setup-python actions, which ran under Node 24. This validates CI execution, not App installation authentication.

## Registration correction

GitHub rejected the initial manifest because its inactive webhook still used a loopback URL. Removed the optional webhook configuration entirely for this polling-only app; localhost remains only the browser callback. GitHub subsequently displayed the Create GitHub App form without validation errors. All 65 local tests and registration-helper mypy checks pass. Webhook secrets are optional in the conversion response because the runtime does not use webhooks.

## Installed pilot and real shadow run

App `jev-review-thiago-ss` (ID `4968910`) is registered. Its private key and the Jev key were staged as Actions secrets, with target scope `thiago-ss/jev-review`. `JEV_ENABLED=true`, `JEV_EXECUTE=false`: scheduled read-only operation is active. The registration listener was removed after successful credential receipt.

Created [documentation-only pilot PR #1](https://github.com/thiago-ss/jev-review/pull/1), then closed it after validation to avoid repeating paid inference against a test fixture. No merge occurred. Adding `config/` exposed setuptools auto-discovery failure in [initial CI](https://github.com/thiago-ss/jev-review/actions/runs/35133451071). Explicit runtime-package discovery fixed it; registration state tests were also isolated from real local credentials. All 65 local tests passed with real credentials present. [Updated pilot CI](https://github.com/thiago-ss/jev-review/actions/runs/35133604350) passed both Python versions.

[Final App workflow 35133673080](https://github.com/thiago-ss/jev-review/actions/runs/35133673080) succeeded: scoped read-only installation-token creation, PR snapshot, Jev inference and token cleanup all completed. The live write job was skipped. [Structured output](github-app-pilot.json) records exact head `c846b8bb8b34308d8277723b9d71bba9f15e4b53`, model `jev-1.13.0`, low risk and deterministic escalation because confidence/calibration gates failed. Both trusted CI checks passed; no CI-failure reason remained. GitHub review API confirmed zero reviews from the Jev App.

The only trusted reviewer is also this pilot PR's author, so the route is empty by design: GitHub cannot request author self-review. A second trusted human/team is needed to test reviewer requests on owner-authored PRs. This run proves App authentication and shadow review of a real PR, not production calibration, active review publication or useful autonomous approval coverage.
