"""Shah Evidence Score (SES) v1.0 — deterministic, read-only evidence aggregation.

This module does NOT replace the existing portfolio manager's rating and
never executes orders. Downstream seven-analyst services must explicitly
provide evidence scores and source metadata; reports are not scored by magic.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal, Sequence

VERSION = "SES-v1.0.0"
ANALYSTS = ("market", "social", "news", "fundamentals", "flow", "oi", "dealer")
# Priors are proposals for SES v1.0, not learned or historically optimized.
BASE_WEIGHTS = {
    "market": 0.22,
    "social": 0.06,
    "news": 0.10,
    "fundamentals": 0.24,
    "flow": 0.16,
    "oi": 0.10,
    "dealer": 0.12,
}
DERIVATIVE_ANALYSTS = frozenset({"flow", "oi", "dealer"})


@dataclass(frozen=True)
class AnalystEvidence:
    analyst: str
    score: float | None
    confidence: float = 1.0
    quality: float = 1.0
    freshness: float = 1.0
    overlap_multiplier: float = 1.0
    source_ids: tuple[str, ...] = ()
    as_of: str | None = None
    # Only verified single-leg SWEEP/BLOCK ask/bid executions carry flow
    # directional bias. OI direction requires confirmed OI changes together
    # with qualifying single-leg directional evidence.
    direction_basis: str = "unspecified"
    # Migration bridge for a completed historical report; never fit a new run
    # to an expected historical score by selecting overrides.
    historical_effective_weight: float | None = None


@dataclass(frozen=True)
class AnalystContribution:
    analyst: str
    score: float | None
    effective_weight: float
    contribution: float
    overlap_adjustment: float
    included: bool
    as_of: str | None
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceScore:
    version: str
    value: float | None
    classification: str
    available_coverage: float
    effective_support: float
    status: Literal["READY", "PROVISIONAL", "INSUFFICIENT"]
    missing: tuple[str, ...]
    flags: tuple[str, ...]
    contributions: tuple[AnalystContribution, ...]


@dataclass(frozen=True)
class TradeGate:
    # All gates must be explicitly True to consider an executable setup.
    quote_fresh: bool | None = None
    technical_confirmed: bool | None = None
    liquidity_ok: bool | None = None
    risk_reward_ok: bool | None = None
    event_risk_ok: bool | None = None
    derivatives_fresh: bool | None = None


@dataclass(frozen=True)
class TradeDecision:
    status: Literal["NO_TRADE", "WATCH", "CANDIDATE_FOR_REVIEW"]
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN"]
    reasons: tuple[str, ...]


def _unit_interval(name: str, value: float) -> None:
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be a finite number in [0, 1]")


def classify(value: float | None) -> str:
    if value is None:
        return "UNAVAILABLE"
    if value <= -0.50:
        return "STRONG_BEARISH"
    if value <= -0.20:
        return "BEARISH"
    if value < 0.20:
        return "NEUTRAL"
    if value < 0.50:
        return "BULLISH"
    return "STRONG_BULLISH"


def score_evidence(
    evidence: Sequence[AnalystEvidence],
    *,
    required: tuple[str, ...] = ("market", "fundamentals"),
    minimum_coverage: float = 0.60,
    minimum_support: float = 0.50,
) -> EvidenceScore:
    """Aggregate seven independently provided scores with explicit provenance.

    Missing evidence is null/None, NEVER zero. A valid assessed neutral signal
    may use 0. Shared raw event IDs within flow/OI/dealer automatically halve
    downstream incremental weights; user-supplied overlap multipliers may
    discount further. Normalization ensures result is in [-1, +1].
    """
    _unit_interval("minimum_coverage", minimum_coverage)
    _unit_interval("minimum_support", minimum_support)
    if any(r not in ANALYSTS for r in required):
        raise ValueError("Unknown required analyst")
    by_name = {}
    for item in evidence:
        if item.analyst not in BASE_WEIGHTS:
            raise ValueError(f"Unknown analyst: {item.analyst}")
        if item.analyst in by_name:
            raise ValueError(f"Duplicate analyst: {item.analyst}")
        for name in ("confidence", "quality", "freshness", "overlap_multiplier"):
            _unit_interval(name, getattr(item, name))
        if item.score is not None and (
            not isfinite(item.score) or not -1 <= item.score <= 1
        ):
            raise ValueError(f"Invalid score for {item.analyst}")
        if item.historical_effective_weight is not None and (
            not isfinite(item.historical_effective_weight)
            or item.historical_effective_weight < 0
        ):
            raise ValueError("Historical weight must be nonnegative and finite")
        if item.score not in (None, 0):
            if item.analyst == "flow" and item.direction_basis != "single_leg_sweep_block":
                raise ValueError("Directional flow requires qualifying single-leg SWEEP/BLOCK")
            if item.analyst == "oi" and item.direction_basis != "confirmed_change_plus_flow":
                raise ValueError("Directional OI requires verified OI change plus single-leg flow")
        by_name[item.analyst] = item

    seen_derivatives: set[str] = set()
    contributions = []
    flags = []
    available_prior = 0.0
    total_effective = 0.0
    numerator = 0.0
    for analyst in ANALYSTS:
        item = by_name.get(analyst)
        if item is None or item.score is None:
            contributions.append(
                AnalystContribution(analyst, None, 0.0, 0.0, 1.0, False,
                                    item.as_of if item else None,
                                    item.source_ids if item else ())
            )
            continue
        shared_raw_ids = set(item.source_ids) & seen_derivatives
        auto_overlap = 0.50 if analyst in DERIVATIVE_ANALYSTS and shared_raw_ids else 1.0
        overlap = min(item.overlap_multiplier, auto_overlap)
        weight = (
            item.historical_effective_weight
            if item.historical_effective_weight is not None
            else BASE_WEIGHTS[analyst] * item.confidence * item.quality
            * item.freshness * overlap
        )
        if analyst in DERIVATIVE_ANALYSTS:
            seen_derivatives.update(item.source_ids)
        if item.as_of is None:
            flags.append(f"{analyst}:as_of_missing")
        if item.historical_effective_weight is not None:
            flags.append(f"{analyst}:historical_weight_override")
        available_prior += BASE_WEIGHTS[analyst] if weight > 0 else 0
        total_effective += weight
        piece = item.score * weight
        numerator += piece
        contributions.append(
            AnalystContribution(analyst, item.score, weight, piece, overlap,
                                weight > 0, item.as_of, item.source_ids)
        )

    missing = tuple(a for a in ANALYSTS if a not in by_name or
                    by_name[a].score is None)
    available_coverage = available_prior / sum(BASE_WEIGHTS.values())
    # Effective support is normalized to prior budget. Historical overrides
    # may exceed that budget and are capped for the support diagnostic only.
    effective_support = min(1.0, total_effective / sum(BASE_WEIGHTS.values()))
    value = numerator / total_effective if total_effective > 0 else None
    absent_required = any(a in missing for a in required)
    if absent_required or value is None or available_coverage < minimum_coverage:
        status = "INSUFFICIENT"
    elif effective_support < minimum_support or missing:
        status = "PROVISIONAL"
    else:
        status = "READY"
    return EvidenceScore(VERSION, value, classify(value), available_coverage,
                         effective_support, status, missing, tuple(flags),
                         tuple(contributions))


def decide_trade(
    score: EvidenceScore,
    gate: TradeGate,
    *,
    options: bool = True,
) -> TradeDecision:
    """Separate execution/readiness assessment: NEVER places or routes orders."""
    if score.value is None:
        direction = "UNKNOWN"
    elif score.value > 0.20:
        direction = "BULLISH"
    elif score.value < -0.20:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
    reasons = []
    if score.status != "READY":
        reasons.append(f"SES evidence status is {score.status}")
    names = ["quote_fresh", "technical_confirmed", "liquidity_ok",
             "risk_reward_ok", "event_risk_ok"]
    if options:
        names.append("derivatives_fresh")
        if any(a in score.missing for a in ("flow", "oi")):
            reasons.append("Options evidence incomplete")
    for name in names:
        if getattr(gate, name) is not True:
            reasons.append(f"{name}: not verified true")
    if reasons:
        return TradeDecision("NO_TRADE", direction, tuple(reasons))
    if abs(score.value or 0.0) >= 0.50:
        return TradeDecision("CANDIDATE_FOR_REVIEW", direction,
                             ("Requires portfolio-manager approval; no automatic order",))
    return TradeDecision("WATCH", direction, ("Score below actionable threshold",))
