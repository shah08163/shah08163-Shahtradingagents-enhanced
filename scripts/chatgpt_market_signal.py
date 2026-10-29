"""Deterministic market trend assessment from dated completed daily bars.

This adapter requires >=20 chronological completed sessions, a dated source,
and a latest completed bar. No live quote is inferred and no trade authorized.
The thresholds are an experimental, uncalibrated v0.1 rubric.
"""
from datetime import date
from math import isfinite

RUBRIC = "market-trend-v0.1-experimental"


def assess_market_bars(bars, source_id):
    """Produce a PARTIAL analyst observation plus a candidate score, or null."""
    reject = {"status": "UNAVAILABLE", "score": None, "rubric_id": RUBRIC}
    if not isinstance(source_id, str) or not source_id.strip():
        return reject
    if not isinstance(bars, list) or len(bars) < 20:
        return reject
    normalized = []
    for bar in bars:
        if not isinstance(bar, dict):
            return reject
        try:
            day = date.fromisoformat(bar["date"])
            close = bar["close"]
        except (KeyError, TypeError, ValueError):
            return reject
        if (isinstance(close, bool) or not isinstance(close, (float, int))
                or not isfinite(close) or close <= 0
                or bar.get("completed") is not True):
            return reject
        normalized.append((day, float(close)))
    if len({day for day, _ in normalized}) != len(normalized):
        return reject
    if any(a[0] >= b[0] for a, b in zip(normalized, normalized[1:], strict=False)):
        return reject
    close = normalized[-1][1]
    sma20 = sum(value for _, value in normalized[-20:]) / 20
    change5 = close / normalized[-6][1] - 1
    # Symmetric, transparent bounded contributions.
    trend = max(-1.0, min(1.0, (close / sma20 - 1) / 0.05))
    momentum = max(-1.0, min(1.0, change5 / 0.05))
    score = round(0.6 * trend + 0.4 * momentum, 6)
    return {
        "status": "PARTIAL",
        "score": score,
        "rubric_id": RUBRIC,
        "as_of": normalized[-1][0].isoformat(),
        "source_ids": [source_id],
        "metrics": {"last_close": close, "sma20": sma20, "return_5_sessions": change5},
        "limitations": [
            "Experimental uncalibrated technical signal",
            "No quote freshness or execution gate verified",
            "Not a certified seven-analyst directional score",
        ],
    }
