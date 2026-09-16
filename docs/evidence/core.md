# Core implementation evidence

Date: 2026-09-16

The core seam is implemented in `jev_review/models.py`, `policy.py`, `calibration.py`, and `owners.py`. It validates structured pull request/review input, retains contradictory model judgments for deterministic escalation, routes only trusted owner entries, and computes empirical calibration metrics.

Validation run:

```text
$ PYTHONPATH=. python3 tests/test_core.py
.......
Ran 7 tests in 0.018s
OK

$ python3 -m compileall -q jev_review
```

Tests cover malformed/truncated/nonfinite input, contradiction escalation, all policy gates, exact false-approval bound/readiness provenance, and untrusted CODEOWNERS entries. No production calibration claim is made: readiness requires labeled held-out records with matching model/prompt/schema/repository identity and per-decision coverage.

Owner routing intentionally implements a small trusted CODEOWNERS subset (globs and directory-prefix patterns). An explicit empty final rule clears broader owners; unmatched paths use configured fallback owners. Unsupported GitHub-specific pattern semantics should remain human-routed.
