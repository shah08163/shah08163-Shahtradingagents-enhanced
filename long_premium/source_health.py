"""Fail-closed source selection and provenance for the long-premium screen.

Provider callables are injected by the runtime that owns their authorized
connections. This module never reads or changes OAuth credentials or secrets.
"""
from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

UTC = dt.UTC
PRIMARY = ("schwab_cloudflare", "alpaca_sip")
CONTINGENCY = "schwab_northflank"


def utc_now() -> dt.datetime:
    return dt.datetime.now(UTC)


def parse_timestamp(value: str | dt.datetime | None) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class MarketSnapshot:
    source: str
    symbol: str
    retrieved_at: str
    provider_timestamp: str | None
    delayed: bool | None
    consolidated: bool
    expected_coverage: int
    received_coverage: int
    expected_option_coverage: int
    received_option_coverage: int
    quote: dict[str, Any]
    options: list[dict[str, Any]] = field(default_factory=list)
    coverage_scope: str = "symbol"


@dataclass
class SourceAttempt:
    source: str
    status: str
    checked_at: str
    provider_timestamp: str | None = None
    delayed: bool | None = None
    consolidated: bool | None = None
    expected_coverage: int = 0
    received_coverage: int = 0
    coverage_ratio: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass
class SelectedSnapshot:
    snapshot: MarketSnapshot
    attempts: list[SourceAttempt]

    def audit(self) -> dict[str, Any]:
        return {
            "selected_source": self.snapshot.source,
            "provider_timestamp": self.snapshot.provider_timestamp,
            "retrieved_at": self.snapshot.retrieved_at,
            "delayed": self.snapshot.delayed,
            "consolidated": self.snapshot.consolidated,
            "coverage": {
                "scope": self.snapshot.coverage_scope,
                "expected": self.snapshot.expected_coverage,
                "received": self.snapshot.received_coverage,
                "ratio": self.snapshot.received_coverage / self.snapshot.expected_coverage,
            },
            "options": {
                "expected": self.snapshot.expected_option_coverage,
                "received": self.snapshot.received_option_coverage,
                "ratio": self.snapshot.received_option_coverage / self.snapshot.expected_option_coverage,
            },
            "attempts": [asdict(attempt) for attempt in self.attempts],
        }


class NoHealthySource(RuntimeError):
    def __init__(self, attempts: list[SourceAttempt]):
        self.attempts = attempts
        super().__init__("No primary/secondary market source passed hard health gates")


def _validate(snapshot: MarketSnapshot, *, symbol: str, max_age_seconds: int) -> list[str]:
    reasons: list[str] = []
    if snapshot.symbol.upper() != symbol.upper():
        reasons.append("symbol_mismatch")
    if snapshot.source not in (*PRIMARY, CONTINGENCY):
        reasons.append("unknown_source")
    if snapshot.delayed is not False:
        reasons.append("delayed_or_delay_status_unknown")
    if not snapshot.consolidated:
        reasons.append("non_consolidated_feed")
    expected = snapshot.expected_coverage
    received = snapshot.received_coverage
    if expected < 1 or received != expected:
        reasons.append("incomplete_coverage")
    expected_options = snapshot.expected_option_coverage
    received_options = snapshot.received_option_coverage
    if expected_options < 1 or received_options != expected_options:
        reasons.append("incomplete_option_coverage")
    if not snapshot.quote:
        reasons.append("missing_quote")
    retrieved = parse_timestamp(snapshot.retrieved_at)
    provider_time = parse_timestamp(snapshot.provider_timestamp)
    now = utc_now()
    if retrieved is None:
        reasons.append("invalid_retrieval_timestamp")
    elif (now - retrieved).total_seconds() > max_age_seconds or (retrieved - now).total_seconds() > 5:
        reasons.append("stale_or_future_retrieval_timestamp")
    if provider_time is None:
        reasons.append("missing_or_invalid_provider_timestamp")
    elif (now - provider_time).total_seconds() > max_age_seconds or (provider_time - now).total_seconds() > 5:
        reasons.append("stale_or_future_provider_timestamp")
    return reasons


def trade_hard_gate_failures(snapshot: MarketSnapshot, flow: FlowSnapshot) -> list[str]:
    """Combine consolidated liquidity/option checks with Bullflow GEX/VEX coverage."""
    quote = snapshot.quote
    failures = consolidated_liquidity_gates(
        price=quote.get("price"),
        consolidated_adv20_shares=quote.get("consolidated_adv20_shares"),
        consolidated_adv20_dollars=quote.get("consolidated_adv20_dollars"),
        option_legs=snapshot.options,
        combined_spread_slippage_pct=quote.get("combined_spread_slippage_pct"),
    )
    return failures + validate_flow_snapshot(flow, ticker=snapshot.symbol)


def select_market_snapshot(
    symbol: str,
    providers: dict[str, Callable[[str], MarketSnapshot]],
    *,
    max_age_seconds: int = 30,
    allow_northflank_contingency: bool = False,
) -> SelectedSnapshot:
    """Try Schwab Cloudflare then Alpaca SIP; Northflank is opt-in contingency only."""
    order = list(PRIMARY)
    if allow_northflank_contingency:
        order.append(CONTINGENCY)
    attempts: list[SourceAttempt] = []
    for source in order:
        checked_at = utc_now().isoformat()
        provider = providers.get(source)
        if provider is None:
            attempts.append(SourceAttempt(source, "unavailable", checked_at, reasons=["provider_not_configured"]))
            continue
        try:
            snapshot = provider(symbol)
        except Exception as exc:  # Provider adapters must not hide transport/auth failures.
            attempts.append(SourceAttempt(source, "error", checked_at, reasons=[type(exc).__name__]))
            continue
        reasons = _validate(snapshot, symbol=symbol, max_age_seconds=max_age_seconds)
        expected = snapshot.expected_coverage
        received = snapshot.received_coverage
        attempts.append(SourceAttempt(
            source=source,
            status="healthy" if not reasons else "rejected",
            checked_at=checked_at,
            provider_timestamp=snapshot.provider_timestamp,
            delayed=snapshot.delayed,
            consolidated=snapshot.consolidated,
            expected_coverage=expected,
            received_coverage=received,
            coverage_ratio=received / expected if expected else 0.0,
            reasons=reasons,
        ))
        if not reasons:
            return SelectedSnapshot(snapshot, attempts)
    raise NoHealthySource(attempts)


@dataclass(frozen=True)
class FlowSnapshot:
    source: str
    ticker: str
    retrieved_at: str
    provider_timestamp: str | None
    gex_rows: list[dict[str, Any]]
    vex_rows: list[dict[str, Any]]
    delayed: bool | None = False


def validate_flow_snapshot(flow: FlowSnapshot, *, ticker: str, max_age_seconds: int = 60) -> list[str]:
    """Validate Bullflow evidence; missing or stale GEX/VEX stays a hard failure."""
    reasons: list[str] = []
    if flow.source != "bullflow":
        reasons.append("wrong_flow_source")
    if flow.ticker.upper() != ticker.upper():
        reasons.append("ticker_mismatch")
    if flow.delayed is not False:
        reasons.append("delayed_or_delay_status_unknown")
    if not flow.gex_rows:
        reasons.append("missing_gex_coverage")
    if not flow.vex_rows:
        reasons.append("missing_vex_coverage")
    now = utc_now()
    for label, value in (("retrieval", flow.retrieved_at), ("provider", flow.provider_timestamp)):
        timestamp = parse_timestamp(value)
        if timestamp is None:
            reasons.append(f"invalid_{label}_timestamp")
        elif (now - timestamp).total_seconds() > max_age_seconds or (timestamp - now).total_seconds() > 5:
            reasons.append(f"stale_or_future_{label}_timestamp")
    return reasons


def consolidated_liquidity_gates(
    *,
    price: float | None,
    consolidated_adv20_shares: float | None,
    consolidated_adv20_dollars: float | None,
    option_legs: Iterable[dict[str, Any]],
    combined_spread_slippage_pct: float | None,
    min_legs: int = 1,
) -> list[str]:
    """Return all failed production hard gates; absent data never passes."""
    failures: list[str] = []
    if not _finite_at_least(price, 20):
        failures.append("price_below_20_or_missing")
    if not _finite_at_least(consolidated_adv20_shares, 1_000_000):
        failures.append("consolidated_adv20_shares_below_1m_or_missing")
    if not _finite_at_least(consolidated_adv20_dollars, 100_000_000):
        failures.append("consolidated_adv20_dollars_below_100m_or_missing")
    legs = list(option_legs)
    if len(legs) < min_legs:
        failures.append("insufficient_option_leg_coverage")
    for index, leg in enumerate(legs):
        if not _finite_at_least(leg.get("open_interest"), 500):
            failures.append(f"leg_{index}_open_interest_below_500_or_missing")
        if not _finite_at_least(leg.get("volume"), 50):
            failures.append(f"leg_{index}_volume_below_50_or_missing")
        spread = leg.get("bid_ask_spread_pct")
        if not _finite_at_most(spread, 10):
            failures.append(f"leg_{index}_spread_above_10pct_or_missing")
    if not _finite_at_most(combined_spread_slippage_pct, 10):
        failures.append("combined_spread_slippage_above_10pct_or_missing")
    return failures


def _finite_at_least(value: Any, threshold: float) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) >= threshold
    except (TypeError, ValueError):
        return False


def _finite_at_most(value: Any, threshold: float) -> bool:
    try:
        return math.isfinite(float(value)) and float(value) <= threshold
    except (TypeError, ValueError):
        return False

