# Target-repository evaluation protocol

Status: required before production approval; no target repository or labeled corpus supplied.

## North star

Maximize **safe autonomous coverage**: PRs that the frozen policy would approve divided by all eligible open PRs observed in the evaluation window, subject to a one-sided 95% exact false-approval upper bound ≤1%. Report excluded PRs and exclusion reasons separately; do not improve coverage by silently removing difficult examples.

Calibration and routing are separate outcomes. Report approval/risk/checklist Brier scores, reliability bins and ECE; report owner-route agreement against trusted maintainer labels. A low aggregate ECE does not prove correctness in a rare security subgroup.

## Dataset and labels

1. Obtain permission and choose the single deployment repository. Record its identity and evaluation period.
2. Sample historical PRs across benign, defective, security-sensitive, dependency, test-only and documentation changes. Preserve complete diffs and context as observed before human review, with immutable base/head SHAs. Do not leak review outcomes into model input.
3. Have maintainers label whether approving each exact change would be acceptable, risk band, each checklist proposition, and responsible owners. Record labeler identity, timestamp and evidence; adjudicate disagreements. A merge is not by itself a correct label.
4. Split by PR (and related changes) into threshold-development and untouched evaluation sets. Keep duplicate commits, backports and correlated changes together. Freeze model version, question definitions, schema, policy, thresholds and ownership/check configuration before evaluating the held-out set.
5. Run the same production candidate-selection gates. Compute false approvals only among candidates selected by that frozen policy. Never select examples after seeing their labels. Preserve rejected and abstained cases to measure coverage and misses.
6. Require ≥299 independent selected approvals with zero false approvals for the stated ≤1% bound. Any observed error needs a larger sample or stricter policy; report the exact bound. This calculation assumes representative independent trials and is not a guarantee under distribution shift.
7. Validate risk and each named checklist separately, including support in deployed confidence bins. Do not pool all checklist items into one number and call every item calibrated.
8. Run shadow observation on fresh PRs, verify owner routes and CI identities, then review the deployment gate report. Re-evaluate after model, prompt, schema, policy or repository changes.

## Evidence integrity

Calibration rows use **selected-answer correctness**: `probability` is the probability assigned to the emitted Boolean/risk/checklist answer, and `label` is whether that answer agrees with the adjudicated label. For a rejected unsafe PR, approval `label` is `true` (the rejection was correct), even though its adjudicated safe-to-approve value is `false`. `selected` is a separate flag: whether the frozen complete approval policy would autonomously approve this PR. For selected approval rows, `label=false` is a false approval. Use one shared immutable PR identifier across its different decision fields; never duplicate the same identifier/field pair. Schema 2 maps checklist answers to binary pass/fail; low probability causes abstention in policy, not an invented probability for a derived warning category.

Synthetic examples test plumbing and adversarial behavior only. They must remain explicitly marked synthetic and cannot satisfy production readiness. Calibration artifacts are trusted deployment inputs: restrict write access to maintainers, review changes, preserve their source manifest and labels, and retain an audit trail. Software can reject missing or inconsistent provenance; it cannot certify that a supplied human label is honest.

## Current gate

Live API smoke exists in [live-wire-smoke.json](live-wire-smoke.json). It contains two synthetic cases and **zero production calibration samples**. Production autonomous coverage and owner-route accuracy are unmeasured.
