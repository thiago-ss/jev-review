# Default PR evidence comments — 2026-09-16

Comments are enabled for the installed pilot App. `JEV_COMMENTS=true`; `JEV_EXECUTE=false`. Scheduler defaults to comments if `JEV_COMMENTS` is absent. CLI remains dry-run by default.

## Observed external evidence

- [Real App review on PR #2](https://github.com/thiago-ss/jev-review/pull/2#pullrequestreview-5226786834): author `jev-review-thiago-ss[bot]`, state `COMMENTED`, exact head `d6bd047c89c07ca5b45ab5e0374eb40f90b0fdda`.
- [Successful publishing workflow](https://github.com/thiago-ss/jev-review/actions/runs/35135157991), implementation revision `8a8f196d686caa6844d3bc2c10147b42121abc16`.
- Jev returned model `jev-1.13.0`, request `req_01a0ab7f12c67860b972692e3d67b088`, 1129 input / 131 output tokens.
- Model approval probability 0.62, low-risk probability 0.96. Policy escalated: checklist/decision confidence below threshold and calibration absent. No approval or reviewer request issued.
- Browser inspection confirmed rendered risk/checklist/CI tables, confidence bars, exact commit and Actions links, and expandable structured evidence.

## Validation and correction

Luna implementer supplied renderer and presentation tests; orchestrator integrated comment-only execution and workflow defaults. Full suite: 76 tests pass on Python 3.9 and 3.12; mypy passes. Tests exercise real adapter transport to confirm comment-only mode never approves or requests reviewers, including provider failure and nonallowlisted repositories.

Live inspection caught JSON array delimiters being escaped inside the evidence block. Revision `624fd27` preserves array syntax and adds JSON round-trip coverage. The existing bot comment was updated using the same App identity; its raw evidence successfully parses as JSON. [Correction CI](https://github.com/thiago-ss/jev-review/actions/runs/35135255255) passed. No model response or decision was changed.

Calibration remains unverified. These results establish comment publication and presentation, not autonomous approval readiness.
