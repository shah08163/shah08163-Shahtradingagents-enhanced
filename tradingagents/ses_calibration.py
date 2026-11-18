"""Point-in-time evaluation harness for Shah Evidence Score (SES) v1.0.

Input returns must be produced by a separate price-history pipeline using the
NEXT EXECUTABLE bar after signal publication, with costs and survivorship
controls applied upstream. This module does not fetch or fabricate history.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from statistics import mean

from tradingagents.ses import classify


@dataclass(frozen=True)
class Outcome:
    ticker: str
    signal_date: str
    latest_input_date: str
    horizon_end: str
    score: float
    next_bar_forward_return: float


@dataclass(frozen=True)
class BucketResult:
    bucket: str
    observations: int
    directional_hit_rate: float | None
    mean_forward_return: float | None
    ready_for_calibration: bool


def evaluate_outcomes(
    outcomes: list[Outcome],
    *,
    minimum_observations: int = 30,
) -> tuple[BucketResult, ...]:
    """Evaluate signed predictions without generating forward-return data.

    Repeated overlapping outcomes should be de-clustered or subjected to
    block bootstrap by the upstream backtester before inference.
    """
    if minimum_observations < 1:
        raise ValueError("minimum_observations must be positive")
    bins: dict[str, list[Outcome]] = {
        k: [] for k in (
            "STRONG_BEARISH", "BEARISH", "NEUTRAL", "BULLISH", "STRONG_BULLISH"
        )
    }
    for row in outcomes:
        signal, available, end = (
            date.fromisoformat(row.signal_date),
            date.fromisoformat(row.latest_input_date),
            date.fromisoformat(row.horizon_end),
        )
        if available > signal:
            raise ValueError("Lookahead: source input postdates signal")
        if end <= signal:
            raise ValueError("Outcome horizon must follow signal")
        if not isfinite(row.score) or not -1 <= row.score <= 1:
            raise ValueError("Invalid SES score")
        if not isfinite(row.next_bar_forward_return):
            raise ValueError("Invalid forward return")
        bins[classify(row.score)].append(row)
    answer = []
    for bucket, rows in bins.items():
        if not rows:
            answer.append(BucketResult(bucket, 0, None, None, False))
            continue
        if bucket == "NEUTRAL":
            accuracy = None
        else:
            direction = 1 if "BULLISH" in bucket else -1
            accuracy = mean(
                float(direction * x.next_bar_forward_return > 0) for x in rows
            )
        answer.append(BucketResult(
            bucket, len(rows), accuracy,
            mean(x.next_bar_forward_return for x in rows),
            len(rows) >= minimum_observations,
        ))
    return tuple(answer)
