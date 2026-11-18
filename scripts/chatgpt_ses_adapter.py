"""Attach SES to a ChatGPT-native report ONLY with structured verified scores.

No provider calls or order execution. A missing analyst/metric produces null.
"""

from dataclasses import asdict
from math import isfinite

from scripts.chatgpt_analyst_rubric import assess_numeric_input
from scripts.validate_chatgpt_research import ANALYSTS, validate
from tradingagents.ses import AnalystEvidence, SourceProvenance, TradeGate, decide_trade, score_evidence
from tradingagents.shah_score import score_official_shah

SES_SCORER_BLOB_SHA = "db393dd773f57eaeca3b4f3908b053b0ae3d4aa1"
SCORER_BLOB_SHA = "9c98c415e1e1c17103a7f9f18cd8c5d83ec6f909"  # legacy import alias

def attach_score(report, numeric_evidence, gates=None):
    result = dict(report)
    result["shah_score"] = None
    result["shah_score_details"] = None
    result["scoring_spec_sha"] = None
    result["ses_score"] = None
    result["shah_score_status"] = "UNAVAILABLE"
    result["actionable"] = False
    result["posture"] = "NO TRADE"
    result["ses_status"] = "INSUFFICIENT"
    result["ses_trade_decision"] = "NO_TRADE"
    if validate(report) or not isinstance(numeric_evidence, dict):
        return result
    rows = []
    accepted_claims = {}
    score_rejections = {}
    role_statuses = {name: report.get("analysts", {}).get(name, {}).get("status", "UNAVAILABLE")
                     for name in ANALYSTS}
    for name in ANALYSTS:
        item = numeric_evidence.get(name)
        cited = report.get("analysts", {}).get(name, {})
        if item is None:
            score_rejections[name] = ["no structured score_input"]
            continue
        accepted, reasons = assess_numeric_input(name, item, cited)
        if accepted is None:
            score_rejections[name] = reasons
            continue
        item = accepted
        direction = item.get("score")
        if isinstance(direction, bool) or not isinstance(direction, (int, float)) or not isfinite(direction) or not -1 <= direction <= 1:
            score_rejections[name] = ["direction outside [-1,1]"]
            continue
        if not item.get("source_ids") or not cited.get("as_of"):
            score_rejections[name] = ["source IDs or report timestamp missing"]
            continue
        if name == "flow" and direction != 0 and item.get("direction_basis") != "single_leg_sweep_block":
            score_rejections[name] = ["unqualified directional evidence"]
            continue
        if name == "oi" and direction != 0 and item.get("direction_basis") != "confirmed_change_plus_flow":
            score_rejections[name] = ["unqualified directional evidence"]
            continue
        try:
            provenance = tuple(SourceProvenance(
                source_id=part["source_id"], provider=part["provider"],
                dataset=part["dataset"], as_of=part.get("as_of"),
                weight_share=part.get("weight_share", 1.0),
                evidence_ids=tuple(part.get("evidence_ids", ())),
                dependence_group=part.get("dependence_group"),
            ) for part in accepted["source_provenance"])
            rows.append(AnalystEvidence(
                analyst=name, score=float(direction),
                confidence=item["confidence"], quality=item["quality"],
                freshness=item["freshness"], overlap_multiplier=item.get("overlap_multiplier", 1.0),
                source_ids=tuple(item["source_ids"]), as_of=cited["as_of"],
                direction_basis=item.get("direction_basis", "unspecified"),
                source_provenance=provenance))
            accepted_claims[name] = item
        except (KeyError, ValueError, TypeError) as exc:
            score_rejections[name] = [str(exc)]
            continue
    result["score_input_rejections"] = score_rejections
    official_score = score_official_shah(accepted_claims, role_statuses)
    result["shah_score"] = official_score["value"]
    result["shah_score_details"] = official_score
    result["scoring_spec_sha"] = official_score["spec_sha"]
    result["shah_score_status"] = official_score["score_status"]
    if len(rows) == len(ANALYSTS) and all(role_statuses[n] == "VERIFIED" for n in ANALYSTS):
        ses = score_evidence(rows)
        decision = decide_trade(ses, gates if isinstance(gates, TradeGate) else TradeGate(), options=True)
        result["ses_score"] = ses.value
        result["ses_scorer_spec_sha"] = SES_SCORER_BLOB_SHA
        result["ses_status"] = ses.status
        result["ses_components"] = [asdict(x) for x in ses.contributions]
        result["ses_trade_decision"] = decision.status
        result["posture"] = decision.status
    result["actionable"] = False  # CANDIDATE_FOR_REVIEW is not an order authorization.
    return result
