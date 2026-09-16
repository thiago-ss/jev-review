# GitHub adapter evidence

Implementation: [jev_review/github.py](/Users/thiago/dev/jev-review/jev_review/github.py).

The adapter uses GitHub REST endpoints documented by GitHub:

- `GET /repos/{owner}/{repo}/pulls/{pull_number}` for PR metadata and base/head SHAs.
- `GET /repos/{owner}/{repo}/pulls/{pull_number}/files` paginated at 100 per page for complete patches.
- `GET /repos/{owner}/{repo}/commits/{ref}/check-runs` paginated at 100 per page for exact-head, latest-per-name, trusted-app checks.
- `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` paginated for authenticated bot marker checks.
- `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` with explicit `event` and `commit_id`.
- `POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers` for trusted users/team slugs.
- `GET /repos/{owner}/{repo}/contents/{path}?ref={base_sha}` for CODEOWNERS at the trusted base.
- `GET /repos/{owner}/{repo}/pulls?state=open` for polling.

Primary sources: [pull request REST endpoints](https://docs.github.com/en/rest/pulls/pulls), [pull request files](https://docs.github.com/en/rest/pulls/files), [check runs](https://docs.github.com/en/rest/checks/runs), [pull request reviews](https://docs.github.com/en/rest/pulls/reviews), [repository contents](https://docs.github.com/en/rest/repos/contents), and [REST pagination](https://docs.github.com/en/rest/using-the-rest-api/using-the-rest-api#using-pagination-in-the-rest-api).

Safety behavior:

- Snapshot rejects closed, merged, draft, missing/binary/truncated patches, pagination overflow, changed-file count mismatches, and base/head changes observed during the read.
- Check runs must be completed/successful, match the exact head SHA, use an allowlisted app ID, be latest by name, and be fresh (24-hour default; caller may override). Failed checks remain available for escalation/comment plans; approval plans require configured required checks.
- HTTP retries apply to GET only. POST failures are not blindly retried because a response may have committed an ambiguous write.
- Before any write, the adapter re-fetches PR/files/checks and compares exact base/head SHAs. It serializes writes process-locally, supports dry-run with no POST, validates trusted reviewers again, and uses an event-specific marker.
- Existing markers are trusted only when authored by the configured/authenticated bot. Existing comments can resume missing reviewer requests.
- The adapter never checks out or executes pull request code.

Local validation:

```text
.venv/bin/python -m unittest tests.test_github tests.test_provider -v
Ran 8 tests ... OK
.venv/bin/mypy jev_review/github.py jev_review/provider.py
Success: no issues found
```

Tests cover exact app/SHA filtering, draft rejection, dry-run zero POSTs, marker idempotency, reviewer trust, provider contract, and non-retryable failures. Live GitHub writes were not performed.
