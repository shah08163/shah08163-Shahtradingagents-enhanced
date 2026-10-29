"""Explicit flow and OI direction qualification; no connector/network calls.

Only independent event IDs for single-leg sweeps/blocks can qualify flow.
OI requires dated prior/current observations plus qualifying directional flow.
No score is created from aggregate premium, MULTI prints, or static OI.
"""


def assess_flow(events):
    if not isinstance(events, list) or not events:
        return {"status": "UNAVAILABLE", "direction": None}
    qualified = [
        e for e in events if isinstance(e, dict)
        and e.get("structure") == "SINGLE"
        and e.get("execution") in ("SWEEP", "BLOCK")
        and e.get("side") in ("ASK", "BID")
        and isinstance(e.get("event_id"), str) and e["event_id"].strip()
        and isinstance(e.get("premium"), (float, int))
        and not isinstance(e.get("premium"), bool)
        and e["premium"] > 0
    ]
    if not qualified:
        return {"status": "PARTIAL", "direction": None,
                "reason": "No qualifying single-leg events"}
    # Cumulative premium is descriptive only; ASK/BID alone does not
    # determine whether an option trade opens or closes.
    return {"status": "PARTIAL", "direction": None,
            "event_ids": sorted({e["event_id"] for e in qualified}),
            "qualified_count": len(qualified),
            "reason": "Opening/closing position and trade intent unconfirmed"}


def assess_oi_change(previous, current, flow_assessment):
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return {"status": "UNAVAILABLE", "direction": None}
    if previous.get("date") == current.get("date"):
        return {"status": "UNAVAILABLE", "direction": None}
    if not previous.get("date") or not current.get("date"):
        return {"status": "UNAVAILABLE", "direction": None}
    if (previous.get("contract_id") != current.get("contract_id")
            or not previous.get("contract_id")):
        return {"status": "UNAVAILABLE", "direction": None}
    for item in (previous, current):
        if not isinstance(item.get("oi"), int) or item["oi"] < 0:
            return {"status": "UNAVAILABLE", "direction": None}
    change = current["oi"] - previous["oi"]
    return {"status": "PARTIAL", "direction": None, "oi_change": change,
            "qualified_flow_event_ids": flow_assessment.get("event_ids", [])
            if isinstance(flow_assessment, dict) else [],
            "reason": "OI changes do not establish long/short intent"}
