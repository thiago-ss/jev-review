"""Fail-closed GitHub REST adapter for review snapshots and gated writes."""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import json
import os
import threading
import time
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .models import ChangedFile, PullRequest

Transport = Callable[[Request, float], Tuple[int, Mapping[str, str], bytes]]
DEFAULT_API = "https://api.github.com"
MAX_RESPONSE_BYTES = 2_000_000


class GitHubError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> Optional[Request]:
        return None


@dataclass(frozen=True)
class GitHubSnapshot:
    pull_request: PullRequest
    state: str
    draft: bool
    merged: bool
    required_checks: Tuple[str, ...]
    trusted_check_app_ids: Mapping[str, Tuple[int, ...]]
    freshness_seconds: Optional[float] = None


@dataclass(frozen=True)
class ReviewPlan:
    repository: str
    number: int
    base_sha: str
    head_sha: str
    event: str
    body: str
    marker: str
    reviewers: Tuple[str, ...] = ()
    team_reviewers: Tuple[str, ...] = ()
    required_checks: Tuple[str, ...] = ()
    trusted_check_app_ids: Mapping[str, Tuple[int, ...]] = field(default_factory=dict)
    freshness_seconds: Optional[float] = None
    trusted_reviewers: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionResult:
    dry_run: bool
    skipped: bool
    operations: Tuple[str, ...]


class GitHubClient:
    """Read GitHub state, then write only after a fresh-head gate."""

    _write_lock = threading.Lock()

    def __init__(self, token: Optional[str] = None, api_url: str = DEFAULT_API, timeout: float = 10.0, retries: int = 2, transport: Optional[Transport] = None, bot_login: Optional[str] = None) -> None:
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self._transport = transport or self._urlopen
        self.bot_login = bot_login
        if not self.token.strip():
            raise GitHubError("GITHUB_TOKEN is required")
        if self.timeout <= 0 or self.retries < 0:
            raise GitHubError("invalid GitHub client configuration")
        if transport is None and self.api_url != DEFAULT_API:
            raise GitHubError("custom GitHub URL requires injected transport")

    @staticmethod
    def _urlopen(request: Request, timeout: float) -> Tuple[int, Mapping[str, str], bytes]:
        opener = build_opener(_NoRedirect())
        with opener.open(request, timeout=timeout) as response:  # nosec B310: fixed official API origin.
            return int(response.status), dict(response.headers.items()), _read_limited(response)

    def _request(self, method: str, path: str, payload: Optional[Mapping[str, Any]] = None, params: Optional[Mapping[str, Any]] = None) -> Tuple[Any, Mapping[str, str]]:
        url = self.api_url + path
        if params:
            url += "?" + urlencode(params)
        data = None if payload is None else json.dumps(payload, separators=(",", ":"), allow_nan=False).encode("utf-8")
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=data, method=method, headers=headers)
        for attempt in range(self.retries + 1):
            try:
                status, response_headers, raw = self._transport(request, self.timeout)
            except HTTPError as exc:
                status, response_headers, raw = exc.code, dict(exc.headers.items()), _read_limited(exc)
            except (OSError, URLError, TimeoutError) as exc:
                if method == "GET" and attempt < self.retries:
                    time.sleep(min(5.0, 0.5 * 2 ** attempt))
                    continue
                raise GitHubError("GitHub connection failed") from exc
            if method == "GET" and (status in (408, 429) or status >= 500):
                if attempt < self.retries:
                    time.sleep(_retry_delay(response_headers, attempt))
                    continue
            if status < 200 or status >= 300:
                raise GitHubError("GitHub HTTP error " + str(status), status=status)
            if not raw:
                return None, response_headers
            try:
                return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates), response_headers
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GitHubError("GitHub returned invalid JSON", status=status) from exc
        raise GitHubError("GitHub request failed")

    def get_pull_request(self, repository: str, number: int) -> Mapping[str, Any]:
        payload, _ = self._request("GET", "/repos/" + _repo(repository) + "/pulls/" + str(number))
        if not isinstance(payload, Mapping):
            raise GitHubError("pull request response malformed")
        return payload

    def list_open_pull_requests(self, repository: str, page: int = 1, per_page: int = 100) -> Tuple[Mapping[str, Any], ...]:
        payload, _ = self._request("GET", "/repos/" + _repo(repository) + "/pulls", params={"state": "open", "page": page, "per_page": min(per_page, 100)})
        if not isinstance(payload, list) or any(not isinstance(item, Mapping) for item in payload):
            raise GitHubError("open pull request response malformed")
        return tuple(payload)

    def snapshot(self, repository: str, number: int, required_checks: Optional[Mapping[str, Iterable[int]]] = None, freshness_seconds: Optional[float] = 86_400.0) -> GitHubSnapshot:
        pull = self.get_pull_request(repository, number)
        if pull.get("state") != "open" or pull.get("draft") is True or pull.get("merged_at") is not None:
            raise GitHubError("pull request is not reviewable")
        base = pull.get("base")
        head = pull.get("head")
        if not isinstance(base, Mapping) or not isinstance(head, Mapping) or not isinstance(base.get("sha"), str) or not isinstance(head.get("sha"), str):
            raise GitHubError("pull request SHA metadata missing")
        raw_files = self._all_files(repository, number)
        if isinstance(pull.get("changed_files"), int) and pull["changed_files"] != len(raw_files):
            raise GitHubError("changed files pagination incomplete")
        files = []
        for item in raw_files:
            path, patch = item.get("filename"), item.get("patch")
            if not isinstance(path, str) or not isinstance(patch, str) or not patch.strip():
                raise GitHubError("changed file patch missing or binary")
            if item.get("status") == "renamed" and not isinstance(item.get("previous_filename"), str):
                raise GitHubError("renamed file metadata missing")
            files.append(ChangedFile(path, patch, item.get("additions", 0), item.get("deletions", 0), False, item.get("previous_filename")))
        if isinstance(pull.get("additions"), int) and sum(item.additions for item in files) != pull["additions"]:
            raise GitHubError("addition count mismatch")
        if isinstance(pull.get("deletions"), int) and sum(item.deletions for item in files) != pull["deletions"]:
            raise GitHubError("deletion count mismatch")
        policy = {str(name): tuple(int(app) for app in apps) for name, apps in dict(required_checks or {}).items()}
        passed = self._passed_checks(repository, head["sha"], policy, freshness_seconds)
        latest = self.get_pull_request(repository, number)
        latest_base, latest_head = latest.get("base"), latest.get("head")
        if not isinstance(latest_base, Mapping) or not isinstance(latest_head, Mapping) or latest_base.get("sha") != base["sha"] or latest_head.get("sha") != head["sha"] or latest.get("state") != "open" or latest.get("draft") is True or latest.get("merged_at") is not None:
            raise GitHubError("pull request changed while reading files/checks")
        pr = PullRequest(repository, number, base["sha"], head["sha"], tuple(files), tuple(policy), passed, str(pull.get("title", "")), str(pull.get("body", "")))
        return GitHubSnapshot(pr, "open", bool(pull.get("draft", False)), False, tuple(policy), policy, freshness_seconds)

    def _all_files(self, repository: str, number: int) -> Tuple[Mapping[str, Any], ...]:
        result = []
        for page in range(1, 1001):
            payload, _ = self._request("GET", "/repos/" + _repo(repository) + "/pulls/" + str(number) + "/files", params={"page": page, "per_page": 100})
            if not isinstance(payload, list) or any(not isinstance(item, Mapping) for item in payload):
                raise GitHubError("changed files response malformed")
            result.extend(payload)
            if len(result) > 1000:
                raise GitHubError("pull request has too many changed files")
            if len(payload) < 100:
                return tuple(result)
        raise GitHubError("changed files pagination exceeded local limit")

    def _passed_checks(self, repository: str, head_sha: str, required: Mapping[str, Tuple[int, ...]], freshness_seconds: Optional[float]) -> Tuple[str, ...]:
        if not required:
            return ()
        runs = []
        for page in range(1, 101):
            payload, _ = self._request("GET", "/repos/" + _repo(repository) + "/commits/" + head_sha + "/check-runs", params={"page": page, "per_page": 100})
            page_runs = payload.get("check_runs") if isinstance(payload, Mapping) else None
            if not isinstance(page_runs, list):
                raise GitHubError("check-runs response malformed")
            runs.extend(page_runs)
            if len(page_runs) < 100:
                break
        else:
            raise GitHubError("check-runs pagination exceeded local limit")
        latest: Dict[str, Mapping[str, Any]] = {}
        for run in runs:
            if not isinstance(run, Mapping) or not isinstance(run.get("name"), str):
                continue
            old = latest.get(run["name"])
            if old is None or _run_key(run) > _run_key(old):
                latest[run["name"]] = run
        passed = []
        for name, app_ids in required.items():
            run = latest.get(name)
            app = run.get("app") if isinstance(run, Mapping) else None
            app_id = app.get("id") if isinstance(app, Mapping) else None
            if run is None or run.get("head_sha") != head_sha or run.get("status") != "completed" or run.get("conclusion") != "success" or isinstance(app_id, bool) or not isinstance(app_id, int) or app_id not in app_ids or _stale(run, freshness_seconds):
                continue
            passed.append(name)
        return tuple(passed)

    def build_plan(self, snapshot: GitHubSnapshot, decision: Any, reviewers: Sequence[str] = (), team_reviewers: Sequence[str] = (), trusted_reviewers: Iterable[str] = (), policy_version: str = "v1", summary: str = "") -> ReviewPlan:
        trusted = frozenset(trusted_reviewers)
        all_reviewers = tuple(reviewers) + tuple(team_reviewers)
        if any(not isinstance(value, str) or not value.strip() or any(ch.isspace() for ch in value) for value in all_reviewers):
            raise GitHubError("reviewer name malformed")
        if any(value not in trusted for value in all_reviewers):
            raise GitHubError("reviewer is not trusted")
        action = getattr(decision, "action", decision)
        action_value = getattr(action, "value", action)
        event = "APPROVE" if action_value == "auto_approve" else "COMMENT" if action_value == "escalate" else "NONE"
        if event == "APPROVE" and not snapshot.required_checks:
            raise GitHubError("approval requires trusted required checks")
        marker = "jev-review:" + policy_version + ":" + snapshot.pull_request.repository + ":" + str(snapshot.pull_request.number) + ":" + snapshot.pull_request.head_sha + ":" + event
        body = marker + "\n\n" + (summary.strip() or "Structured Jev review; see policy decision and trusted checks.")
        return ReviewPlan(snapshot.pull_request.repository, snapshot.pull_request.number, snapshot.pull_request.base_sha, snapshot.pull_request.head_sha, event, body, marker, tuple(reviewers), tuple(team_reviewers), snapshot.required_checks, snapshot.trusted_check_app_ids, snapshot.freshness_seconds, tuple(trusted))

    def execute(self, plan: ReviewPlan, dry_run: bool = True) -> ExecutionResult:
        if plan.event == "NONE":
            return ExecutionResult(dry_run, True, ())
        if plan.event not in ("APPROVE", "COMMENT") or plan.number < 1 or len(plan.base_sha) != 40 or len(plan.head_sha) != 40:
            raise GitHubError("review plan malformed")
        _repo(plan.repository)
        all_reviewers = plan.reviewers + plan.team_reviewers
        if any(not isinstance(value, str) or not value.strip() or any(ch.isspace() for ch in value) for value in all_reviewers):
            raise GitHubError("reviewer name malformed")
        if any(value not in plan.trusted_reviewers for value in all_reviewers):
            raise GitHubError("reviewer is not trusted")
        with self._write_lock:
            fresh = self.snapshot(plan.repository, plan.number, {key: value for key, value in plan.trusted_check_app_ids.items()}, plan.freshness_seconds)
            if fresh.pull_request.head_sha != plan.head_sha or fresh.pull_request.base_sha != plan.base_sha:
                raise GitHubError("base/head SHA changed before write")
            if plan.event == "APPROVE" and (not fresh.required_checks or tuple(fresh.pull_request.passed_checks) != tuple(fresh.required_checks)):
                raise GitHubError("required checks are not fresh/passing")
            bot = self.bot_login or self._current_user()
            reviews = self._reviews(plan.repository, plan.number)
            marker_present = any(isinstance(item, Mapping) and isinstance(item.get("body"), str) and plan.marker in item["body"] and isinstance(item.get("user"), Mapping) and item["user"].get("login") == bot for item in reviews)
            requested_users, requested_teams = self._requested_reviewers(plan.repository, plan.number) if plan.reviewers or plan.team_reviewers else (set(), set())
            missing_users = tuple(value for value in plan.reviewers if value not in requested_users)
            missing_teams = tuple(value for value in plan.team_reviewers if value not in requested_teams)
            if marker_present and not (missing_users or missing_teams):
                return ExecutionResult(dry_run, True, ("marker already present",))
            operations = ["marker already present" if marker_present else plan.event + " review at " + plan.head_sha]
            if missing_users or missing_teams:
                operations.append("request trusted reviewers")
            if dry_run:
                return ExecutionResult(True, False, tuple(operations))
            if not marker_present:
                self._request("POST", "/repos/" + _repo(plan.repository) + "/pulls/" + str(plan.number) + "/reviews", {"body": plan.body, "event": plan.event, "commit_id": plan.head_sha})
            if missing_users or missing_teams:
                self._request("POST", "/repos/" + _repo(plan.repository) + "/pulls/" + str(plan.number) + "/requested_reviewers", {"reviewers": list(missing_users), "team_reviewers": list(missing_teams)})
            return ExecutionResult(False, marker_present, tuple(operations))

    def _current_user(self) -> str:
        payload, _ = self._request("GET", "/user")
        login = payload.get("login") if isinstance(payload, Mapping) else None
        if not isinstance(login, str) or not login.strip():
            raise GitHubError("authenticated GitHub user unavailable")
        return login

    def _reviews(self, repository: str, number: int) -> Tuple[Mapping[str, Any], ...]:
        result = []
        for page in range(1, 101):
            payload, _ = self._request("GET", "/repos/" + _repo(repository) + "/pulls/" + str(number) + "/reviews", params={"page": page, "per_page": 100})
            if not isinstance(payload, list) or any(not isinstance(item, Mapping) for item in payload):
                raise GitHubError("reviews response malformed")
            result.extend(payload)
            if len(payload) < 100:
                return tuple(result)
        raise GitHubError("reviews pagination exceeded local limit")

    def _requested_reviewers(self, repository: str, number: int) -> Tuple[set, set]:
        payload, _ = self._request("GET", "/repos/" + _repo(repository) + "/pulls/" + str(number) + "/requested_reviewers")
        if not isinstance(payload, Mapping):
            raise GitHubError("requested reviewers response malformed")
        users, teams = payload.get("users"), payload.get("teams")
        if not isinstance(users, list) or not isinstance(teams, list):
            raise GitHubError("requested reviewers response malformed")
        user_logins = {item.get("login") for item in users if isinstance(item, Mapping) and isinstance(item.get("login"), str)}
        team_slugs = {item.get("slug") for item in teams if isinstance(item, Mapping) and isinstance(item.get("slug"), str)}
        return user_logins, team_slugs

    def reviewers_for_snapshot(self, snapshot: GitHubSnapshot, trusted_owners: Iterable[str], trusted_config: Optional[Mapping[str, Sequence[str]]] = None, fallback: Sequence[str] = ()) -> Tuple[str, ...]:
        """Resolve reviewers from CODEOWNERS at the trusted base SHA or config."""
        from .owners import parse_codeowners, route_files

        text = self._codeowners_at(snapshot.pull_request.repository, snapshot.pull_request.base_sha)
        rules = parse_codeowners(text, trusted_owners) if text is not None else ()
        return route_files(snapshot.pull_request.changed_paths, rules, trusted_config, fallback)

    def _codeowners_at(self, repository: str, base_sha: str) -> Optional[str]:
        for filename in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
            try:
                payload, _ = self._request("GET", "/repos/" + _repo(repository) + "/contents/" + filename, params={"ref": base_sha})
            except GitHubError as exc:
                if exc.status == 404:
                    continue
                raise
            content = payload.get("content") if isinstance(payload, Mapping) else None
            encoding = payload.get("encoding") if isinstance(payload, Mapping) else None
            if not isinstance(content, str) or encoding != "base64":
                raise GitHubError("CODEOWNERS response malformed")
            try:
                return base64.b64decode(content, validate=True).decode("utf-8")
            except (ValueError, UnicodeDecodeError) as exc:
                raise GitHubError("CODEOWNERS content malformed") from exc
        return None


def _repo(repository: str) -> str:
    if not isinstance(repository, str) or repository.count("/") != 1 or any(not part or part in (".", "..") for part in repository.split("/")):
        raise GitHubError("repository must be owner/name")
    return repository


def _read_limited(stream: Any) -> bytes:
    data = stream.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise GitHubError("GitHub response exceeds local byte limit")
    return data


def _reject_duplicates(pairs: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise GitHubError("duplicate JSON key")
        result[key] = value
    return result


def _retry_delay(headers: Mapping[str, str], attempt: int) -> float:
    for key, divisor in (("retry-after-ms", 1000.0), ("retry-after", 1.0)):
        value = next((str(v) for k, v in headers.items() if k.lower() == key), None)
        if value:
            try:
                return min(5.0, max(0.0, float(value) / divisor))
            except ValueError:
                pass
    return min(5.0, 0.5 * 2 ** attempt)


def _stale(run: Mapping[str, Any], freshness_seconds: Optional[float]) -> bool:
    if freshness_seconds is None:
        return False
    stamp = run.get("completed_at") or run.get("started_at")
    if not isinstance(stamp, str):
        return True
    try:
        from datetime import datetime, timezone
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - when).total_seconds() > freshness_seconds
    except ValueError:
        return True


def _run_key(run: Mapping[str, Any]) -> Tuple[int, str]:
    """GitHub run IDs are monotonic; timestamps are fallback for test doubles."""
    run_id = run.get("id")
    if isinstance(run_id, int) and not isinstance(run_id, bool):
        return run_id, ""
    stamp = run.get("completed_at") or run.get("started_at")
    return 0, stamp if isinstance(stamp, str) else ""
