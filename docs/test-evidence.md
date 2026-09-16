# What the tests establish

The Validate workflow installs the package and executes unittest discovery on Python 3.9 and 3.12. Python 3.12 also runs mypy over `jev_review`. Job logs list every test; the job summary records observed counts per module, failures, errors and skips.

| Area | Assertions exercised |
| --- | --- |
| Approval policy | Every approval gate blocks independently; synthetic calibration and model drift cannot authorize approval. |
| Calibration and parsing | Invalid/truncated input, duplicate samples, future timestamps, provenance and statistical readiness checks. |
| GitHub adapter | Exact SHA and App identity, stale/pending checks, draft rejection, write idempotency, trusted owners, uncertain POST outcomes. |
| Provider | Typed response mapping, probability validation, confidence preservation and error handling. |
| CLI and comment mode | Snapshot-to-policy wiring, dry-run isolation, comment-only writes, outages, repository allowlists. |
| Presentation | Evidence links, JSON round trips, Markdown escaping, absent evidence, output bounds and ASCII layout. |
| App setup and workflow | Scoped permissions, callback validation, private credential storage, secret handling and disabled setup defaults. |

These are deterministic tests, largely with fake HTTP transports. A passing suite does not prove Jev's real-world review accuracy, production calibration, coverage percentage or absence of vulnerabilities. Real provider/App observations are recorded separately under `docs/evidence/`.

The PR comment distinguishes GitHub check results from model assessments. Check status alone does not expose individual test counts; follow its job link for the execution report.
