# Jev autonomous review

Jev evaluates a pull-request change using structured evidence and a deterministic safety policy, then emits a review decision and owner route.

## Core language

**Change**:
A pull-request head commit plus its repository identity, base, metadata, diff, and check evidence.
_Avoid_: patch alone, request, submission

**Review packet**:
The normalized evidence Jev evaluates for one Change, including findings, confidence, risk, checks, and provenance.
_Avoid_: prompt, model response

**Finding**:
A specific possible defect or risk with location, rationale, severity, and supporting evidence.
_Avoid_: issue when referring to review output

**Decision**:
Jev's typed outcome for a Review packet: approve, request-human-review, or abstain, with reasons and policy gates.
_Avoid_: model answer, verdict

**Risk band**:
A bounded category describing consequence if a finding or approval is wrong: low, medium, high, or critical.
_Avoid_: severity when discussing consequence rather than defect priority

**Confidence**:
A model-reported belief attached to one finding or decision. It is an input to policy, not proof of calibration.
_Avoid_: probability unless empirically calibrated

**Calibration evidence**:
Held-out, representative labeled outcomes used to assess confidence reliability and false-approval risk for a frozen policy/model/version.
_Avoid_: intuition, benchmark score

**Trusted check**:
A configured check whose identity, conclusion, commit SHA, and freshness satisfy repository policy.
_Avoid_: green check

**Policy gate**:
A deterministic prerequisite that must pass before Jev may approve.
_Avoid_: guardrail when referring to an enforceable predicate

**Owner route**:
A structured recommendation of trusted human owners, rationale, urgency, and review packet for escalation.
_Avoid_: assignee when no external assignment occurs

**Dry run**:
Execution that computes and records a Decision while suppressing GitHub approval and merge side effects.
_Avoid_: simulation when evaluating a real Change
