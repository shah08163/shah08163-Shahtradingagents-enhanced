"""Fail-closed validation for ChatGPT-native Shah TradingAgents research envelopes.

Standard-library only. Validates evidence completeness, not accuracy or trade suitability.
Usage: python scripts/validate_chatgpt_research.py path/to/report.json
Exit 0 only when all 7 analyst records are VERIFIED and scoring provenance is valid.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ANALYSTS = ("market", "social", "news", "fundamentals", "flow", "oi", "dealer")
STATUSES = {"VERIFIED", "PARTIAL", "UNAVAILABLE"}

def valid_timestamp(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False

def validate(report):
    errors = []
    if not isinstance(report, dict):
        return ["Report must be an object"]
    if not isinstance(report.get("ticker"), str) or not report["ticker"].strip():
        errors.append("ticker required")
    if not valid_timestamp(report.get("run_at")):
        errors.append("run_at must be ISO8601")
    if not isinstance(report.get("repository_sha"), str) or len(report["repository_sha"]) < 7:
        errors.append("repository_sha required")
    analysts = report.get("analysts")
    if not isinstance(analysts, dict):
        return errors + ["analysts must be an object"]
    if set(analysts) != set(ANALYSTS):
        errors.append("exactly seven canonical analyst keys required")
    all_verified = True
    for name in ANALYSTS:
        a = analysts.get(name)
        if not isinstance(a, dict):
            errors.append(f"{name}: record required")
            all_verified = False
            continue
        status = a.get("status")
        if status not in STATUSES:
            errors.append(f"{name}: invalid status")
        if status != "VERIFIED":
            all_verified = False
        if status == "VERIFIED":
            if not valid_timestamp(a.get("as_of")):
                errors.append(f"{name}: verified data requires as_of ISO8601")
            if not isinstance(a.get("sources"), list) or not a["sources"] or any(not isinstance(x,str) or not x.strip() for x in a["sources"]):
                errors.append(f"{name}: verified data requires sources")
            if not isinstance(a.get("evidence"), list) or not a["evidence"]:
                errors.append(f"{name}: verified data requires evidence")
        if not isinstance(a.get("limitations"), list):
            errors.append(f"{name}: limitations must be a list")
    if report.get("complete") is True and not all_verified:
        errors.append("complete cannot be true unless all seven analysts VERIFIED")
    score = report.get("shah_score")
    if score is not None:
        if not all_verified:
            errors.append("shah_score prohibited with incomplete analysts")
        if not isinstance(score,(int,float)) or isinstance(score,bool):
            errors.append("shah_score must be numeric or null")
        if not report.get("scoring_spec_sha"):
            errors.append("numeric shah_score requires scoring_spec_sha")
    if report.get("actionable") is True and not all_verified:
        errors.append("actionable cannot be true with incomplete analysts")
    return errors

def main():
    if len(sys.argv) != 2:
        print("Usage: validate_chatgpt_research.py REPORT.json", file=sys.stderr)
        return 2
    try:
        report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Cannot read report: {exc}", file=sys.stderr)
        return 2
    errors = validate(report)
    for error in errors:
        print("FAIL:", error)
    if errors:
        return 1
    print("PASS: envelope is structurally valid; data accuracy not certified")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
