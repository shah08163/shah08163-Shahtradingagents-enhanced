"""Regression tests for SES v1.0. No network or order execution."""
import pytest

from tradingagents.ses import (
    AnalystEvidence, TradeGate, classify, decide_trade, score_evidence,
)
from tradingagents.ses_calibration import Outcome, evaluate_outcomes


@pytest.mark.unit
def test_eght_completed_shah_legacy_score_regression():
    # Reference: completed Oct-18 EGHT report, -0.331.
    # These are the report's EXISTING effective weights, not SES new priors.
    scores = [
        ("market", -0.48, 0.550), ("social", -0.18, 0.043),
        ("news", -0.08, 0.080), ("fundamentals", -0.30, 0.230),
        ("flow", 0.0, 0.016), ("oi", 0.0, 0.051),
        ("dealer", 0.0, 0.080),
    ]
    result = score_evidence([
        AnalystEvidence(a, s, historical_effective_weight=w) for a, s, w in scores
    ])
    assert result.value == pytest.approx(-0.3306095238095)
    assert round(result.value, 3) == -0.331
    assert result.classification == "BEARISH"
    assert result.version == "SES-v1.0.0"


@pytest.mark.unit
def test_aapl_prior_chat_score_is_illustrative_only():
    # This tests historical ARITHMETIC, NOT an official Shah AAPL result.
    rows = [
        ("market", 0.45, 0.60), ("social", 0.05, 0.03),
        ("news", 0.20, 0.12), ("fundamentals", 0.40, 0.30),
        ("flow", 0.10, 0.20), ("oi", 0.0, 0.10),
        ("dealer", 0.15, 0.15),
    ]
    data = [
        AnalystEvidence(a, s, historical_effective_weight=w,
                        direction_basis=("single_leg_sweep_block" if a == "flow" else
                                         "unspecified"))
        for a, s, w in rows
    ]
    answer = score_evidence(data)
    assert round(answer.value, 2) == 0.31


@pytest.mark.unit
def test_missing_is_not_neutral_or_ignored_in_readiness():
    result = score_evidence([AnalystEvidence("market", 0.8)])
    assert result.status == "INSUFFICIENT"
    assert "fundamentals" in result.missing
    assert result.value == pytest.approx(0.8)
    assert decide_trade(result, TradeGate(), options=True).status == "NO_TRADE"


@pytest.mark.unit
def test_quality_and_freshness_reduce_weight():
    inputs = [
        AnalystEvidence("market", 1.0, freshness=0.5, as_of="2026-10-16"),
        AnalystEvidence("fundamentals", -1.0, as_of="2026-10-16"),
    ]
    score = score_evidence(inputs)
    assert score.value == pytest.approx((0.22 * 0.5 - 0.24) / (0.22 * 0.5 + 0.24))


@pytest.mark.unit
def test_shared_derivative_trade_ids_are_discounted():
    inputs = [
        AnalystEvidence("market", 0.0),
        AnalystEvidence("fundamentals", 0.0),
        AnalystEvidence("flow", 0.6, direction_basis="single_leg_sweep_block",
                        source_ids=("trade-100",)),
        AnalystEvidence("oi", 0.4, direction_basis="confirmed_change_plus_flow",
                        source_ids=("trade-100", "oi-200")),
        AnalystEvidence("dealer", 0.2, source_ids=("oi-200",)),
    ]
    report = score_evidence(inputs)
    components = {x.analyst: x for x in report.contributions}
    assert components["flow"].overlap_adjustment == 1.0
    assert components["oi"].overlap_adjustment == 0.5
    assert components["dealer"].overlap_adjustment == 0.5


@pytest.mark.unit
@pytest.mark.parametrize("analyst,basis", [
    ("flow", "MULTI"), ("flow", "call_volume"),
    ("oi", "MULTI"), ("oi", "oi_level_only"),
])
def test_direction_requires_validated_single_leg_evidence(analyst, basis):
    with pytest.raises(ValueError):
        score_evidence([AnalystEvidence(analyst, 0.5, direction_basis=basis)])


@pytest.mark.unit
def test_insufficient_trade_gates_block_automatic_action():
    inputs = [AnalystEvidence(a, 0.8, as_of="2026-10-16",
              direction_basis=(
                  "single_leg_sweep_block" if a == "flow" else
                  "confirmed_change_plus_flow" if a == "oi" else "unspecified"
              )) for a in ("market","social","news","fundamentals","flow","oi","dealer")]
    s = score_evidence(inputs)
    assert s.status == "READY"
    assert decide_trade(s, TradeGate(), options=True).status == "NO_TRADE"
    all_verified = TradeGate(True, True, True, True, True, True)
    result = decide_trade(s, all_verified, options=True)
    assert result.status == "CANDIDATE_FOR_REVIEW"
    assert "no automatic order" in result.reasons[0]


@pytest.mark.unit
def test_thresholds():
    assert classify(-0.5) == "STRONG_BEARISH"
    assert classify(-0.2) == "BEARISH"
    assert classify(0) == "NEUTRAL"
    assert classify(0.2) == "BULLISH"
    assert classify(0.5) == "STRONG_BULLISH"


@pytest.mark.unit
def test_point_in_time_calibration_and_minimum_sample():
    rows = [Outcome("EGHT", "2026-10-18", "2026-10-16",
                    "2026-11-18", -0.3, -0.04)]
    metrics = evaluate_outcomes(rows, minimum_observations=30)
    bearish = next(x for x in metrics if x.bucket == "BEARISH")
    assert bearish.observations == 1
    assert bearish.directional_hit_rate == 1.0
    assert not bearish.ready_for_calibration


@pytest.mark.unit
def test_lookahead_rejected():
    with pytest.raises(ValueError, match="Lookahead"):
        evaluate_outcomes([Outcome("AAPL", "2026-10-16", "2026-10-17",
                                   "2026-11-16", 0.3, 0.01)])
