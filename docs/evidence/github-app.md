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
