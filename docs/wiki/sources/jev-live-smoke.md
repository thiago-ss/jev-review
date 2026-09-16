---
title: Jev live-wire synthetic smoke evidence
type: source
status: current
updated: 2026-09-16
sources: []
decisions: [../../../.scratch/jev-autonomous-review/spec.md]
---

## Evidence

- Artifact: [`docs/evidence/live-wire-smoke.json`](../../evidence/live-wire-smoke.json)
- Observed: 2026-09-16
- Synthetic: yes
- Calibration evidence: no
- Endpoint: `https://api.typesafe.ai/v1/systemone`
- Observed provider model: `jev-1.13.0` (request alias was `latest`)

The authenticated smoke run returned HTTP 200 for two synthetic cases: a documentation typo classified low risk with a high safe-to-approve signal, and a SQL string-concatenation change classified critical risk with a low safe-to-approve signal. These observations demonstrate endpoint reachability and response-shape compatibility for those two inputs only.

## Caveats

Two synthetic examples do not establish calibration, general review quality, coverage, or a false-approval bound. Calibration identity must use the provider-returned model (`jev-1.13.0`) rather than the request alias. The full raw artifact is the evidence record; this page is a pointer and bounded summary.
