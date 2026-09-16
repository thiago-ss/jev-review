"""Bounded, safe Markdown presentation for GitHub pull-request reviews.

The renderer is deliberately separate from policy and GitHub writes.  It only
turns already validated evidence into a readable comment.  Repository text is
untrusted, so every value that reaches Markdown is escaped and action links are
constructed only from validated GitHub Actions context.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import math
import os
import re
from typing import Any, Mapping, Optional, Sequence, cast
from urllib.parse import urlsplit

from .models import Review, ValidationError, parse_pr, parse_review
from .policy import PolicyDecision


MAX_MARKDOWN_CHARS = 10_000
MAX_RAW_CHARS = 4_000
MAX_VALUE_CHARS = 320
MAX_FILES = 40
MAX_CONCERNS = 20
MAX_SUGGESTIONS = 12
_REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,98})/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,99})$")
_SHA = re.compile(r"^[0-9a-fA-F]{40}$")
_POSITIVE_INTEGER = re.compile(r"^[1-9][0-9]{0,18}$")
_UNVERIFIED_CALIBRATION = frozenset(("", "not-verified", "embedded", "unverified", "none"))


def render_review(
    pr: Any,
    review: Optional[Any],
    decision: Any,
    config: Any,
    provider_result: Optional[Any] = None,
    route: Sequence[str] = (),
    calibration_ref: Any = "not-verified",
    check_evidence: Sequence[Mapping[str, Any]] = (),
    investigation: Optional[Mapping[str, Any]] = None,
) -> str:
    """Render a GitHub-safe, visual review comment.

    ``review`` may be absent when Jev is unavailable.  In that case the output
    explicitly reports an unavailable provider and never fills in risk,
    checklist, or confidence values.  Calibration is reported as verified only
    when a typed policy decision passed and a non-empty reference was supplied.
    """
    parsed_pr = _parse_or_none(pr, parse_pr)
    parsed_review = _parse_or_none(review, parse_review)
    provider_error = _provider_error(provider_result)
    action = _action(decision)
    calibrated, calibration_text = _calibration_status(calibration_ref, decision)
    server = _safe_server_url(os.environ.get("GITHUB_SERVER_URL", "https://github.com"))

    sections = []
    sections.append("## Jev / Review X-ray" if investigation is not None else _header(action, parsed_review, provider_error))
    if investigation is not None:
        sections.append(_investigation(investigation))
    sections.append(_mode_note(config))
    links = _links(parsed_pr, server)
    if links:
        sections.append("**Trace:** " + " · ".join(links))
    sections.append("**Evidence status:** " + calibration_text)
    if investigation is not None:
        sections.append("<details>\n<summary>Baseline decision and checklist</summary>\n\n" + _decision_table(parsed_review, calibrated) + "\n\n" + _checklist_table(parsed_review, calibrated) + "\n\n</details>")
    else:
        sections.append(_decision_table(parsed_review, calibrated))
        sections.append(_checklist_table(parsed_review, calibrated))
    sections.append(_ci_table(parsed_pr, check_evidence))
    sections.append(_scope(parsed_pr))
    sections.append(_reasons_and_route(decision, parsed_review, route, provider_error))
    sections.append(_suggestions(parsed_review))
    sections.append(_provider_summary(provider_result, provider_error))
    sections.append(_raw_evidence(parsed_pr, parsed_review, decision, config, provider_result, route, calibration_ref, provider_error))

    rendered = "\n\n".join(section for section in sections if section)
    if len(rendered) <= MAX_MARKDOWN_CHARS:
        return rendered
    # The raw details are expendable before visible evidence.  Keep a valid
    # closing details/code fence even for unusually large provider responses.
    raw_marker = "\n\n<details>\n<summary>Raw structured evidence</summary>"
    raw_start = rendered.rfind(raw_marker)
    if raw_start >= 0:
        rendered = rendered[:raw_start] + "\n\n<details>\n<summary>Raw structured evidence</summary>\n\n_omitted: output limit reached._\n\n</details>"
    if len(rendered) <= MAX_MARKDOWN_CHARS:
        return rendered
    return rendered[: MAX_MARKDOWN_CHARS - len("\n\n_omitted: output limit reached._")].rstrip() + "\n\n_omitted: output limit reached._"


def _parse_or_none(value: Any, parser: Any) -> Any:
    if value is None:
        return None
    try:
        return parser(value)
    except (TypeError, ValueError, ValidationError):
        return None


def _string_attr(value: Any, name: str) -> str:
    result = getattr(value, name, "") if value is not None else ""
    return result if isinstance(result, str) else ""


def _action(decision: Any) -> str:
    value = getattr(decision, "action", decision)
    value = getattr(value, "value", value)
    return value if isinstance(value, str) and value in {"auto_approve", "escalate", "shadow"} else "unknown"


def _header(action: str, review: Optional[Review], provider_error: Optional[str]) -> str:
    labels = {
        "auto_approve": ("ELIGIBLE", "policy gates passed; approval remains a separate GitHub action"),
        "shadow": ("SHADOW", "informational review; no approval issued"),
        "escalate": ("HUMAN REVIEW", "policy requires human review"),
        "unknown": ("UNKNOWN", "policy action unavailable"),
    }
    label, note = labels[action]
    lines = ["## Jev / Review receipt", "", "```text", " J E V   /   REVIEW", " " + "-" * 36, " DISPOSITION   " + label, " " + "-" * 36, "```", "", "**Policy:** " + note]
    if review is not None:
        lines.append("**Model answer:** " + ("approve" if review.approve else "hold / review"))
    if provider_error is not None:
        lines.append("**Provider:** unavailable - " + _safe_text(provider_error))
    elif review is None:
        lines.append("**Provider:** no typed review evidence supplied")
    return "\n".join(lines)


def _mode_note(config: Any) -> str:
    mode = getattr(config, "mode", None)
    if mode == "shadow":
        return "**Mode:** shadow — automatic approvals disabled; comment is informational."
    if mode == "active":
        return "**Mode:** active — any approval still requires every policy gate."
    return "**Mode:** unknown — write capability not established."


def _links(pr: Any, server: Optional[str]) -> list[str]:
    if pr is None:
        return []
    repo = _string_attr(pr, "repository")
    head = _string_attr(pr, "head_sha")
    links = []
    if _REPOSITORY.fullmatch(repo) and _SHA.fullmatch(head):
        commit_server = server or "https://github.com"
        links.append("[Exact head commit `" + head.lower() + "`](" + commit_server + "/" + repo + "/commit/" + head.lower() + ")")
    run = _actions_run_url(repo, server)
    if run is not None:
        links.append("[Open Actions run](" + run + ")")
    return links


def _safe_server_url(raw: str) -> Optional[str]:
    if not isinstance(raw, str) or len(raw) > 200:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.hostname != "github.com" or parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
        return None
    return "https://github.com"


def _actions_run_url(repository: str, server: Optional[str]) -> Optional[str]:
    env_repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "")
    if server is None or not _REPOSITORY.fullmatch(env_repo) or not _POSITIVE_INTEGER.fullmatch(run_id):
        return None
    result = server + "/" + env_repo + "/actions/runs/" + run_id
    if attempt:
        if not _POSITIVE_INTEGER.fullmatch(attempt):
            return None
        result += "/attempt/" + attempt
    return result


def _decision_table(review: Optional[Review], calibrated: bool) -> str:
    suffix = "calibrated" if calibrated else "uncalibrated"
    if review is None:
        return "### Decision evidence\n\n_No typed decision available._"
    rows = [
        ("Approval", "approve" if review.approve else "hold / review", review.approve_confidence),
        ("Risk", _risk_label(review.risk), review.risk_confidence),
    ]
    lines = ["### Decision evidence", "", "| Signal | Typed result | Model confidence (" + suffix + ") |", "| --- | --- | --- |"]
    lines.extend("| " + _safe_text(name) + " | " + _safe_text(result) + " | " + _confidence(value) + " |" for name, result, value in rows)
    return "\n".join(lines)


def _checklist_table(review: Optional[Review], calibrated: bool) -> str:
    if review is None:
        return ""
    suffix = "calibrated" if calibrated else "uncalibrated"
    lines = ["### Model assessment", "", "| Check | Status | Blocking | Model confidence (" + suffix + ") |", "| --- | --- | --- | --- |"]
    for item in review.required_checklist_items[:MAX_CONCERNS]:
        status = item.status.value
        lines.append("| " + _safe_text(item.name) + " | " + _safe_text(status) + " | " + ("yes" if item.blocking else "no") + " | " + _confidence(item.confidence) + " |")
    lines.extend(("", "These are Jev assessments of the diff, not executed tests. The tests score describes test adequacy."))
    return "\n".join(lines)


def _ci_table(pr: Any, evidence: Sequence[Mapping[str, Any]] = ()) -> str:
    if pr is None:
        return ""
    required = _string_tuple(getattr(pr, "required_checks", ()))
    passed = set(_string_tuple(getattr(pr, "passed_checks", ())))
    if not required:
        return "### Executed checks\n\n_Unknown - no configured trusted checks supplied._"
    by_name = {row.get("name"): row for row in evidence if isinstance(row, Mapping)}
    lines = ["### Executed checks", "", "GitHub-reported results for the reviewed head. A passing job does not establish coverage.", "", "| Check | Verified result | Execution evidence |", "| --- | --- | --- |"]
    for name in required[:MAX_CONCERNS]:
        row = by_name.get(name, {})
        url = row.get("details_url", "")
        repo = _string_attr(pr, "repository")
        valid_url = isinstance(url, str) and re.fullmatch(r"https://github\.com/" + re.escape(repo) + r"/actions/runs/[0-9]+/job/[0-9]+", url)
        link = "[Job logs](" + url + ")" if valid_url else "Link unavailable"
        lines.append("| " + _safe_text(name) + " | " + ("PASS" if name in passed else "NOT VERIFIED") + " | " + link + " |")
    # Keep provider-reported prose separate from trusted pass/fail status.
    for name in required[:MAX_CONCERNS]:
        row = by_name.get(name, {})
        completed = row.get("completed_at")
        if isinstance(completed, str):
            lines.extend(("", "**" + _safe_text(name) + ":** completed " + _safe_text(completed) + "; App ID " + _safe_text(str(row.get("app_id", "unknown"))) + "."))
        summary = row.get("summary")
        if isinstance(summary, str) and summary.strip():
            lines.extend(("", "**Reported by " + _safe_text(name) + ":** " + _safe_text(summary)))
    lines.extend(("", "Individual test names, counts and coverage are not supplied by check status. Open job logs for executed commands and assertions. Jev does not run the PR code."))
    return "\n".join(lines)


def _scope(pr: Any) -> str:
    if pr is None:
        return ""
    files = getattr(pr, "files", ())
    additions = sum(item.additions for item in files)
    deletions = sum(item.deletions for item in files)
    lines = ["<details>", "<summary>Review scope / " + str(len(files)) + " files / +" + str(additions) + " -" + str(deletions) + "</summary>", "", "| File | Added | Removed |", "| --- | ---: | ---: |"]
    lines.extend("| " + _safe_text(item.path) + " | " + str(item.additions) + " | " + str(item.deletions) + " |" for item in files[:MAX_FILES])
    lines.extend(("", "Input: PR metadata and file patches. No full-repository execution, coverage measurement or runtime security scan is performed by Jev.", "", "</details>"))
    return "\n".join(lines)


def _reasons_and_route(decision: Any, review: Optional[Review], route: Sequence[str], provider_error: Optional[str]) -> str:
    reasons = getattr(decision, "reasons", ())
    if not isinstance(reasons, (tuple, list)):
        reasons = ()
    lines = ["### Why", ""]
    if provider_error:
        lines.append("- Jev provider unavailable; no model-derived finding was fabricated.")
    elif reasons:
        lines.extend("- " + _safe_text(reason) for reason in reasons[:MAX_CONCERNS] if isinstance(reason, str))
    elif review is not None and review.concerns:
        lines.extend("- " + _safe_text(concern.message) + " (`" + _safe_path(concern.path) + ":" + str(concern.line) + "`)" for concern in review.concerns[:MAX_CONCERNS])
    else:
        lines.append("- No blocking reason emitted by policy.")
    if review is not None and review.concerns:
        lines.append("")
        lines.append("**Concrete concerns**")
        lines.extend("- " + _safe_text(concern.severity.value) + ": " + _safe_text(concern.message) + " — `" + _safe_path(concern.path) + ":" + str(concern.line) + "`" for concern in review.concerns[:MAX_CONCERNS])
    if route:
        lines.extend(("", "**Suggested owner route:** " + ", ".join(_safe_text(owner) for owner in route[:MAX_CONCERNS])))
    return "\n".join(lines)


def _suggestions(review: Optional[Review]) -> str:
    if review is None or not review.suggestions:
        return ""
    lines = ["### Advisory suggestions", "", "_Output-only suggestions; Jev does not edit files._"]
    lines.extend("- " + _safe_text(value) for value in review.suggestions[:MAX_SUGGESTIONS])
    return "\n".join(lines)


def _provider_summary(provider_result: Any, provider_error: Optional[str]) -> str:
    if provider_error is not None:
        return "### Provider evidence\n\n**Unavailable:** " + _safe_text(provider_error)
    if provider_result is None:
        return "### Provider evidence\n\n_No provider response supplied._"
    model = getattr(provider_result, "model", None)
    usage = getattr(provider_result, "usage", None)
    request_id = getattr(provider_result, "request_id", None)
    if not isinstance(model, str) or not model.strip():
        model = "unknown"
    usage_text = _usage(usage)
    request_text = _safe_text(request_id) if isinstance(request_id, str) and request_id else "not supplied"
    return "### Provider evidence\n\n**Model:** " + _safe_text(model) + "  \n**Usage:** " + usage_text + "  \n**Request ID:** " + request_text


def _raw_evidence(pr: Any, review: Optional[Review], decision: Any, config: Any, provider_result: Any, route: Sequence[str], calibration_ref: Any, provider_error: Optional[str]) -> str:
    evidence: dict[str, Any] = {
        "change": _raw_pr(pr),
        "review": _raw_review(review),
        "policy": _raw_decision(decision, config),
        "route": list(route[:MAX_CONCERNS]) if isinstance(route, (tuple, list)) else [],
        "calibration_reference": calibration_ref if isinstance(calibration_ref, str) else "not-verified",
    }
    if provider_error is not None:
        evidence["provider"] = {"status": "unavailable", "error": provider_error}
    elif provider_result is not None:
        evidence["provider"] = _raw_provider(provider_result)
    else:
        evidence["provider"] = {"status": "not-supplied"}
    encoded = _json_for_markdown(evidence, MAX_RAW_CHARS)
    return "<details>\n<summary>Raw structured evidence</summary>\n\n```json\n" + encoded + "\n```\n\n</details>"


def _raw_pr(pr: Any) -> Any:
    if pr is None:
        return {"status": "not-supplied"}
    files = []
    for item in getattr(pr, "files", ())[:MAX_FILES]:
        files.append({"path": getattr(item, "path", ""), "previous_path": getattr(item, "previous_path", None), "additions": getattr(item, "additions", None), "deletions": getattr(item, "deletions", None)})
    return {"repository": _string_attr(pr, "repository"), "number": getattr(pr, "number", None), "base_sha": _string_attr(pr, "base_sha"), "head_sha": _string_attr(pr, "head_sha"), "observed_head_sha": _string_attr(pr, "observed_head_sha"), "files": files, "required_checks": list(_string_tuple(getattr(pr, "required_checks", ()))), "passed_checks": list(_string_tuple(getattr(pr, "passed_checks", ())))}


def _raw_review(review: Optional[Review]) -> Any:
    if review is None:
        return {"status": "not-supplied"}
    return {"approve": review.approve, "risk": review.risk.value, "approve_confidence": review.approve_confidence, "risk_confidence": review.risk_confidence, "checklist": [{"name": i.name, "status": i.status.value, "confidence": i.confidence, "blocking": i.blocking} for i in review.required_checklist_items], "concerns": [{"message": c.message, "path": c.path, "line": c.line, "severity": c.severity.value} for c in review.concerns], "suggestions": list(review.suggestions), "native_confidences": dict(review.native_confidences)}


def _raw_decision(decision: Any, config: Any) -> Any:
    action = _action(decision)
    reasons = getattr(decision, "reasons", ())
    return {"action": action, "approve": getattr(decision, "approve", None), "reasons": list(reasons[:MAX_CONCERNS]) if isinstance(reasons, (tuple, list)) else [], "policy_id": _string_attr(config, "policy_id"), "mode": _string_attr(config, "mode"), "min_confidence": getattr(config, "min_confidence", None)}


def _raw_provider(provider: Any) -> Any:
    answers = getattr(provider, "answers", {})
    usage = getattr(provider, "usage", {})
    return {"status": "received", "model": getattr(provider, "model", None), "request_id": getattr(provider, "request_id", None), "answers": answers, "usage": usage}


def _provider_error(value: Any) -> Optional[str]:
    if isinstance(value, BaseException):
        message = str(value)
        return message[:MAX_VALUE_CHARS] if message else value.__class__.__name__
    return None


def _calibration_status(reference: Any, decision: Any) -> tuple[bool, str]:
    supplied = isinstance(reference, str) and reference not in _UNVERIFIED_CALIBRATION and bool(reference.strip())
    verified = isinstance(decision, PolicyDecision) and _action(decision) in ("auto_approve", "shadow") and supplied
    if verified:
        return True, "Model confidence is **calibrated** against policy evidence: " + _safe_text(reference)
    if supplied:
        return False, "Model confidence is **uncalibrated**; reference supplied but policy evidence is not verified: " + _safe_text(reference)
    return False, "Model confidence is **uncalibrated**; calibration evidence is absent."


def _confidence(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or not 0 <= float(value) <= 1:
        return "unknown"
    probability = float(value)
    filled = int(round(probability * 10))
    return "`" + "[" + ("#" * filled) + ("." * (10 - filled)) + "]" + "` " + str(round(probability * 100)) + "%"


def _risk_label(value: Any) -> str:
    raw = getattr(value, "value", value)
    if not isinstance(raw, str):
        return "unknown"
    return {"low": "low", "medium": "medium", "high": "high", "critical": "critical"}.get(raw, "unknown")


def _usage(value: Any) -> str:
    if not isinstance(value, Mapping):
        return "unknown"
    input_tokens, output_tokens = value.get("input_tokens"), value.get("output_tokens")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in (input_tokens, output_tokens)):
        return "unknown"
    return str(input_tokens) + " in / " + str(output_tokens) + " out"


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _safe_path(value: Any) -> str:
    # Code spans cannot contain an unescaped backtick; entity encoding keeps
    # the path readable while preventing a span or Markdown link from closing.
    return _safe_text(value).replace("&#96;", "'")


def _safe_text(value: Any) -> str:
    if not isinstance(value, str):
        value = "unknown"
    value = value.replace("\r", " ").replace("\n", " ")[:MAX_VALUE_CHARS]
    entities = {"&": "&amp;", "<": "&lt;", ">": "&gt;", "`": "&#96;", "|": "&#124;", "@": "&#64;", "[": "&#91;", "]": "&#93;", "*": "&#42;", "_": "&#95;", "~": "&#126;", "#": "&#35;"}
    return "".join(entities.get(char, char) for char in value)


def _json_for_markdown(value: Any, budget: int) -> str:
    try:
        encoded = json.dumps(_json_value(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        encoded = json.dumps({"status": "evidence-serialization-failed"}, separators=(",", ":"))
    # Escape syntax even inside a fenced block. This protects future renderers
    # and makes @handles / HTML tags inert if a fence is ever moved.
    for source, escaped in (("`", "\\u0060"), ("<", "\\u003c"), (">", "\\u003e"), ("@", "\\u0040"), ("&", "\\u0026")):
        encoded = encoded.replace(source, escaped)
    if len(encoded) <= budget:
        return encoded
    return json.dumps({"status": "evidence-truncated", "original_chars": len(encoded)}, separators=(",", ":"))


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(cast(Any, value)))
    return "<unsupported>"


def _investigation(report: Mapping[str, Any]) -> str:
    """Display correlated views without turning their agreement into authority."""
    perspectives = report.get('perspectives', {})
    if not isinstance(perspectives, Mapping):
        return '**Investigation unavailable.**'
    labels = ('correctness', 'security', 'verification')
    diagram = ['```mermaid', 'flowchart LR', '  D["PR diff + metadata"]']
    rows = []
    for index, label in enumerate(labels):
        item = perspectives.get(label, {})
        answers = item.get('answers', {}) if isinstance(item, Mapping) else {}
        verdict = answers.get('verdict', {})
        choice = verdict.get('choice', 'unavailable')
        choice = choice if choice in ('approve', 'hold', 'review') else 'unavailable'
        diagram.append('  D --> V' + str(index) + '["' + label.title() + ': ' + choice.upper() + '"]')
        diagram.append('  V' + str(index) + ' --> P["Human review / compare evidence"]')
        probs = verdict.get('probabilities', {})
        distribution_text = ' / '.join(str(round(probs[k] * 100)) + '%' if isinstance(probs.get(k), (int, float)) else '?' for k in ('approve', 'hold', 'review'))
        rows.append('| ' + label.title() + ' | ' + choice + ' | ' + distribution_text + ' |')
    diagram.extend(['  classDef evidence fill:#eef3fc,stroke:#2854a1,color:#17231f', '  classDef policy fill:#f5ede7,stroke:#a54527,color:#17231f', '  class V0,V1,V2 evidence', '  class P policy', '```'])
    lines = ['Three prompts interrogate the same change. These are correlated views from one model, not independent reviewers.', '', *diagram, '', '| Perspective | Verdict | P(approve / hold / review) |', '| --- | --- | --- |', *rows]
    scope = report.get('scope', {})
    paths = scope.get('files_reviewed', ()) if isinstance(scope, Mapping) else ()
    if paths:
        lines.extend(('', '### File-level hypotheses', '', 'Model-selected categories, not proven defects. Percentages are selected-category probabilities.', '', '| Changed file | Correctness view | Security view | Verification view |', '| --- | --- | --- | --- |'))
        for path in paths[:8]:
            values = []
            for label in labels:
                item = perspectives.get(label, {})
                answer = item.get('files', {}).get(path, {}).get('failure', {})
                probability = answer.get('selected_probability')
                pct = ' / ' + str(round(probability * 100)) + '%' if isinstance(probability, (int, float)) else ''
                values.append(_safe_text(answer.get('choice', 'unavailable')) + pct)
            lines.append('| ' + _safe_text(path) + ' | ' + ' | '.join(values) + ' |')
    if report.get('scope_complete') is not True:
        lines.extend(('', '**Scope incomplete.** Bounded investigation cannot cover this PR; no complete-review claim.'))
    recommendations = report.get('recommended_checks', ())
    if recommendations:
        lines.extend(('', '<details>', '<summary>Proposed next checks / not executed</summary>', '', '```json', _json_for_markdown(recommendations, 2000), '```', '', '</details>'))
    lines.extend(('', '<details>', '<summary>Investigation provenance / model, request IDs, failures</summary>', '', '| Perspective | Model | Request | Status |', '| --- | --- | --- | --- |'))
    for label in labels:
        item = perspectives.get(label, {})
        lines.append('| ' + label + ' | ' + _safe_text(item.get('model')) + ' | ' + _safe_text(item.get('request_id')) + ' | ' + _safe_text(item.get('status')) + ' |')
    lines.extend(('', 'Full question/response evidence is in the linked Actions run. Agreement does not establish calibration.', '', '</details>'))
    return '\n'.join(lines)
