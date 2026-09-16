# Jev research wiki

Persistent, source-linked knowledge for the Jev autonomous review workflow. Read this index first; follow page links before relying on a claim.

## Overview

- [Overview](./overview.md): north star, current scope, and evidence posture.
- [Schema and workflows](./schema.md): page fields, provenance, ingest/query/lint/update rules.
- [Conventions](./conventions.md): source and decision writing rules.
- [Synthesis: autonomous review](./synthesis/jev-autonomous-review.md): current design synthesis, decisions, and open caveats.

## Sources

- [Immutable source manifest](./raw/manifest.json): retrieved source snapshots and content hashes.
- [Jev API research](../research/jev-api.md): verified HTTP contract, probability semantics and live smoke observations.

- [Karpathy LLM Wiki pattern](./sources/karpathy-llm-wiki.md): durable source summaries, index/log, synthesis, and lint principles.
- [GitHub API and app security](./sources/github-api-security.md): primary GitHub documentation relevant to read-only review and approval boundaries.
- [Calibration and selective prediction](./sources/calibration-selective-prediction.md): primary research informing confidence, abstention, and risk claims.
- [Jev live-wire synthetic smoke](./sources/jev-live-smoke.md): two authenticated endpoint smoke cases; integration evidence only, not calibration evidence.

## Operations

- [Log](./log.md): append-only wiki operations and evidence updates.

## Status

Local implementation and synthetic experiments are complete; see [final validation](../evidence/validation.md). No GitHub installation or production calibration is claimed. Claims marked `Not verified` require deployment evidence.
