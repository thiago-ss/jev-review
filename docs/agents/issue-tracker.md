# Issue tracker: Local Markdown

This repository has no remote configured, so its issue tracker is local Markdown under `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`.
- Feature spec: `.scratch/<feature-slug>/spec.md`.
- One implementation ticket per file under `.scratch/<feature-slug>/issues/`, numbered from `01` in dependency order.
- `Status:` records `ready-for-agent`, `in-progress`, `blocked`, or `done`.
- `Blocked by:` lists ticket numbers and titles. A ticket is ready when all listed blockers are `done`.
- Comments append under `## Comments`.

## Wayfinding

- Map: `.scratch/<effort>/map.md`.
- Decision tickets use `Type: research|prototype|grilling|task`, `Status: claimed|resolved`, and an `## Answer` section.
- The map's `Decisions so far` links resolved decisions; open tickets remain in `issues/`.

## Scope note

The user authorized autonomous planning and documentation. This setup records assumptions without an interview. A future GitHub remote may replace this tracker through an explicit setup change.
