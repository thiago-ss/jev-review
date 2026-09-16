# Jev Review

A small autonomous PR review bot built around TypeSafe's Jev. It consumes structured PR metadata and patches, asks finite typed questions, then applies deterministic approval gates. Uncertain or risky reviews route to trusted owners with a structured explanation. Suggestions are advisory; the bot never edits or merges code.

**Status:** GitHub App installed on `thiago-ss/jev-review`; scheduled shadow reviews enabled; approval writes disabled. Production approval is gated on a named repository, trusted deployment configuration and representative held-out calibration evidence. The included synthetic examples do not satisfy that gate.

## Run locally

Python 3.9+; runtime uses the standard library.

```sh
python3 -m venv .venv
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m jev_review --help
```

`review --input FILE` accepts a JSON packet containing `pr`, optional `review`, `config` and `calibration`. Supplying a review exercises the pipeline offline; omitting it calls Jev using `TYPESAFE_API_KEY`. The CLI reads environment variables and does not automatically load `.env`.

```sh
.venv/bin/python -m jev_review review --input examples/review.json
.venv/bin/python -m jev_review calibrate --input examples/calibration.json --config examples/calibration-config.json
```

The calibration example is intentionally synthetic and reports `ready: false`; production readiness requires the held-out evidence described below.

Dry-run is the default. `review --execute` only simulates active policy evaluation locally; it never calls GitHub. Only the `github` and `poll` commands can write externally, and only with explicit `--execute`.

## Installable GitHub App

Use the [GitHub App setup guide](docs/github-app.md) to register predefined permissions, install on selected repositories and run with short-lived scoped tokens. The trusted controller workflow defaults to disabled/read-only operation.

## GitHub integration

```sh
export TYPESAFE_API_KEY='...'
export GITHUB_TOKEN='...'
.venv/bin/python -m jev_review github --repo OWNER/REPO --pr 123 --config examples/github-config.json --dry-run
.venv/bin/python -m jev_review poll --repo OWNER/REPO --config examples/github-config.json --dry-run
```

Use trusted configuration from the bot's default branch. Do not load credentials, policy or calibration from a PR branch. Review the [deployment runbook](docs/deployment.md) before enabling writes.

## Confidence and calibration

Jev returns probability distributions and a vendor confidence statistic. These are preserved separately. Model certainty alone never authorizes approval. Production evidence must match the concrete response model, prompt/schema and frozen policy; synthetic, stale, duplicated or mismatched evidence fails closed.

The [evaluation protocol](docs/evidence/labeling-protocol.md) defines safe autonomous coverage and the false-approval bound. The final [ten-case real API run](docs/evidence/live-final-integration-evaluation.json) matched all synthetic approval labels; it does not establish production accuracy or calibration.

## Project map

- [Product spec and acceptance criteria](.scratch/jev-autonomous-review/spec.md)
- [Success criteria and definition of done](docs/acceptance.md)
- [Wayfinder decision map](.scratch/jev-autonomous-review/map.md)
- [LLM wiki](docs/wiki/index.md), including immutable source snapshots and linked decisions
- [Jev API research](docs/research/jev-api.md)
- [Final validation evidence](docs/evidence/validation.md)
- [Validation contract](docs/evidence/validation-plan.md)
- [Live synthetic evaluation](docs/evidence/live-evaluation.md), including original failure and final ten-case run

Matt Pocock's selected engineering skills are installed under `.agents/skills/`, with upstream provenance and license. Implementers use Luna high; recorded evidence distinguishes local tests, real API observations and missing production evidence.
