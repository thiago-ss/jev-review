"""Empirical calibration evidence. No report qualifies without explicit provenance."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Iterable, Mapping, Optional, Tuple, Union

from .models import ValidationError

DECISIONS = ("approve", "risk", "checklist")
DEFAULT_REQUIRED_DECISIONS = ("approve", "risk", "checklist:correctness", "checklist:security", "checklist:tests")


def _decision_group(value: str, wanted: str) -> bool:
    return value == wanted or (wanted == "checklist" and value.startswith("checklist:"))


@dataclass(frozen=True)
class CalibrationRecord:
    probability: float
    label: bool
    decision: str = "approve"
    model_id: str = ""
    prompt_version: str = ""
    schema_version: str = ""
    repository: str = ""
    heldout: Optional[bool] = None
    synthetic: Optional[bool] = None
    observed_at: Optional[datetime] = None
    selected: Optional[bool] = None
    sample_id: str = ""
    policy_id: str = ""
    stratum: Optional[str] = None

    def __post_init__(self) -> None:
        if isinstance(self.probability, bool) or not isinstance(self.probability, (int, float)) or not math.isfinite(float(self.probability)) or not 0 <= float(self.probability) <= 1:
            raise ValidationError("calibration probability must be finite [0,1]")
        if not isinstance(self.label, bool) or not isinstance(self.decision, str) or (self.decision not in DECISIONS and not self.decision.startswith("checklist:")):
            raise ValidationError("malformed calibration record")
        for identity_value in (self.model_id, self.prompt_version, self.schema_version, self.repository, self.sample_id, self.policy_id):
            if not isinstance(identity_value, str):
                raise ValidationError("calibration identity must be string")
        if self.stratum is not None and (not isinstance(self.stratum, str) or not self.stratum):
            raise ValidationError("stratum must be nonempty string")
        for provenance_value, provenance_name in ((self.heldout, "heldout"), (self.synthetic, "synthetic"), (self.selected, "selected")):
            if provenance_value is not None and not isinstance(provenance_value, bool):
                raise ValidationError("malformed " + provenance_name + " provenance")
        if self.observed_at is not None and not isinstance(self.observed_at, datetime):
            raise ValidationError("observed_at must be datetime")

    @classmethod
    def from_mapping(cls, data: Mapping[str, object]) -> "CalibrationRecord":
        if not isinstance(data, Mapping):
            raise ValidationError("calibration record must be mapping")
        try:
            values: Any = data
            required = ("heldout", "synthetic", "selected", "sample_id", "observed_at", "policy_id")
            missing = [key for key in required if key not in values]
            if missing:
                raise ValidationError("missing calibration provenance: " + ",".join(missing))
            at = values.get("observed_at")
            if isinstance(at, str):
                at = datetime.fromisoformat(at.replace("Z", "+00:00"))
            return cls(values["probability"], values["label"], values.get("decision", "approve"), values["model_id"], values["prompt_version"], values["schema_version"], values["repository"], values.get("heldout"), values.get("synthetic"), at, values.get("selected"), values.get("sample_id", ""), values.get("policy_id", ""), values.get("stratum"))
        except KeyError as exc:
            raise ValidationError("missing calibration identity: " + str(exc)) from exc
        except ValueError as exc:
            raise ValidationError("malformed calibration timestamp") from exc


@dataclass(frozen=True)
class ReliabilityPoint:
    lower: float
    upper: float
    count: int
    mean_probability: float
    observed_rate: float


@dataclass(frozen=True)
class CalibrationReport:
    records: Tuple[CalibrationRecord, ...]
    brier: Mapping[str, float]
    ece: Mapping[str, float]
    reliability: Mapping[str, Tuple[ReliabilityPoint, ...]]
    false_approval_errors: int
    false_approval_trials: int
    false_approval_upper_bound: float
    identity: Tuple[str, str, str, str]
    heldout: bool
    synthetic: bool
    latest_at: Optional[datetime]
    oldest_at: Optional[datetime]
    selection_threshold: float = .90
    duplicate_sample_ids: Tuple[str, ...] = ()
    duplicate_approval_ids: Tuple[str, ...] = ()
    missing_sample_ids: bool = False
    policy_ids: Tuple[str, ...] = ()
    candidate_prs: int = 0
    selected_prs: int = 0
    coverage: float = 0.0
    abstention_rate: float = 1.0
    selected_error_rate: Optional[float] = None
    strata: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    @property
    def error_rate(self) -> Optional[float]:
        return self.selected_error_rate

    @property
    def selection_coverage(self) -> float:
        return self.coverage

    @property
    def abstention_count(self) -> int:
        return max(0, self.candidate_prs - self.selected_prs)

    def confidence_for(self, decision: str, probability: float, min_samples: int = 1, max_error: float = .10) -> bool:
        if (not isinstance(decision, str) or (decision not in DECISIONS and not decision.startswith("checklist:"))) or isinstance(probability, bool) or not isinstance(probability, (int, float)) or not math.isfinite(float(probability)):
            return False
        if min_samples < 1 or not 0 <= max_error <= 1:
            return False
        points = self.reliability.get(decision, ())
        return any(point.count >= min_samples and (point.lower <= probability < point.upper or (point.upper == 1.0 and probability == 1.0)) and point.mean_probability + 1e-12 >= probability and point.observed_rate + 1e-12 >= probability - max_error for point in points)

    def covers(self, decisions: Iterable[str]) -> bool:
        return all(any(_decision_group(r.decision, d) for r in self.records) for d in decisions)


def false_approval_upper_bound(errors: int, trials: int, confidence: float = .95) -> float:
    """Exact one-sided Clopper-Pearson upper endpoint, stable for large n."""
    if trials <= 0 or errors < 0 or errors > trials or not 0 < confidence < 1:
        raise ValidationError("invalid binomial sample")
    if errors == trials:
        return 1.0
    target = 1.0 - confidence

    def cdf(p: float) -> float:
        logs = [math.lgamma(trials + 1) - math.lgamma(k + 1) - math.lgamma(trials - k + 1) + k * math.log(p) + (trials - k) * math.log1p(-p) for k in range(errors + 1) if (p > 0 or k == 0) and (p < 1 or k == trials)]
        top = max(logs)
        return math.exp(top) * sum(math.exp(item - top) for item in logs)

    low, high = 0.0, 1.0
    for _ in range(90):
        middle = (low + high) / 2
        if cdf(middle) > target:
            low = middle
        else:
            high = middle
    return high


def summarize(records: Iterable[Union[CalibrationRecord, Mapping[str, object]]], bins: int = 10, selection_threshold: float = .90) -> CalibrationReport:
    parsed = tuple(r if isinstance(r, CalibrationRecord) else CalibrationRecord.from_mapping(r) for r in records)
    if not parsed or isinstance(bins, bool) or not isinstance(bins, int) or not 1 <= bins <= 100 or isinstance(selection_threshold, bool) or not isinstance(selection_threshold, (int, float)) or not math.isfinite(float(selection_threshold)) or not 0 <= float(selection_threshold) <= 1:
        raise ValidationError("calibration records and valid bins required")
    identities = {(r.model_id, r.prompt_version, r.schema_version, r.repository) for r in parsed}
    identity = next(iter(identities)) if len(identities) == 1 else ("", "", "", "")
    brier, ece, reliability = {}, {}, {}
    for decision in sorted({r.decision for r in parsed} | set(DECISIONS)):
        group = tuple(r for r in parsed if r.decision == decision)
        if not group:
            continue
        brier[decision] = sum((r.probability - int(r.label)) ** 2 for r in group) / len(group)
        points, weighted = [], 0.0
        for index in range(bins):
            lower, upper = index / bins, (index + 1) / bins
            chosen = tuple(r for r in group if lower <= r.probability < upper or (index == bins - 1 and r.probability == upper))
            if not chosen:
                continue
            mean = sum(r.probability for r in chosen) / len(chosen)
            observed = sum(r.label for r in chosen) / len(chosen)
            weighted += len(chosen) / len(group) * abs(mean - observed)
            points.append(ReliabilityPoint(lower, upper, len(chosen), mean, observed))
        ece[decision], reliability[decision] = weighted, tuple(points)
    selected_rows = tuple(r for r in parsed if r.decision == "approve" and r.selected is True)
    unique_approvals = {}
    for row in selected_rows:
        if row.sample_id and row.sample_id not in unique_approvals:
            unique_approvals[row.sample_id] = row
    approvals = tuple(unique_approvals.values())
    errors = sum(not r.label for r in approvals)
    candidate_ids = {r.sample_id for r in parsed if r.decision == "approve" and r.sample_id}
    candidate_count, selected_count = len(candidate_ids), len(approvals)
    coverage = selected_count / candidate_count if candidate_count else 0.0
    strata = {}
    for stratum in sorted({r.stratum for r in parsed if r.stratum is not None}):
        candidates = {r.sample_id for r in parsed if r.decision == "approve" and r.stratum == stratum and r.sample_id}
        chosen = tuple(r for r in approvals if r.stratum == stratum)
        strata[stratum] = {"candidate_prs": float(len(candidates)), "selected_prs": float(len(chosen)), "coverage": len(chosen) / len(candidates) if candidates else 0.0, "error_rate": sum(not r.label for r in chosen) / len(chosen) if chosen else 0.0}
    duplicate_ids = {r.sample_id for r in parsed if r.sample_id and sum(x.sample_id == r.sample_id and x.decision == r.decision for x in parsed) > 1}
    duplicate_approval_ids = {r.sample_id for r in selected_rows if r.sample_id and sum(x.sample_id == r.sample_id for x in selected_rows) > 1}
    return CalibrationReport(parsed, brier, ece, reliability, errors, len(approvals), false_approval_upper_bound(errors, len(approvals)) if approvals else 1.0, identity, all(r.heldout is True for r in parsed), any(r.synthetic is True for r in parsed), max((r.observed_at for r in parsed if r.observed_at is not None), default=None), min((r.observed_at for r in parsed if r.observed_at is not None), default=None), float(selection_threshold), tuple(sorted(duplicate_ids)), tuple(sorted(duplicate_approval_ids)), any(not r.sample_id for r in parsed), tuple(sorted({r.policy_id for r in parsed})), candidate_count, selected_count, coverage, 1.0 - coverage, errors / len(approvals) if approvals else None, strata)


def readiness(report: CalibrationReport, *, min_samples: int = 299, min_samples_per_decision: int = 30, model_id: str = "", prompt_version: str = "", schema_version: str = "", repository: str = "", policy_id: str = "", required_decisions: Iterable[str] = DEFAULT_REQUIRED_DECISIONS, max_age_days: Optional[float] = 90, now: Optional[datetime] = None, false_approval_limit: float = .01, selection_threshold: Optional[float] = .90, max_ece: float = .10, max_brier: float = .10) -> Tuple[bool, Tuple[str, ...]]:
    reasons = []
    required = tuple(required_decisions)
    if "checklist" in required:
        reasons.append("aggregate checklist calibration unsupported")
    if len(report.records) < min_samples:
        reasons.append("insufficient samples")
    if min_samples_per_decision < 1:
        raise ValidationError("invalid per-decision sample floor")
    for decision in required:
        count = sum(_decision_group(r.decision, decision) for r in report.records)
        if count < min_samples_per_decision:
            reasons.append("insufficient " + decision + " samples")
        if decision in report.ece and report.ece[decision] > max_ece:
            reasons.append(decision + " ECE exceeds limit")
        if decision in report.brier and report.brier[decision] > max_brier:
            reasons.append(decision + " Brier exceeds limit")
    if report.synthetic or any(r.synthetic is not False for r in report.records):
        reasons.append("synthetic evidence")
    if not report.heldout or any(r.heldout is not True for r in report.records):
        reasons.append("non-heldout evidence")
    if report.duplicate_sample_ids or report.duplicate_approval_ids:
        reasons.append("duplicate sample IDs")
    if report.missing_sample_ids:
        reasons.append("sample IDs required")
    if not all(report.identity):
        reasons.append("incomplete or mixed evidence identity")
    if not policy_id or not report.policy_ids or report.policy_ids != (policy_id,):
        reasons.append("policy identity mismatch or missing")
    expected = (model_id, prompt_version, schema_version, repository)
    if not all(expected) or report.identity != expected:
        reasons.append("evidence identity mismatch")
    if report.false_approval_upper_bound > false_approval_limit:
        reasons.append("false approval bound exceeds limit")
    if any(r.selected is None for r in report.records):
        reasons.append("selection provenance missing")
    if selection_threshold is not None and report.selection_threshold != selection_threshold:
        reasons.append("selection threshold mismatch")
    current = now or datetime.now(timezone.utc)
    if report.oldest_at is None or any(r.observed_at is None for r in report.records):
        reasons.append("timestamp provenance missing")
    else:
        for record in report.records:
            observed = record.observed_at
            assert observed is not None
            aware = observed if observed.tzinfo else observed.replace(tzinfo=timezone.utc)
            if aware > current:
                reasons.append("future timestamp")
            if max_age_days is not None and (current - aware).total_seconds() > max_age_days * 86400:
                reasons.append("stale evidence")
    return not reasons, tuple(dict.fromkeys(reasons))


calibrate = summarize
production_readiness = readiness
