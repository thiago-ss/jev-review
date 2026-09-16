"""Small JSON CLI for deterministic Jev review decisions.

The JSON review path is provider-free and is the highest seam for tests and
offline operation. GitHub integration is loaded lazily so this command still
works when no GitHub credentials or adapter are installed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass, replace
from datetime import datetime
from enum import Enum
import json
import os
import sys
from typing import Any, Mapping, Optional, Sequence

from .calibration import readiness, summarize
from .models import parse_pr, parse_review
from .owners import parse_and_route
from .policy import Action, PolicyConfig, PolicyDecision, evaluate


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}  # type: ignore[arg-type]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _read_json(path: str) -> Any:
    try:
        text = sys.stdin.read() if path == "-" else open(path, "r", encoding="utf-8").read()
        return json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("invalid JSON input: " + str(exc)) from exc


def _repo_map(value: Any, *, values: bool = False) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("repository config must be an object")
    result = {}
    for repo, checks in value.items():
        if not isinstance(repo, str) or not isinstance(checks, (list, tuple)):
            raise ValueError("repository checks config malformed")
        result[repo] = frozenset(checks) if values else tuple(checks)
    return result


def _policy_config(raw: Optional[Mapping[str, Any]], *, execute: bool) -> PolicyConfig:
    raw = raw or {}
    if not isinstance(raw, Mapping):
        raise ValueError("config must be an object")
    allowed = raw.get("allowlisted_repositories", raw.get("allowlist", ()))
    if not isinstance(allowed, (list, tuple, set, frozenset)):
        raise ValueError("allowlist must be an array")
    fields = {
        "allowlisted_repositories": frozenset(allowed),
        "required_checks_by_repo": _repo_map(raw.get("required_checks_by_repo")),
        "passed_checks_by_repo": _repo_map(raw.get("passed_checks_by_repo"), values=True),
        "expected_head_sha_by_repo": dict(raw.get("expected_head_sha_by_repo", {})),
        "sensitive_paths": tuple(raw.get("sensitive_paths", PolicyConfig.sensitive_paths)),
        "max_files": raw.get("max_files", PolicyConfig.max_files),
        "max_additions": raw.get("max_additions", PolicyConfig.max_additions),
        "max_deletions": raw.get("max_deletions", PolicyConfig.max_deletions),
        "max_patch_bytes": raw.get("max_patch_bytes", PolicyConfig.max_patch_bytes),
        "min_confidence": raw.get("min_confidence", PolicyConfig.min_confidence),
        "selection_threshold": raw.get("selection_threshold", PolicyConfig.selection_threshold),
        "calibration_min_samples": raw.get("calibration_min_samples", PolicyConfig.calibration_min_samples),
        "calibration_max_age_days": raw.get("calibration_max_age_days", PolicyConfig.calibration_max_age_days),
        "calibration_model_id": raw.get("calibration_model_id", ""),
        "calibration_prompt_version": raw.get("calibration_prompt_version", ""),
        "calibration_schema_version": raw.get("calibration_schema_version", ""),
        "mode": "active" if execute else "shadow",
    }
    return PolicyConfig(**fields)


def _calibration(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = _read_json(raw)
    if isinstance(raw, Mapping):
        raw = raw.get("records", raw.get("calibration", raw))
    if not isinstance(raw, list):
        raise ValueError("calibration must be an array or object with records")
    return summarize(raw)


def _calibrate_command(input_path: str, config_path: Optional[str]) -> Mapping[str, Any]:
    records = _read_json(input_path)
    if isinstance(records, Mapping):
        records = records.get("records", records.get("calibration"))
    if not isinstance(records, list):
        raise ValueError("calibration input must be an array or object with records")
    config = _github_config(config_path)
    report = summarize(records, bins=int(config.get("bins", 10)), selection_threshold=float(config.get("selection_threshold", .90)))
    model_id = str(config.get("calibration_model_id", config.get("model_id", "")))
    ready, reasons = readiness(
        report,
        min_samples=int(config.get("calibration_min_samples", config.get("min_samples", 299))),
        model_id=model_id,
        prompt_version=str(config.get("calibration_prompt_version", config.get("prompt_version", ""))),
        schema_version=str(config.get("calibration_schema_version", config.get("schema_version", ""))),
        repository=str(config.get("repository", "")),
        policy_id=str(config.get("calibration_policy_id", config.get("policy_id", ""))),
        max_age_days=config.get("calibration_max_age_days", config.get("max_age_days", 90)),
        false_approval_limit=float(config.get("false_approval_limit", .01)),
        selection_threshold=float(config.get("selection_threshold", .90)),
    )
    return {"ready": ready, "reasons": list(reasons), "report": _json_value(report), "input": input_path}


def review_payload(payload: Mapping[str, Any], *, execute: bool = False, input_path: str = "") -> Mapping[str, Any]:
    """Evaluate a JSON packet and return a JSON-serializable decision."""
    if not isinstance(payload, Mapping):
        raise ValueError("review input must be an object")
    pr_payload = payload.get("pr", payload.get("pull_request", payload))
    pr = parse_pr(pr_payload)
    review_data = payload.get("review")
    provider_model = None
    provider_request_id = None
    if review_data is None:
        from .provider import JevProvider

        provider = JevProvider(model=str(payload.get("model", os.environ.get("JEV_MODEL", "jev-latest"))))
        review, provider_result = provider.review_with_result(pr)
        provider_model, provider_request_id = provider_result.model, provider_result.request_id
    else:
        review = parse_review(review_data)
    config = _policy_config(payload.get("config"), execute=execute)
    calibration = _calibration(payload.get("calibration"))
    if provider_model:
        # Compare calibration identity to Jev's returned model, never a
        # request alias such as ``jev-latest``.
        config = replace(config, calibration_model_id=provider_model)
    decision = evaluate(pr, review, config, calibration)
    result = {
        "action": decision.action.value,
        "approve": decision.approve,
        "reasons": list(decision.reasons),
        "pr": _json_value(pr),
        "review": _json_value(review),
        "dry_run": not execute,
        "execution": {"performed": False, "simulated": True, "reason": "JSON review path has no external mutation"},
    }
    if provider_model:
        result["provider_model"] = provider_model
    if provider_request_id:
        result["provider_request_id"] = provider_request_id
    if input_path:
        result["input"] = input_path
    return result


def _github_config(path: Optional[str]) -> Mapping[str, Any]:
    path = path or os.environ.get("JEV_CONFIG", "")
    if not path:
        return {}
    value = _read_json(path)
    if not isinstance(value, Mapping):
        raise ValueError("GitHub config must be an object")
    return value


def _github_owner_name(owner: str) -> str:
    return owner[1:] if owner.startswith("@") else owner


def _split_github_routes(owners: Sequence[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    users: list[str] = []
    teams: list[str] = []
    for owner in owners:
        if not isinstance(owner, str) or not owner.strip():
            continue
        clean = _github_owner_name(owner.strip())
        (teams if "/" in clean else users).append(clean)
    return tuple(dict.fromkeys(users)), tuple(dict.fromkeys(teams))


def _github_one(repository: str, number: int, *, execute: bool, config_raw: Mapping[str, Any]) -> Mapping[str, Any]:
    from .github import ExecutionResult, GitHubClient
    from .provider import JevProvider, JevProviderError

    trusted = config_raw.get("trusted_checks", config_raw.get("required_checks", {}))
    if not isinstance(trusted, Mapping):
        raise ValueError("trusted_checks must map check names to app IDs")
    freshness = config_raw.get("check_freshness_seconds")
    client = GitHubClient(bot_login=config_raw.get("bot_login"))
    snapshot = client.snapshot(repository, number, trusted, freshness)
    configured_trusted = tuple(config_raw.get("trusted_reviewers", ()))
    route = parse_and_route(
        snapshot.pull_request.changed_paths,
        str(config_raw.get("codeowners", "")),
        configured_trusted,
        tuple(config_raw.get("fallback_reviewers", ())),
    )
    route_users, route_teams = _split_github_routes(route)
    trusted_for_github = tuple(dict.fromkeys(configured_trusted + tuple(_github_owner_name(v) for v in configured_trusted)))
    # Expected SHA and passed checks are captured from one snapshot and then
    # revalidated by GitHubClient.execute() immediately before a write.
    policy_raw = dict(config_raw.get("policy", {}))
    policy_raw.setdefault("allowlisted_repositories", config_raw.get("allowlisted_repositories", ()))
    policy_raw["required_checks_by_repo"] = {repository: list(snapshot.required_checks)}
    policy_raw["passed_checks_by_repo"] = {repository: list(snapshot.pull_request.passed_checks)}
    policy_raw["expected_head_sha_by_repo"] = {repository: snapshot.pull_request.head_sha}
    calibration = _calibration(config_raw.get("calibration"))
    provider_result = None
    try:
        provider = JevProvider(model=str(config_raw.get("model", os.environ.get("JEV_MODEL", "jev-latest"))))
        review, provider_result = provider.review_with_result(snapshot.pull_request)
    except JevProviderError as exc:
        decision = PolicyDecision(Action.ESCALATE, ("Jev provider unavailable: " + str(exc),))
        plan = client.build_plan(snapshot, decision, reviewers=route_users, team_reviewers=route_teams, trusted_reviewers=trusted_for_github, policy_version=str(config_raw.get("policy_version", "v1")), summary=json.dumps({"action": "escalate", "reasons": list(decision.reasons), "route": list(route)}, sort_keys=True))
        if repository not in frozenset(config_raw.get("allowlisted_repositories", ())):
            execution = ExecutionResult(not execute, True, ("repository is not allowlisted; no external write",))
        else:
            execution = client.execute(plan, dry_run=not execute)
        return {"repository": repository, "pull_request": number, "decision": _json_value(decision), "route": list(route), "plan": _json_value(plan), "execution": _json_value(execution), "provider_error": str(exc), "dry_run": not execute}
    if provider_result is None:
        raise RuntimeError("Jev provider returned no result")
    config = _policy_config(policy_raw, execute=execute)
    # Compare calibration identity to Jev's returned model, never a request
    # alias such as ``jev-latest``.
    config = replace(config, calibration_model_id=provider_result.model)
    decision = evaluate(snapshot.pull_request, review, config, calibration)
    configured_users, configured_teams = _split_github_routes(tuple(config_raw.get("reviewers", ()))), _split_github_routes(tuple(config_raw.get("team_reviewers", ())))
    reviewers = tuple(dict.fromkeys(configured_users[0] + route_users))
    team_reviewers = tuple(dict.fromkeys(configured_teams[1] + route_teams))
    trusted_reviewers = trusted_for_github
    summary = json.dumps({"action": decision.action.value, "reasons": list(decision.reasons), "risk": review.risk.value, "approve_confidence": review.approve_confidence, "risk_confidence": review.risk_confidence, "checklist": [_json_value(item) for item in review.required_checklist_items], "paths": list(snapshot.pull_request.changed_paths), "route": list(route)}, sort_keys=True)
    plan = client.build_plan(snapshot, decision, reviewers, team_reviewers, trusted_reviewers, str(config_raw.get("policy_version", "v1")), summary)
    if execute and repository not in config.allowlisted_repositories:
        execution = ExecutionResult(False, True, ("repository is not allowlisted; no external write",))
    else:
        execution = client.execute(plan, dry_run=not execute)
    return {
        "repository": repository,
        "pull_request": number,
        "decision": _json_value(decision),
        "review": _json_value(review),
        "provider_model": provider_result.model,
        "provider_request_id": provider_result.request_id,
        "route": list(route),
        "plan": _json_value(plan),
        "execution": _json_value(execution),
    }


def _github_command(args: argparse.Namespace) -> Mapping[str, Any]:
    """Run one or all open pull requests through the GitHub adapter."""
    config = _github_config(args.config)
    if getattr(args, "model", None) or getattr(args, "calibration", None):
        config = dict(config)
        if args.model:
            config["model"] = args.model
        if args.calibration:
            config["calibration"] = args.calibration
    if args.command == "github":
        return _github_one(args.repo, args.pr, execute=args.execute, config_raw=config)
    from .github import GitHubClient

    client = GitHubClient()
    pulls = client.list_open_pull_requests(args.repo)
    results = []
    for pull in pulls:
        number = pull.get("number") if isinstance(pull, Mapping) else None
        if isinstance(number, int):
            try:
                results.append(_github_one(args.repo, number, execute=args.execute, config_raw=config))
            except (RuntimeError, ValueError) as exc:
                results.append({"pull_request": number, "action": "escalate", "error": str(exc), "dry_run": not args.execute})
    return {"repository": args.repo, "count": len(results), "results": results, "dry_run": not args.execute}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jev-review", description="Fail-closed autonomous Jev review")
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review", help="review a JSON packet")
    review.add_argument("--input", required=True, help="JSON path, or - for stdin")
    review.add_argument("--calibration", help="calibration JSON path (overrides packet value)")
    review_mode = review.add_mutually_exclusive_group()
    review_mode.add_argument("--execute", action="store_true", help="enable policy active mode; JSON mode still performs no external write")
    review_mode.add_argument("--dry-run", action="store_true", help="explicitly select default dry-run mode")
    gh = sub.add_parser("github", help="review one GitHub pull request")
    gh.add_argument("--repo", required=True)
    gh.add_argument("--pr", type=int, required=True)
    gh.add_argument("--config", help="JSON deployment/policy config (or JEV_CONFIG)")
    gh.add_argument("--calibration", help="calibration JSON path (overrides config value)")
    gh.add_argument("--model", help="request model alias")
    gh_mode = gh.add_mutually_exclusive_group()
    gh_mode.add_argument("--execute", action="store_true", help="permit approval/reviewer-request writes after all gates")
    gh_mode.add_argument("--dry-run", action="store_true", help="explicitly select default dry-run mode")
    poll = sub.add_parser("poll", help="poll configured GitHub pull requests")
    poll.add_argument("--repo", required=True)
    poll.add_argument("--config", help="JSON deployment/policy config (or JEV_CONFIG)")
    poll.add_argument("--calibration", help="calibration JSON path (overrides config value)")
    poll.add_argument("--model", help="request model alias")
    poll_mode = poll.add_mutually_exclusive_group()
    poll_mode.add_argument("--execute", action="store_true", help="permit approval/reviewer-request writes after all gates")
    poll_mode.add_argument("--dry-run", action="store_true", help="explicitly select default dry-run mode")
    cal = sub.add_parser("calibrate", help="evaluate held-out calibration records")
    cal.add_argument("--input", required=True, help="JSON records path")
    cal.add_argument("--config", help="JSON calibration identity/config path")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "review":
            payload = _read_json(args.input)
            if args.calibration:
                payload = dict(payload)
                payload["calibration"] = args.calibration
            result = review_payload(payload, execute=args.execute, input_path=args.input)
        elif args.command in ("github", "poll"):
            result = _github_command(args)
        else:
            result = _calibrate_command(args.input, args.config)
        print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print("jev-review: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
