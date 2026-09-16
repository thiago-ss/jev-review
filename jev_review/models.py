"""Typed, fail-closed models at the autonomous review trust seam."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional, Tuple, Union


class ValidationError(ValueError):
    """Input cannot safely be interpreted as a review or pull request."""


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChecklistStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ChecklistItem:
    name: str
    status: ChecklistStatus
    confidence: float
    blocking: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("checklist item name required")
        object.__setattr__(self, "status", _enum(ChecklistStatus, self.status, "checklist status"))
        _probability(self.confidence, "checklist confidence")
        if not isinstance(self.blocking, bool):
            raise ValidationError("checklist blocking must be boolean")


@dataclass(frozen=True)
class Concern:
    message: str
    path: str
    line: int
    severity: RiskLevel = RiskLevel.MEDIUM

    def __post_init__(self) -> None:
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValidationError("concern message required")
        if not isinstance(self.path, str) or not self.path.strip() or self.path.startswith("/"):
            raise ValidationError("concern path must be repository-relative")
        if isinstance(self.line, bool) or not isinstance(self.line, int) or self.line < 1:
            raise ValidationError("concern line must be positive integer")
        object.__setattr__(self, "severity", _enum(RiskLevel, self.severity, "concern severity"))


@dataclass(frozen=True)
class ChangedFile:
    path: str
    patch: str
    additions: int = 0
    deletions: int = 0
    truncated: bool = False
    previous_path: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip() or self.path.startswith("/") or ".." in self.path.split("/"):
            raise ValidationError("invalid changed file path")
        if not isinstance(self.patch, str) or not self.patch.strip():
            raise ValidationError("missing diff for " + self.path)
        if not isinstance(self.truncated, bool) or self.truncated:
            raise ValidationError("truncated diff for " + self.path)
        for value, label in ((self.additions, "additions"), (self.deletions, "deletions")):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationError(label + " must be nonnegative integer")
        patch_additions = sum(1 for line in self.patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        patch_deletions = sum(1 for line in self.patch.splitlines() if line.startswith("-") and not line.startswith("---"))
        if self.additions == 0 and patch_additions:
            object.__setattr__(self, "additions", patch_additions)
        elif self.additions != patch_additions:
            raise ValidationError("additions do not match patch for " + self.path)
        if self.deletions == 0 and patch_deletions:
            object.__setattr__(self, "deletions", patch_deletions)
        elif self.deletions != patch_deletions:
            raise ValidationError("deletions do not match patch for " + self.path)
        if self.previous_path is not None and (not isinstance(self.previous_path, str) or not self.previous_path.strip()):
            raise ValidationError("invalid previous file path")


@dataclass(frozen=True)
class PullRequest:
    repository: str
    number: int
    base_sha: str
    head_sha: str
    files: Tuple[ChangedFile, ...]
    required_checks: Tuple[str, ...] = ()
    passed_checks: Tuple[str, ...] = ()
    title: str = ""
    body: str = ""
    truncated: bool = False
    author: str = ""
    base_branch: str = ""
    observed_head_sha: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.repository, str) or not self.repository.strip() or "/" not in self.repository:
            raise ValidationError("repository must be owner/name")
        if isinstance(self.number, bool) or not isinstance(self.number, int) or self.number < 1:
            raise ValidationError("pull request number must be positive integer")
        for value, label in ((self.base_sha, "base_sha"), (self.head_sha, "head_sha")):
            if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdefABCDEF" for c in value):
                raise ValidationError("invalid " + label)
        if not self.files or any(not isinstance(item, ChangedFile) for item in self.files):
            raise ValidationError("complete changed files required")
        if self.truncated:
            raise ValidationError("truncated pull request")
        if not isinstance(self.title, str) or not isinstance(self.body, str):
            raise ValidationError("title/body must be strings")
        if not isinstance(self.author, str) or not isinstance(self.base_branch, str):
            raise ValidationError("author/base branch must be strings")
        if not self.observed_head_sha:
            object.__setattr__(self, "observed_head_sha", self.head_sha)
        if not isinstance(self.observed_head_sha, str) or len(self.observed_head_sha) != 40 or any(c not in "0123456789abcdefABCDEF" for c in self.observed_head_sha):
            raise ValidationError("invalid observed_head_sha")
        for values, label in ((self.required_checks, "required checks"), (self.passed_checks, "passed checks")):
            if not isinstance(values, tuple):
                raise ValidationError(label + " malformed")
            if any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValidationError(label + " malformed")

    @property
    def changed_paths(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(p for f in self.files for p in ((f.previous_path, f.path) if f.previous_path else (f.path,))))

    @property
    def additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def deletions(self) -> int:
        return sum(f.deletions for f in self.files)


@dataclass(frozen=True)
class Review:
    approve: bool
    risk: RiskLevel
    required_checklist_items: Tuple[ChecklistItem, ...]
    approve_confidence: float
    risk_confidence: float
    concerns: Tuple[Concern, ...] = ()
    suggestions: Tuple[str, ...] = ()
    native_confidences: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.approve, bool):
            raise ValidationError("approve must be boolean")
        object.__setattr__(self, "risk", _enum(RiskLevel, self.risk, "risk"))
        if not self.required_checklist_items or any(not isinstance(i, ChecklistItem) for i in self.required_checklist_items):
            raise ValidationError("required checklist items required")
        _probability(self.approve_confidence, "approve confidence")
        _probability(self.risk_confidence, "risk confidence")
        if any(not isinstance(c, Concern) for c in self.concerns):
            raise ValidationError("malformed concerns")
        names = [item.name for item in self.required_checklist_items]
        if len(names) != len(set(names)):
            raise ValidationError("duplicate checklist item")
        if any(not isinstance(s, str) or not s.strip() for s in self.suggestions):
            raise ValidationError("malformed suggestions")
        if not isinstance(self.native_confidences, Mapping):
            raise ValidationError("malformed native confidences")
        for value in self.native_confidences.values():
            _probability(value, "native confidence")

    @property
    def contradictory(self) -> bool:
        return self.approve and (self.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL) or any(i.status == ChecklistStatus.FAIL or i.blocking for i in self.required_checklist_items))

    @property
    def approval_confidence(self) -> float:
        return self.approve_confidence


def _enum(enum_type: Any, value: Any, label: str) -> Any:
    if isinstance(value, enum_type):
        return value
    if not isinstance(value, str):
        raise ValidationError("unknown " + label)
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ValidationError("unknown " + label) from exc


def _probability(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
        raise ValidationError(label + " must be finite probability")
    return float(value)


def parse_pr(payload: Union[Mapping[str, Any], PullRequest]) -> PullRequest:
    if isinstance(payload, PullRequest):
        return payload
    if not isinstance(payload, Mapping):
        raise ValidationError("pull request must be mapping")
    try:
        raw_files = payload["files"]
        patches = payload.get("patches", {})
        if isinstance(patches, Mapping):
            raw_files = tuple((dict(f, patch=patches[f["path"]]) if isinstance(f, Mapping) and "patch" not in f and f.get("path") in patches else f) for f in raw_files)
        files = tuple(parse_file(f) for f in raw_files)
        return PullRequest(
            repository=payload["repository"], number=payload["number"], base_sha=payload["base_sha"], head_sha=payload["head_sha"],
            files=files, required_checks=tuple(payload.get("required_checks", ())), passed_checks=tuple(payload.get("passed_checks", ())),
            title=payload.get("title", ""), body=payload.get("body", ""), truncated=payload.get("truncated", False), author=payload.get("author", ""), base_branch=payload.get("base_branch", ""), observed_head_sha=payload.get("observed_head_sha", payload.get("observed_sha", "")),
        )
    except KeyError as exc:
        raise ValidationError("missing pull request field: " + str(exc)) from exc
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("malformed pull request") from exc


def parse_file(payload: Union[Mapping[str, Any], ChangedFile]) -> ChangedFile:
    if isinstance(payload, ChangedFile):
        return payload
    if not isinstance(payload, Mapping):
        raise ValidationError("changed file must be mapping")
    if "patch" not in payload and "diff" in payload:
        payload = dict(payload); payload["patch"] = payload["diff"]
    try:
        return ChangedFile(payload["path"], payload["patch"], payload.get("additions", 0), payload.get("deletions", 0), payload.get("truncated", False), payload.get("previous_path"))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("malformed changed file") from exc


def parse_review(payload: Union[Mapping[str, Any], Review]) -> Review:
    if isinstance(payload, Review):
        return payload
    if not isinstance(payload, Mapping):
        raise ValidationError("review must be mapping")
    try:
        items = tuple(parse_checklist(i) for i in payload["required_checklist_items"])
        concerns = tuple(parse_concern(c) for c in payload.get("concerns", ()))
        suggestions = tuple(payload.get("suggestions", ()))
        native = payload.get("native_confidences", {})
        if "confidence" in payload and "approve" not in native:
            native = dict(native); native["approve"] = payload["confidence"]
        confidence = payload.get("confidence", {})
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            confidence = {}
        if not isinstance(confidence, Mapping):
            raise ValidationError("confidence must be mapping or finite number")
        approve_confidence = payload.get("approve_confidence", confidence.get("approve"))
        risk_confidence = payload.get("risk_confidence", confidence.get("risk"))
        if approve_confidence is None or risk_confidence is None:
            raise ValidationError("approve/risk confidence required")
        return Review(payload["approve"], payload["risk"], items, approve_confidence, risk_confidence, concerns, suggestions, native)
    except KeyError as exc:
        raise ValidationError("missing review field: " + str(exc)) from exc
    except (TypeError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("malformed review") from exc


def parse_checklist(payload: Union[Mapping[str, Any], ChecklistItem]) -> ChecklistItem:
    if isinstance(payload, ChecklistItem):
        return payload
    if not isinstance(payload, Mapping):
        raise ValidationError("checklist item must be mapping")
    try:
        return ChecklistItem(payload["name"], payload["status"], payload["confidence"], payload.get("blocking", False))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("malformed checklist item") from exc


def parse_concern(payload: Union[Mapping[str, Any], Concern]) -> Concern:
    if isinstance(payload, Concern):
        return payload
    if not isinstance(payload, Mapping):
        raise ValidationError("concern must be mapping")
    try:
        return Concern(payload["message"], payload["path"], payload["line"], payload.get("severity", RiskLevel.MEDIUM))
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise
        raise ValidationError("malformed concern") from exc


# Friendly aliases used by adapters.
PRMetadata = PullRequest
PRFile = ChangedFile
ReviewOutput = Review
Change = PullRequest
ReviewPacket = Review
