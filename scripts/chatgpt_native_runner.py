"""Assemble read-only seven-analyst evidence supplied by ChatGPT connectors.

No external services are called here; the active ChatGPT conversation gathers evidence.
An analyst is never certified just because an input says 'VERIFIED'.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.validate_chatgpt_research import ANALYSTS, validate, valid_timestamp

def assemble(ticker, repository_sha, evidence, run_at=None):
    if not isinstance(evidence, dict):
        raise TypeError("evidence must be an object")
    records = {}
    for analyst in ANALYSTS:
        supplied = evidence.get(analyst)
        if not isinstance(supplied, dict):
            records[analyst] = {"status": "UNAVAILABLE", "as_of": None,
                "sources": [], "evidence": [], "limitations": ["No analyst evidence supplied"]}
            continue
        sources = supplied.get("sources")
        facts = supplied.get("evidence")
        as_of = supplied.get("as_of")
        limitations = supplied.get("limitations")
        valid = (supplied.get("status") == "VERIFIED" and valid_timestamp(as_of)
            and isinstance(sources, list) and bool(sources)
            and all(isinstance(x, str) and bool(x.strip()) for x in sources)
            and isinstance(facts, list) and bool(facts)
            and all(isinstance(x, str) and bool(x.strip()) for x in facts)
            and isinstance(limitations, list))
        records[analyst] = {
            "status": "VERIFIED" if valid else "PARTIAL",
            "as_of": as_of,
            "sources": sources if isinstance(sources, list) else [],
            "evidence": facts if isinstance(facts, list) else [],
            "limitations": limitations if isinstance(limitations, list) else ["Malformed limitations"]
        }
    complete = all(r["status"] == "VERIFIED" for r in records.values())
    report = {"ticker": ticker.upper().strip(),
        "run_at": run_at or datetime.now(UTC).isoformat(),
        "repository_sha": repository_sha, "analysts": records,
        "complete": complete, "actionable": False, "shah_score": None,
        "scoring_spec_sha": None, "posture": "NO TRADE",
        "certification": "STRUCTURAL_ONLY"}
    errors = validate(report)
    if errors:
        raise ValueError("; ".join(errors))
    return report

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", required=True)
    p.add_argument("--repository-sha", required=True)
    p.add_argument("--evidence-json", required=True, type=Path)
    p.add_argument("--out-json", required=True, type=Path)
    args = p.parse_args()
    evidence = json.loads(args.evidence_json.read_text(encoding="utf-8"))
    report = assemble(args.ticker, args.repository_sha, evidence)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("Assembled:", report["ticker"], "complete=", report["complete"],
          "Shah Score=", report["shah_score"])

if __name__ == "__main__":
    main()
