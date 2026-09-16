# Jev agent guidance

Jev is an autonomous pull-request review workflow. Work is planned in the local Markdown tracker, and durable research lives in `docs/wiki/`.

## Agent skills

### Issue tracker

Issues are local Markdown files under `.scratch/`; see `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository; see `docs/agents/domain.md` and `CONTEXT.md`.

## Operating constraints

- Default to dry-run. A live approval requires every policy gate to pass.
- Fail closed on missing, stale, ambiguous, untrusted, or unverifiable evidence.
- Accept only an unchanged head SHA with all configured trusted checks passing in an allowlisted repository.
- LLM outputs are advisory evidence. Confidence is not calibration evidence until evaluated on representative held-out labels.
- Suggestions may be emitted as structured output. Jev never edits files, pushes commits, or merges; approval/reviewer-request mutations exist only behind explicit `--execute`, target config, and every policy/calibration gate.
- The target repository and deployment identity are intentionally unset until deployment configuration is supplied. Synthetic fixtures are the current integration surface.
- Record assumptions and caveats in the wiki and decision log; do not invent completed experiments or API observations.
