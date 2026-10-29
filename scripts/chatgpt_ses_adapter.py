"""Attach SES to a ChatGPT-native report ONLY with structured verified scores.

No provider calls or order execution. A missing analyst/metric produces null.
"""

from dataclasses import asdict
from math import isfinite

from scripts.chatgpt_analyst_rubric import assess_numeric_input
from scripts.validate_chatgpt_research import ANALYSTS, validate
from tradingagents.ses import AnalystEvidence, TradeGate, decide_trade, score_evidence

SCORER_BLOB_SHA = "db393dd773f57eaeca3b4f3908b053b0ae3d4aa1"

def attach_score(report, numeric_evidence, gates=None):
    result = dict(report)
    result["shah_score"] = None
    result["scoring_spec_sha"] = None
    result["actionable"] = False
    result["posture"] = "NO TRADE"
    result["ses_status"] = "INSUFFICIENT"
    result["ses_trade_decision"] = "NO_TRADE"
    if not report.get("complete") or validate(report) or not isinstance(numeric_evidence, dict):
        return result
    rows = []
    for name in ANALYSTS:
        item = numeric_evidence.get(name)
        cited = report.get("analysts", {}).get(name, {})
        accepted, reasons = assess_numeric_input(name, item, cited)
        if accepted is None:
            return result
        direction = item.get("score")
        if isinstance(direction, bool) or not isinstance(direction, (int, float)) or not isfinite(direction) or not -1 <= direction <= 1:
            return result
        if not item.get("source_ids") or not cited.get("as_of"):
            return result
        if name == "flow" and direction != 0 and item.get("direction_basis") != "single_leg_sweep_block":
            return result
        if name == "oi" and direction != 0 and item.get("direction_basis") != "confirmed_change_plus_flow":
            return result
        try:
            rows.append(AnalystEvidence(
                analyst=name, score=float(direction),
                confidence=item["confidence"], quality=item["quality"],
                freshness=item["freshness"], overlap_multiplier=item.get("overlap_multiplier", 1.0),
                source_ids=tuple(item["source_ids"]), as_of=cited["as_of"],
                direction_basis=item.get("direction_basis", "unspecified")))
        except (KeyError, ValueError, TypeError):
            return result
    ses = score_evidence(rows)
    decision = decide_trade(ses, gates if isinstance(gates, TradeGate) else TradeGate(), options=True)
    result["shah_score"] = ses.value
    result["scoring_spec_sha"] = SCORER_BLOB_SHA
    result["ses_status"] = ses.status
    result["ses_components"] = [asdict(x) for x in ses.contributions]
    result["ses_trade_decision"] = decision.status
    result["posture"] = decision.status
    result["actionable"] = False  # CANDIDATE_FOR_REVIEW is not an order authorization.
    return result
