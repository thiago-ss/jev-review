"""Small JSON CLI for deterministic Jev review decisions.

The JSON review path is provider-free and is the highest seam for tests and
offline operation. GitHub integration is loaded lazily so this command still
works when no GitHub credentials or adapter are installed.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
import hashlib
import json
import os
import sys
from typing import Any, Mapping, Optional, Sequence

from .calibration import readiness, summarize
from .models import parse_pr, parse_review
from .owners import parse_and_route
from .policy import Action, PolicyConfig, PolicyDecision, evaluate, policy_fingerprint


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


def _trusted_context_id(checks: Mapping[str, Any], freshness: Any) -> str:
    """Stable identity for trusted check names, app IDs, and freshness policy."""
    normalized = {}
    for name, app_ids in checks.items():
        if not isinstance(name, str) or not isinstance(app_ids, (list, tuple, set, frozenset)):
            raise ValueError("trusted check config malformed")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in app_ids):
            raise ValueError("trusted check app IDs malformed")
        normalized[name] = sorted(app_ids)
    payload = {"checks": normalized, "freshness_seconds": 86_400.0 if freshness is None else freshness}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ValueError("config must be an object")
    allowed = raw.get("allowlisted_repositories", raw.get("allowlist", ()))
    if not isinstance(allowed, (list, tuple, set, frozenset)):
        raise ValueError("allowlist must be an array")
    config_fields = {
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
        "calibration_min_samples_per_decision": raw.get("calibration_min_samples_per_decision", PolicyConfig.calibration_min_samples_per_decision),
        "calibration_max_ece": raw.get("calibration_max_ece", PolicyConfig.calibration_max_ece),
        "calibration_max_brier": raw.get("calibration_max_brier", PolicyConfig.calibration_max_brier),
        "required_checklist_decisions": tuple(raw.get("required_checklist_decisions", PolicyConfig.required_checklist_decisions)),
        "trusted_required_checks": _repo_map(raw.get("trusted_required_checks")),
        "trusted_passed_checks": _repo_map(raw.get("trusted_passed_checks"), values=True),
        "exact_head_sha_by_repo": dict(raw.get("exact_head_sha_by_repo", {})),
        "policy_id": raw.get("policy_id", ""),
        "mode": "active" if execute else "shadow",
    }
    config_fields["trusted_context_id"] = raw.get("trusted_context_id", "")
    config = PolicyConfig(**config_fields)
    if not config.policy_id:
        config = replace(config, policy_id=policy_fingerprint(config))
    return config


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


def _calibration_reference(raw: Any) -> str:
    if raw is None:
        return "not-verified"
    return raw if isinstance(raw, str) else "embedded"


def _gate_results(decision: PolicyDecision) -> list[Mapping[str, str]]:
    if not decision.reasons:
        return [{"status": "pass", "reason": "all policy gates passed"}]
    unknown_terms = ("missing", "stale", "unavailable", "not passing", "not exact", "mismatch", "unknown")
    return [{"status": "unknown" if any(term in reason.lower() for term in unknown_terms) else "fail", "reason": reason} for reason in decision.reasons]


def _route_breakdown(review: Any, owners: Sequence[str]) -> Mapping[str, Any]:
    findings = []
    for concern in getattr(review, "concerns", ()):
        findings.append({"message": concern.message, "path": concern.path, "line": concern.line, "severity": concern.severity.value})
    risk = getattr(getattr(review, "risk", None), "value", None)
    return {"owners": list(owners), "urgency": "high" if risk in ("high", "critical") else "normal", "risk": risk, "findings": findings}


def _audit_envelope(pr: Any, review: Any, decision: PolicyDecision, config: PolicyConfig, *, execute: bool, policy_version: str = "v1", calibration_ref: str = "not-verified", provider_result: Any = None, route: Sequence[str] = ()) -> Mapping[str, Any]:
    model_id = getattr(provider_result, "model", "") or getattr(config, "calibration_model_id", "") or "not-verified"
    prompt_version = getattr(config, "calibration_prompt_version", "") or "not-verified"
    schema_version = getattr(config, "calibration_schema_version", "") or "not-verified"
    identity = {"repository": pr.repository, "pull_request": pr.number, "base_sha": pr.base_sha, "head_sha": pr.head_sha, "policy_id": config.policy_id, "model_id": model_id, "prompt_version": prompt_version, "schema_version": schema_version}
    audit_id = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    provider = {}
    if provider_result is not None:
        provider = {"request_id": getattr(provider_result, "request_id", None), "answers": _json_value(getattr(provider_result, "answers", {})), "usage": _json_value(getattr(provider_result, "usage", {}))}
    return {
        "audit_id": audit_id,
        "generated_at": datetime.now().astimezone().isoformat(),
        "change": {"repository": pr.repository, "pull_request": pr.number, "base_sha": pr.base_sha, "head_sha": pr.head_sha, "observed_head_sha": pr.head_sha, "author": getattr(pr, "author", None), "base_branch": getattr(pr, "base_branch", None)},
        "policy": {"version": policy_version, "policy_id": config.policy_id, "action": decision.action.value, "reasons": list(decision.reasons), "gates": _gate_results(decision)},
        "model": {"provider": "typesafe-jev" if provider_result is not None else "supplied-review", "model_id": model_id, "prompt_version": prompt_version, "schema_version": schema_version},
        "calibration": {"reference": calibration_ref, "verified": decision.action in (Action.AUTO_APPROVE, Action.SHADOW) and calibration_ref != "not-verified"},
        "review": {"risk": getattr(getattr(review, "risk", None), "value", None), "approve_confidence": getattr(review, "approve_confidence", None), "risk_confidence": getattr(review, "risk_confidence", None), "checklist": _json_value(getattr(review, "required_checklist_items", ())), "concerns": _json_value(getattr(review, "concerns", ())), "suggestions": list(getattr(review, "suggestions", ()))},
        "route": _route_breakdown(review, route),
        "provider": provider,
        "dry_run": not execute,
    }


def _plan_value(plan: Any) -> Any:
    """Serialize public plan fields without embedding private approval context."""
    if is_dataclass(plan):
        return {item.name: _json_value(getattr(plan, item.name)) for item in fields(plan) if item.name != "approval_context"}
    value = _json_value(plan)
    return dict(value) if isinstance(value, Mapping) else value


def _build_plan(client: Any, snapshot: Any, decision: PolicyDecision, *, reviewers: Sequence[str], team_reviewers: Sequence[str], trusted_reviewers: Sequence[str], policy_version: str, summary: str, config: PolicyConfig, review: Any = None, calibration: Any = None, comment_only: bool = False) -> Any:
    from .github import ApprovalContext
    if comment_only:
        decision = PolicyDecision(Action.ESCALATE, decision.reasons)
        reviewers, team_reviewers = (), ()
    kwargs: dict[str, Any] = {"allowlisted_repositories": tuple(config.allowlisted_repositories)}
    if decision.action is Action.AUTO_APPROVE:
        kwargs["approval_context"] = ApprovalContext(review=review, policy=config, calibration=calibration)
    return client.build_plan(snapshot, decision, reviewers, team_reviewers, trusted_reviewers, policy_version, summary, **kwargs)


def _calibrate_command(input_path: str, config_path: Optional[str]) -> Mapping[str, Any]:
    records = _read_json(input_path)
    if isinstance(records, Mapping):
        records = records.get("records", records.get("calibration"))
    if not isinstance(records, list):
        raise ValueError("calibration input must be an array or object with records")
    config = dict(_github_config(config_path))
    nested = config.get("policy")
    if isinstance(nested, Mapping):
        merged = dict(nested)
        merged.update({key: value for key, value in config.items() if key not in ("policy", "calibration")})
        config = merged
    from .provider import PROMPT_VERSION, SCHEMA_VERSION
    report = summarize(records, bins=int(config.get("bins", 10)), selection_threshold=float(config.get("selection_threshold", .90)))
    model_id = str(config.get("calibration_model_id", config.get("model_id", "")))
    ready, reasons = readiness(
        report,
        min_samples=int(config.get("calibration_min_samples", config.get("min_samples", 299))),
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
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
    provider_result = None
    if review_data is None:
        from .provider import JevProvider, PROMPT_VERSION, SCHEMA_VERSION

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
        config = replace(config, calibration_model_id=provider_model, calibration_prompt_version=PROMPT_VERSION, calibration_schema_version=SCHEMA_VERSION)
    decision = evaluate(pr, review, config, calibration)
    result = {
        "action": decision.action.value,
        "approve": decision.approve,
        "reasons": list(decision.reasons),
        "pr": _json_value(pr),
        "review": _json_value(review),
        "dry_run": not execute,
        "execution": {"performed": False, "simulated": True, "reason": "JSON review path has no external mutation"},
        "audit": _audit_envelope(pr, review, decision, config, execute=execute, policy_version=str((payload.get("config") or {}).get("policy_version", "v1")) if isinstance(payload.get("config") or {}, Mapping) else "v1", calibration_ref=_calibration_reference(payload.get("calibration")), provider_result=provider_result),
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


def _github_one(repository: str, number: int, *, execute: bool, config_raw: Mapping[str, Any], comment_only: bool = False) -> Mapping[str, Any]:
    from .github import ExecutionResult, GitHubClient
    from .provider import JevProvider, JevProviderError, PROMPT_VERSION, SCHEMA_VERSION

    from .presentation import render_review

    if execute and comment_only:
        raise ValueError("execute and comment-only modes are mutually exclusive")
    write = execute or comment_only
    trusted = config_raw.get("trusted_checks", config_raw.get("required_checks", {}))
    if not isinstance(trusted, Mapping):
        raise ValueError("trusted_checks must map check names to app IDs")
    freshness = config_raw.get("check_freshness_seconds", 86_400.0)
    if freshness is None:
        freshness = 86_400.0
    client = GitHubClient(bot_login=config_raw.get("bot_login"))
    snapshot = client.snapshot(repository, number, trusted, freshness)
    configured_trusted = tuple(config_raw.get("trusted_reviewers", ()))
    fallback_reviewers = tuple(config_raw.get("fallback_reviewers", ()))
    resolve_reviewers = getattr(client, "reviewers_for_snapshot", None)
    if callable(resolve_reviewers):
        route = resolve_reviewers(snapshot, configured_trusted, fallback=fallback_reviewers)
    else:
        route = parse_and_route(snapshot.pull_request.changed_paths, str(config_raw.get("codeowners", "")), configured_trusted, fallback_reviewers)
    author = getattr(snapshot.pull_request, "author", "")
    if isinstance(author, str) and author:
        route = tuple(owner for owner in route if _github_owner_name(owner) != author)
    route_users, route_teams = _split_github_routes(route)
    trusted_for_github = tuple(dict.fromkeys(configured_trusted + fallback_reviewers + tuple(_github_owner_name(v) for v in configured_trusted + fallback_reviewers)))
    # Expected SHA and passed checks are captured from one snapshot and then
    # revalidated by GitHubClient.execute() immediately before a write.
    nested_policy = config_raw.get("policy", {})
    if not isinstance(nested_policy, Mapping):
        raise ValueError("policy config must be an object")
    policy_raw = dict(nested_policy)
    for key in ("calibration_model_id", "calibration_prompt_version", "calibration_schema_version", "calibration_min_samples", "calibration_min_samples_per_decision", "calibration_max_ece", "calibration_max_brier", "calibration_max_age_days", "selection_threshold", "min_confidence", "required_checklist_decisions", "policy_id"):
        if key in config_raw and key not in policy_raw:
            policy_raw[key] = config_raw[key]
    policy_raw.setdefault("allowlisted_repositories", config_raw.get("allowlisted_repositories", ()))
    policy_raw["required_checks_by_repo"] = {repository: list(snapshot.required_checks)}
    policy_raw["passed_checks_by_repo"] = {repository: list(snapshot.pull_request.passed_checks)}
    policy_raw["expected_head_sha_by_repo"] = {repository: snapshot.pull_request.head_sha}
    policy_raw["trusted_context_id"] = _trusted_context_id(trusted, freshness)
    calibration = _calibration(config_raw.get("calibration"))
    config = _policy_config(policy_raw, execute=execute)
    provider_result = None
    try:
        provider = JevProvider(model=str(config_raw.get("model", os.environ.get("JEV_MODEL", "jev-latest"))))
        review, provider_result = provider.review_with_result(snapshot.pull_request)
    except JevProviderError as exc:
        decision = PolicyDecision(Action.ESCALATE, ("Jev provider unavailable: " + str(exc),))
        plan = _build_plan(client, snapshot, decision, reviewers=route_users, team_reviewers=route_teams, trusted_reviewers=trusted_for_github, policy_version=str(config_raw.get("policy_version", "v1")), summary=render_review(snapshot.pull_request, None, decision, config, route=route, check_evidence=getattr(snapshot, "check_evidence", ())), config=config, calibration=calibration, comment_only=comment_only)
        if repository not in frozenset(config_raw.get("allowlisted_repositories", ())):
            execution = ExecutionResult(not write, True, ("repository is not allowlisted; no external write",))
        else:
            execution = client.execute(plan, dry_run=not write)
        return {"repository": repository, "pull_request": number, "decision": _json_value(decision), "route": list(route), "plan": _plan_value(plan), "execution": _json_value(execution), "provider_error": str(exc), "dry_run": not write, "audit": _audit_envelope(snapshot.pull_request, None, decision, config, execute=write, policy_version=str(config_raw.get("policy_version", "v1")), calibration_ref=_calibration_reference(config_raw.get("calibration")), route=route)}
    if provider_result is None:
        raise RuntimeError("Jev provider returned no result")
    # Compare calibration identity to Jev's returned model, never a request
    # alias such as ``jev-latest``.
    config = replace(config, calibration_model_id=provider_result.model, calibration_prompt_version=PROMPT_VERSION, calibration_schema_version=SCHEMA_VERSION)
    decision = evaluate(snapshot.pull_request, review, config, calibration)
    configured_users = _split_github_routes(tuple(config_raw.get("reviewers", ())))[0]
    configured_teams = _split_github_routes(tuple(config_raw.get("team_reviewers", ())))[1]
    reviewers = tuple(dict.fromkeys(configured_users + route_users))
    team_reviewers = tuple(dict.fromkeys(configured_teams + route_teams))
    trusted_reviewers = trusted_for_github
    summary = render_review(snapshot.pull_request, review, decision, config, provider_result=provider_result, route=route, calibration_ref=_calibration_reference(config_raw.get("calibration")), check_evidence=getattr(snapshot, "check_evidence", ()))
    plan = _build_plan(client, snapshot, decision, reviewers=reviewers, team_reviewers=team_reviewers, trusted_reviewers=trusted_reviewers, policy_version=str(config_raw.get("policy_version", "v1")), summary=summary, config=config, review=review, calibration=calibration, comment_only=comment_only)
    if write and repository not in config.allowlisted_repositories:
        execution = ExecutionResult(False, True, ("repository is not allowlisted; no external write",))
    else:
        execution = client.execute(plan, dry_run=not write)
    return {
        "repository": repository,
        "pull_request": number,
        "decision": _json_value(decision),
        "review": _json_value(review),
        "provider_model": provider_result.model,
        "provider_request_id": provider_result.request_id,
        "route": list(route),
        "plan": _plan_value(plan),
        "execution": _json_value(execution),
        "audit": _audit_envelope(snapshot.pull_request, review, decision, config, execute=write, policy_version=str(config_raw.get("policy_version", "v1")), calibration_ref=_calibration_reference(config_raw.get("calibration")), provider_result=provider_result, route=route),
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
        return _github_one(args.repo, args.pr, execute=args.execute, config_raw=config, comment_only=args.comment_only)
    from .github import GitHubClient

    client = GitHubClient()
    pulls: list[Mapping[str, Any]] = []
    for page in range(1, 101):
        page_pulls = client.list_open_pull_requests(args.repo, page=page, per_page=100)
        pulls.extend(page_pulls)
        if len(pulls) > 10_000:
            raise RuntimeError("open pull request pagination exceeded local limit")
        if len(page_pulls) < 100:
            break
    else:
        raise RuntimeError("open pull request pagination exceeded local limit")
    results = []
    for pull in pulls:
        number = pull.get("number") if isinstance(pull, Mapping) else None
        if isinstance(number, int):
            try:
                results.append(_github_one(args.repo, number, execute=args.execute, config_raw=config, comment_only=args.comment_only))
            except (RuntimeError, ValueError) as exc:
                results.append({"pull_request": number, "action": "escalate", "error": str(exc), "dry_run": not (args.execute or args.comment_only)})
    return {"repository": args.repo, "count": len(results), "results": results, "dry_run": not (args.execute or args.comment_only)}


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
    gh_mode.add_argument("--comment-only", action="store_true", help="post evidence comments without approvals or reviewer requests")
    gh_mode.add_argument("--execute", action="store_true", help="permit approval/reviewer-request writes after all gates")
    gh_mode.add_argument("--dry-run", action="store_true", help="explicitly select default dry-run mode")
    poll = sub.add_parser("poll", help="poll configured GitHub pull requests")
    poll.add_argument("--repo", required=True)
    poll.add_argument("--config", help="JSON deployment/policy config (or JEV_CONFIG)")
    poll.add_argument("--calibration", help="calibration JSON path (overrides config value)")
    poll.add_argument("--model", help="request model alias")
    poll_mode = poll.add_mutually_exclusive_group()
    poll_mode.add_argument("--comment-only", action="store_true", help="post evidence comments without approvals or reviewer requests")
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
