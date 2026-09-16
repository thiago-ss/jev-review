---
title: Karpathy LLM Wiki pattern
type: source
status: current
updated: 2026-09-16
sources: []
decisions: [../../../.scratch/jev-autonomous-review/map.md]
---

## Source

- Publisher: Andrej Karpathy, GitHub Gist
- URL: https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f
- Retrieved: 2026-09-16
- Primary for the pattern: yes (idea file; implementation details remain agent-specific)

## Claims

The pattern treats an LLM-maintained Markdown wiki as a persistent, compounding artifact. A source is ingested once into a summary, related entity/concept pages, cross-references, and a chronological log; later queries read the compiled wiki rather than rediscovering every source. An index supports navigation at moderate scale, while lint checks stale claims, contradictions, orphan pages, missing cross-references, and research gaps.

The gist separates raw material, LLM-maintained wiki, and the schema/skill that governs workflows. It explicitly leaves implementation specifics to the adopting agent.

## Jev implication

Use `docs/wiki/index.md`, source summaries, synthesis pages, and append-only `log.md` to preserve research decisions and caveats. Keep source provenance explicit because a generated wiki can become internally consistent around an unverified claim.

## Caveats

The gist is a design pattern, not Jev evidence, a safety guarantee, or a GitHub API contract. No claim here demonstrates Jev accuracy or calibration.
