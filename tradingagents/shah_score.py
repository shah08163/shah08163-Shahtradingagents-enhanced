"""Source-pinned Shah evidence score with provenance-aware overlap control.

The legacy seven-role Evidence Weigher is pinned to
tradingagents/agents/analysts/evidence_weigher.py at commit
393a4539cecc5b19c20f5f80829612cd8abef28a (blob
9c98c415e1e1c17103a7f9f18cd8c5d83ec6f909). This module implements its
confidence × data-quality × freshness weighted average and its shared
Flow/OI cap. The native extension applies that cap only to explicitly shared
event IDs or dependence groups, so independent Schwab chain components remain
eligible at full weight.

This is an evidence audit score, not the Portfolio Manager's five-tier rating,
a probability, or an automatic trade signal.
"""
from __future__ import annotations

from collections import defaultdict
from math import isfinite

ANALYSTS = ("market", "social", "news", "fundamentals", "flow", "oi", "dealer")
SCORING_SPEC_SHA = "9c98c415e1e1c17103a7f9f18cd8c5d83ec6f909"
SCORING_SPEC_REF = (
    "shah08163/shah08163-Shahtradingagents-enhanced@"
    "393a4539cecc5b19c20f5f80829612cd8abef28a:"
    "tradingagents/agents/analysts/evidence_weigher.py"
)
FORMULA = (
    "sum(direction * effective_weight) / sum(effective_weight); "
    "base_weight=confidence*quality*freshness; explicitly shared "
    "provenance components are proportionally capped at their strongest "
    "single component"
)


def _number(value, name, lower, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not isfinite(value) or not lower <= value <= upper:
        raise ValueError(f"{name} outside [{lower}, {upper}]")
    return value


def _components(analyst, provenance, base_weight):
    if not isinstance(provenance, list) or not provenance:
        raise ValueError(f"{analyst}: source provenance required")
    raw = []
    total_share = 0.0
    for index, part in enumerate(provenance):
        if not isinstance(part, dict):
            raise ValueError(f"{analyst}: malformed provenance")
        share = _number(part.get("weight_share", 1.0), "weight_share", 0.0, 1.0)
        if share <= 0:
            raise ValueError(f"{analyst}: weight_share must be positive")
        ids = part.get("evidence_ids", [])
        if not isinstance(ids, list) or any(not isinstance(x, str) or not x.strip() for x in ids):
            raise ValueError(f"{analyst}: malformed evidence_ids")
        group = part.get("dependence_group")
        if group is not None and (not isinstance(group, str) or not group.strip()):
            raise ValueError(f"{analyst}: malformed dependence_group")
        source_id = part.get("source_id")
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError(f"{analyst}: source_id required")

        # A dependence group is the clearest shared-measurement declaration.
        # Otherwise split a mixed component evenly across its explicit event IDs.
        if group:
            keys = ["group:" + group]
        elif ids:
            keys = ["event:" + event_id for event_id in dict.fromkeys(ids)]
        else:
            keys = [f"independent:{analyst}:{source_id}:{index}"]
        component_share = share / len(keys)
        for key in keys:
            raw.append((key, component_share))
        total_share += share

    if total_share <= 0:
        raise ValueError(f"{analyst}: source shares must sum above zero")
    return [(key, base_weight * (share / total_share)) for key, share in raw]


def _label(score):
    if score >= 0.55:
        return "Strong Bullish"
    if score >= 0.20:
        return "Bullish"
    if score <= -0.55:
        return "Strong Bearish"
    if score <= -0.20:
        return "Bearish"
    return "Mixed / Neutral"


def score_official_shah(evidence, role_statuses=None):
    """Score accepted structured inputs; absent roles remain visible at zero weight.

    Partial coverage is scoreable. The returned status distinguishes a provisional
    score from a seven-role fully verified score. Missing roles are never bearish.
    """
    if not isinstance(evidence, dict) or not set(evidence).issubset(set(ANALYSTS)):
        raise ValueError("structured score inputs must use canonical analyst keys")
    role_statuses = role_statuses or {}
    if not isinstance(role_statuses, dict):
        raise ValueError("role_statuses must be an object")

    directions = {}
    bases = {}
    by_key = defaultdict(list)
    for analyst in ANALYSTS:
        if analyst not in evidence:
            continue
        item = evidence[analyst]
        if not isinstance(item, dict):
            raise ValueError(f"{analyst}: structured score input required")
        directions[analyst] = _number(item.get("score"), "direction", -1.0, 1.0)
        confidence = _number(item.get("confidence"), "confidence", 0.0, 1.0)
        quality = _number(item.get("quality"), "quality", 0.0, 1.0)
        freshness = _number(item.get("freshness"), "freshness", 0.0, 1.0)
        bases[analyst] = confidence * quality * freshness
        for key, amount in _components(analyst, item.get("source_provenance"), bases[analyst]):
            by_key[key].append((analyst, amount))

    effective = {analyst: 0.0 for analyst in ANALYSTS}
    for components in by_key.values():
        total = sum(amount for _, amount in components)
        strongest = max((amount for _, amount in components), default=0.0)
        factor = strongest / total if total > 0 else 0.0
        for analyst, amount in components:
            effective[analyst] += amount * factor

    denominator = sum(effective.values())
    value = (
        sum(directions[name] * effective[name] for name in directions) / denominator
        if denominator > 0 else None
    )
    rows = []
    for analyst in ANALYSTS:
        status = role_statuses.get(analyst, "VERIFIED" if analyst in evidence else "UNAVAILABLE")
        if status not in ("VERIFIED", "PARTIAL", "UNAVAILABLE"):
            status = "UNAVAILABLE"
        if analyst not in evidence:
            rows.append({
                "analyst": analyst, "status": status, "direction": None,
                "confidence": None, "data_quality": None, "freshness": None,
                "base_weight": 0.0, "effective_weight": 0.0,
                "weighted_contribution": 0.0, "overlap_adjustment": 1.0,
                "source_provenance": [],
                "exclusion_reason": "No accepted structured score input; excluded, not bearish evidence.",
            })
            continue
        item = evidence[analyst]
        weight = effective[analyst]
        rows.append({
            "analyst": analyst, "status": status,
            "direction": directions[analyst],
            "confidence": float(item["confidence"]),
            "data_quality": float(item["quality"]),
            "freshness": float(item["freshness"]),
            "base_weight": bases[analyst],
            "effective_weight": weight,
            "weighted_contribution": directions[analyst] * weight,
            "overlap_adjustment": weight / bases[analyst] if bases[analyst] else 1.0,
            "source_provenance": item["source_provenance"],
        })
    scored_count = len(directions)
    all_verified = scored_count == len(ANALYSTS) and all(
        role_statuses.get(name, "VERIFIED") == "VERIFIED" for name in ANALYSTS
    )
    return {
        "version": "shah-evidence-weigher-provenance-v1",
        "spec_sha": SCORING_SPEC_SHA,
        "spec_ref": SCORING_SPEC_REF,
        "formula": FORMULA,
        "value": value,
        "classification": _label(value) if value is not None else "UNAVAILABLE",
        "score_status": "READY" if all_verified and value is not None else (
            "PROVISIONAL" if value is not None else "UNAVAILABLE"
        ),
        "coverage": {
            "scored_roles": scored_count,
            "total_roles": len(ANALYSTS),
            "fraction": scored_count / len(ANALYSTS),
            "statuses": {name: role_statuses.get(name, "VERIFIED" if name in evidence else "UNAVAILABLE")
                         for name in ANALYSTS},
        },
        "effective_weight_total": denominator,
        "contributions": rows,
        "is_official_shah_score": True,
        "is_trade_signal": False,
    }
