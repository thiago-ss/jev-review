"""Deterministic approval gate. Model output can suggest; policy alone can approve."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import hashlib
import json
from typing import Iterable, Mapping, Optional, Tuple, Union

from .calibration import CalibrationReport, DEFAULT_REQUIRED_DECISIONS, readiness
from .models import PullRequest, Review, RiskLevel, ValidationError, parse_pr, parse_review

POLICY_IMPLEMENTATION_VERSION = "1"


class Action(str, Enum):
    AUTO_APPROVE = "auto_approve"
    ESCALATE = "escalate"
    SHADOW = "shadow"


@dataclass(frozen=True)
class PolicyConfig:
    allowlisted_repositories: frozenset[str] = frozenset()
    required_checks_by_repo: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    passed_checks_by_repo: Mapping[str, frozenset[str]] = field(default_factory=dict)
    expected_head_sha_by_repo: Mapping[str, str] = field(default_factory=dict)
    sensitive_paths: Tuple[str, ...] = (".github/**", "secrets/**", "**/secrets/**", "*.pem", "**/*.pem", "*.key", "**/*.key", "auth/**", "**/auth/**", ".env", ".env.*", "**/.env", "**/.env.*")
    max_files: int = 100
    max_additions: int = 5000
    max_deletions: int = 5000
    max_patch_bytes: int = 1_000_000
    min_confidence: float = .90
    selection_threshold: float = .90
    mode: str = "shadow"
    calibration_min_samples: int = 299
    calibration_max_age_days: Optional[float] = 90
    calibration_model_id: str = ""
    calibration_prompt_version: str = ""
    calibration_schema_version: str = ""
    policy_id: str = ""
    trusted_context_id: str = ""
    required_checklist_decisions: Tuple[str, ...] = DEFAULT_REQUIRED_DECISIONS[2:]
    calibration_min_samples_per_decision: int = 30
    calibration_max_ece: float = .10
    calibration_max_brier: float = .10
    # Compatibility names for adapters loading trusted repository policy.
    trusted_required_checks: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    trusted_passed_checks: Mapping[str, frozenset[str]] = field(default_factory=dict)
    exact_head_sha_by_repo: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.mode not in ("shadow", "active"):
            raise ValidationError("policy mode must be shadow or active")
        for value in (self.max_files, self.max_additions, self.max_deletions, self.max_patch_bytes, self.calibration_min_samples):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValidationError("policy limits must be positive integers")
        if isinstance(self.calibration_min_samples_per_decision, bool) or not isinstance(self.calibration_min_samples_per_decision, int) or self.calibration_min_samples_per_decision < 1:
            raise ValidationError("invalid per-decision calibration floor")
        if isinstance(self.min_confidence, bool) or isinstance(self.selection_threshold, bool) or not 0 <= self.min_confidence <= 1 or not 0 <= self.selection_threshold <= 1:
            raise ValidationError("invalid minimum confidence")
        if self.selection_threshold != self.min_confidence:
            raise ValidationError("selection threshold must equal minimum decision confidence")
        if not all(isinstance(item, str) and item.startswith("checklist:") and len(item) > len("checklist:") for item in self.required_checklist_decisions):
            raise ValidationError("invalid checklist calibration decisions")
        if not 0 <= self.calibration_max_ece <= 1 or not 0 <= self.calibration_max_brier <= 1:
            raise ValidationError("invalid calibration quality limits")


@dataclass(frozen=True)
class PolicyDecision:
    action: Action
    reasons: Tuple[str, ...]
    approve: bool = False

    @property
    def auto_approved(self) -> bool:
        return self.action is Action.AUTO_APPROVE


class PolicyEvaluator:
    """Small adapter retaining one deterministic policy interface."""

    def __init__(self, config: Optional[PolicyConfig] = None, calibration: Optional[CalibrationReport] = None) -> None:
        self.config = config or PolicyConfig()
        self.calibration = calibration

    def evaluate(self, pr: Union[PullRequest, Mapping[str, object]], review: Union[Review, Mapping[str, object]]) -> PolicyDecision:
        return evaluate(pr, review, self.config, self.calibration)


def _trusted_ci_ok(pr: PullRequest, config: PolicyConfig) -> bool:
    required = tuple(config.required_checks_by_repo.get(pr.repository, config.trusted_required_checks.get(pr.repository, ())))
    passed = config.passed_checks_by_repo.get(pr.repository, config.trusted_passed_checks.get(pr.repository, frozenset()))
    return bool(required) and all(check in passed for check in required)


def _sensitive(pr: PullRequest, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for path in pr.changed_paths for pattern in patterns)


def policy_fingerprint(config: PolicyConfig) -> str:
    """Hash approval-affecting static policy; omit live SHA/check/model evidence."""
    checks = dict(config.trusted_required_checks)
    checks.update(config.required_checks_by_repo)
    payload = {
        "implementation": POLICY_IMPLEMENTATION_VERSION,
        "allowlisted_repositories": sorted(config.allowlisted_repositories),
        "required_checks_by_repo": {k: sorted(v) for k, v in sorted(checks.items())},
        "sensitive_paths": list(config.sensitive_paths), "max_files": config.max_files,
        "max_additions": config.max_additions, "max_deletions": config.max_deletions,
        "max_patch_bytes": config.max_patch_bytes, "min_confidence": config.min_confidence,
        "selection_threshold": config.selection_threshold, "calibration_max_age_days": config.calibration_max_age_days,
        "required_checklist_decisions": list(config.required_checklist_decisions),
        "trusted_context_id": config.trusted_context_id,
        "calibration_min_samples": config.calibration_min_samples,
        "calibration_min_samples_per_decision": config.calibration_min_samples_per_decision,
        "calibration_max_ece": config.calibration_max_ece, "calibration_max_brier": config.calibration_max_brier,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def evaluate(pr: Union[PullRequest, Mapping[str, object]], review: Union[Review, Mapping[str, object]], config: Optional[PolicyConfig] = None, calibration: Optional[CalibrationReport] = None) -> PolicyDecision:
    config = config or PolicyConfig()
    reasons = []
    if not config.policy_id or config.policy_id != policy_fingerprint(config):
        reasons.append("policy identity is missing or does not match configuration")
    try:
        pr = parse_pr(pr)
        review = parse_review(review)
    except ValidationError as exc:
        return PolicyDecision(Action.ESCALATE, ("invalid input: " + str(exc),))
    if review.contradictory:
        reasons.append("review decisions contradict")
    if not review.approve:
        reasons.append("review did not approve")
    if review.risk is not RiskLevel.LOW:
        reasons.append("risk is not low")
    if any(item.status.value in ("fail", "warn", "unknown") or item.blocking for item in review.required_checklist_items):
        reasons.append("required checklist has blocker or uncertainty")
    if any(item.confidence < config.min_confidence for item in review.required_checklist_items):
        reasons.append("checklist confidence below threshold")
    expected_checklist = {item[len("checklist:"):] for item in config.required_checklist_decisions}
    actual_checklist = {item.name[len("checklist:"):] if item.name.startswith("checklist:") else item.name for item in review.required_checklist_items}
    if actual_checklist != expected_checklist:
        reasons.append("required named checklist fields do not match policy")
    if review.concerns:
        reasons.append("review has concerns")
    if pr.repository not in config.allowlisted_repositories:
        reasons.append("repository is not allowlisted")
    if not _trusted_ci_ok(pr, config):
        reasons.append("trusted required CI is not passing")
    expected = config.expected_head_sha_by_repo.get(pr.repository, config.exact_head_sha_by_repo.get(pr.repository))
    if not expected or pr.head_sha != expected:
        reasons.append("head SHA is not exact trusted SHA")
    if len(pr.files) > config.max_files or pr.additions > config.max_additions or pr.deletions > config.max_deletions:
        reasons.append("change exceeds policy limits")
    if sum(len(f.patch.encode("utf-8")) for f in pr.files) > config.max_patch_bytes:
        reasons.append("patch exceeds byte limit")
    if _sensitive(pr, config.sensitive_paths):
        reasons.append("sensitive path changed")
    if review.approve_confidence < config.min_confidence or review.risk_confidence < config.min_confidence:
        reasons.append("decision confidence below threshold")
    if calibration is None:
        reasons.append("no calibration evidence")
    else:
        ready, calibration_reasons = readiness(calibration, min_samples=config.calibration_min_samples, min_samples_per_decision=config.calibration_min_samples_per_decision, model_id=config.calibration_model_id, prompt_version=config.calibration_prompt_version, schema_version=config.calibration_schema_version, repository=pr.repository, policy_id=config.policy_id, required_decisions=("approve", "risk") + config.required_checklist_decisions, max_age_days=config.calibration_max_age_days, selection_threshold=config.selection_threshold, max_ece=config.calibration_max_ece, max_brier=config.calibration_max_brier)
        if not ready:
            reasons.extend("calibration: " + reason for reason in calibration_reasons)
        elif not calibration.covers(("approve", "risk", "checklist")):
            reasons.append("calibration lacks per-decision coverage")
        elif not all(calibration.confidence_for("checklist:" + (item.name[len("checklist:"):] if item.name.startswith("checklist:") else item.name), item.confidence, config.calibration_min_samples_per_decision, config.calibration_max_ece) for item in review.required_checklist_items):
            reasons.append("calibration lacks checklist confidence support")
        elif not calibration.confidence_for("approve", review.approve_confidence, config.calibration_min_samples_per_decision, config.calibration_max_ece) or not calibration.confidence_for("risk", review.risk_confidence, config.calibration_min_samples_per_decision, config.calibration_max_ece):
            reasons.append("calibration lacks decision confidence support")
    if reasons:
        return PolicyDecision(Action.ESCALATE, tuple(dict.fromkeys(reasons)))
    if config.mode == "shadow":
        return PolicyDecision(Action.SHADOW, ("shadow mode",))
    return PolicyDecision(Action.AUTO_APPROVE, (), approve=True)


# Names used by integrations.
decide = evaluate
evaluate_policy = evaluate
Decision = PolicyDecision
