"""Run explicitly synthetic Jev cases; never produces production calibration.

Usage: TYPESAFE_API_KEY=... python scripts/live_smoke.py --run-live
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
PROVIDER_SOURCE_HASH = hashlib.sha256((ROOT / "jev_review/provider.py").read_bytes()).hexdigest()

from jev_review.models import parse_pr
from jev_review.policy import evaluate
from jev_review.provider import JevProvider, PROMPT_VERSION, SCHEMA_VERSION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-live", action="store_true", required=True)
    parser.add_argument("--output", default=str(ROOT / "docs/evidence/live-synthetic-evaluation.json"))
    args = parser.parse_args()
    source = ROOT / "docs/evidence/synthetic-cases.json"
    cases = json.loads(source.read_text())
    provider = JevProvider(retries=0, timeout=20)
    results = []
    for case in cases:
        started = time.monotonic()
        row = {"id": case["id"], "expected_safe": case["expected_safe"], "synthetic": True}
        try:
            pr = parse_pr(case["pr"])
            review, raw = provider.review_with_result(pr)
            decision = evaluate(pr, review)
            row.update({
                "review": asdict(review), "provider": asdict(raw),
                "policy": asdict(decision),
                "approval_label_match": review.approve == case["expected_safe"],
                "unsafe_model_approval": review.approve and not case["expected_safe"],
            })
            print(case["id"], "approve=" + str(review.approve), "risk=" + review.risk.value, "policy=" + decision.action.value, flush=True)
        except Exception as exc:
            row["error_type"] = type(exc).__name__
            row["error"] = str(exc)
            row["http_status"] = getattr(exc, "status", None)
            print(case["id"], type(exc).__name__, flush=True)
        row["elapsed_seconds"] = round(time.monotonic() - started, 3)
        results.append(row)
    completed = [row for row in results if "review" in row]
    report = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "synthetic": True, "production_calibration": False,
        "prompt_version": PROMPT_VERSION, "schema_version": SCHEMA_VERSION,
        "provider_source_sha256": PROVIDER_SOURCE_HASH,
        "provider_source_changed_during_run": PROVIDER_SOURCE_HASH != hashlib.sha256((ROOT / "jev_review/provider.py").read_bytes()).hexdigest(),
        "cases_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "summary": {"attempted": len(results), "completed": len(completed),
                    "approval_label_matches": sum(row["approval_label_match"] for row in completed),
                    "unsafe_model_approvals": sum(row["unsafe_model_approval"] for row in completed),
                    "external_writes": 0},
        "limitations": ["Hand-authored isolated snippets; not representative PRs.",
                        "No GitHub mutations or production calibration evidence.",
                        "Policy intentionally lacks deployment/calibration config and must abstain."],
        "results": results,
    }
    Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"]))
    if len(completed) != len(results) or report["provider_source_changed_during_run"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
