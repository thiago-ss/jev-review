# Jev Review
<!-- impeccable:product-schema: 1 -->

## Platform
web

## Purpose and users
Repository maintainers inspect typed Jev assessments and decide whether to trust or escalate a pull request. The pilot is thiago-ss/jev-review. The user requests both deeper review intelligence and bold visual reports, with no emojis.

## Mechanism
Jev produces typed decisions and probability distributions. Deterministic policy gates control writes. GitHub App comments expose evidence; execution results and model assessment must remain distinguishable. Multiple prompts to one model are correlated perspectives, not independent reviewers.

## Stack
Existing Python standard-library service and GitHub Actions. Implementation choices delegated by the user's original autonomous-build instruction. Generated HTML/SVG reports are artifacts, not a new hosted application.

## Constraints and commitments
No automatic approval without production calibration. No executing arbitrary PR code. No exposed credentials. Preserve exact SHAs, model/request identity and raw evidence. Synthetic experiments must remain labeled synthetic. Current App permissions and comment-only mode remain in force.

## Product principles
- Make uncertainty and missing evidence visible.
- Prefer reproducible observations over claims.
- Connect visual marks directly to underlying decisions and source evidence.
- Investigate disagreements; do not hide them in an average.
