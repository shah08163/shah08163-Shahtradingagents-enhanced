"""Explicit seven-analyst numeric evidence policy, no sentiment inference.

A numeric score is accepted only with a separately documented structured rubric,
source-specific supporting IDs, timestamps, and quality weights. This module does
not calculate direction from narratives or make broker/API requests.
"""
from datetime import datetime

ANALYSTS = ("market", "social", "news", "fundamentals", "flow", "oi", "dealer")
DIRECTION_BASIS = {
    "flow": "single_leg_sweep_block",
    "oi": "confirmed_change_plus_flow",
}


def _aware_time(value):
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def assess_numeric_input(analyst, claim, report_record):
    """Return (accepted numeric claim or None, rejection reasons).

    Even accepted claims require the separate SES readiness and trade gates.
    """
    reasons = []
    if analyst not in ANALYSTS:
        return None, ["unknown analyst"]
    if not isinstance(claim, dict) or not isinstance(report_record, dict):
        return None, ["missing structured assessment"]
    status = report_record.get("status")
    if status not in ("VERIFIED", "PARTIAL"):
        reasons.append("analyst unavailable or invalid status")
    if not _aware_time(report_record.get("as_of")):
        reasons.append("report timestamp missing or timezone-naive")
    direction = claim.get("score")
    if isinstance(direction, bool) or not isinstance(direction, (int, float)):
        reasons.append("numeric direction required")
    elif not -1 <= direction <= 1:
        reasons.append("direction outside [-1,1]")
    source_ids = claim.get("source_ids")
    if not isinstance(source_ids, list) or not all(
        isinstance(x, str) and x.strip() for x in source_ids
    ):
        source_ids = []
    provenance = claim.get("source_provenance")
    provenance_ok = isinstance(provenance, list) and bool(provenance) and all(
        isinstance(part, dict)
        and all(isinstance(part.get(k), str) and part[k].strip()
                for k in ("source_id", "provider", "dataset"))
        and _aware_time(part.get("as_of"))
        for part in provenance
    )
    if not provenance_ok:
        reasons.append("timestamped source provenance components required")
    else:
        for part in provenance:
            share = part.get("weight_share", 1.0)
            if (isinstance(share, bool) or not isinstance(share, (int, float))
                    or not 0 < share <= 1):
                reasons.append("source provenance weight_share must be in (0,1]")
    if analyst in ("flow", "oi") and direction not in (0, None) and not source_ids:
        reasons.append("directional derivative evidence IDs required")
    for key in ("confidence", "quality", "freshness"):
        value = claim.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
            reasons.append(key + " missing or outside [0,1]")
    if not isinstance(claim.get("rubric_id"), str) or not claim["rubric_id"].strip():
        reasons.append("versioned directional rubric required")
    if (analyst in DIRECTION_BASIS and direction not in (0, None)
            and claim.get("direction_basis") != DIRECTION_BASIS[analyst]):
        reasons.append("unqualified directional evidence")
    if reasons:
        return None, sorted(set(reasons))
    accepted = dict(claim)
    if status == "PARTIAL":
        accepted["quality"] = min(float(claim["quality"]), 0.5)
    return accepted, []
