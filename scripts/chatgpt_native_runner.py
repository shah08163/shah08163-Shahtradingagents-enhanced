"""Assemble read-only seven-analyst evidence supplied by ChatGPT connectors.

No external services are called here; the active ChatGPT conversation gathers evidence.
An analyst is never certified just because an input says 'VERIFIED'.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.chatgpt_analyst_rubric import assess_numeric_input
from scripts.validate_chatgpt_research import ANALYSTS, valid_timestamp, validate
from tradingagents.ses import AnalystEvidence, SourceProvenance, score_confidence_weighted_evidence
from tradingagents.shah_score import score_official_shah


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
        requested_status = supplied.get("status")
        reported_status = ("VERIFIED" if valid else
            requested_status if requested_status in ("PARTIAL", "UNAVAILABLE") else "PARTIAL")
        records[analyst] = {
            "status": reported_status,
            "as_of": as_of,
            "sources": sources if isinstance(sources, list) else [],
            "evidence": facts if isinstance(facts, list) else [],
            "limitations": limitations if isinstance(limitations, list) else ["Malformed limitations"]
        }
        for key in ("source_provenance", "observation_end", "observation_date",
                    "pagination_complete", "requested_window", "context_sources",
                    "features"):
            if key in supplied:
                records[analyst][key] = supplied[key]
        if analyst == "flow" and isinstance(evidence.get("supplemental"), dict):
            dark_pool = evidence["supplemental"].get("dark_pool_context")
            if dark_pool:
                records[analyst]["context_sources"] = {"dark_pool": dark_pool}

    score_inputs = []
    score_claims = {}
    score_rejections = {}
    for analyst in ANALYSTS:
        supplied = evidence.get(analyst)
        claim = supplied.get("score_input") if isinstance(supplied, dict) else None
        if claim is None:
            continue
        if (isinstance(claim, dict) and not claim.get("source_provenance")
                and isinstance(records[analyst].get("source_provenance"), list)):
            claim = {**claim, "source_provenance": records[analyst]["source_provenance"]}
        accepted, reasons = assess_numeric_input(analyst, claim, records[analyst])
        if reasons:
            score_rejections[analyst] = reasons
            continue
        score_claims[analyst] = accepted
        provenance = tuple(SourceProvenance(
            source_id=part["source_id"], provider=part["provider"],
            dataset=part["dataset"], as_of=part.get("as_of"),
            weight_share=part.get("weight_share", 1.0),
            evidence_ids=tuple(part.get("evidence_ids", ())),
            dependence_group=part.get("dependence_group"),
        ) for part in accepted.get("source_provenance", []))
        score_inputs.append(AnalystEvidence(
            analyst=analyst,
            score=accepted["score"],
            confidence=accepted["confidence"],
            quality=accepted["quality"],
            freshness=accepted["freshness"],
            source_ids=tuple(accepted.get("source_ids") or ()),
            as_of=accepted.get("as_of"),
            direction_basis=accepted.get("direction_basis", "unspecified"),
            source_provenance=provenance,
        ))

    weighted_evidence_score = (
        score_confidence_weighted_evidence(score_inputs)
        if score_inputs else None
    )
    complete = all(r["status"] == "VERIFIED" for r in records.values())
    official_score = None
    shah_score_details = None
    scoring_spec_sha = None
    for analyst in ANALYSTS:
        if analyst not in score_claims:
            score_rejections.setdefault(analyst, ["no valid structured score_input"])
    try:
        shah_score_details = score_official_shah(
            score_claims,
            {name: records[name]["status"] for name in ANALYSTS},
        )
        official_score = shah_score_details["value"]
        scoring_spec_sha = shah_score_details["spec_sha"]
    except (TypeError, ValueError) as exc:
        score_rejections["official_shah_score"] = [str(exc)]
    report = {"ticker": ticker.upper().strip(),
        "run_at": run_at or datetime.now(UTC).isoformat(),
        "repository_sha": repository_sha, "analysts": records,
        "complete": complete, "actionable": False, "shah_score": official_score,
        "shah_score_details": shah_score_details,
        "shah_score_status": shah_score_details["score_status"] if shah_score_details else "UNAVAILABLE",
        "weighted_evidence_score": weighted_evidence_score,
        "score_input_rejections": score_rejections,
        "scoring_spec_sha": scoring_spec_sha, "posture": "NO TRADE",
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
