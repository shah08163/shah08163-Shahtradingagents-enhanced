"""Summarize an owner-supplied Schwab Cloudflare MCP explorer snapshot.

The Render service cannot borrow ChatGPT's Cloudflare OAuth session. ChatGPT may
retrieve the chain via its connected MCP tool and pass a bounded, sanitized
snapshot to an authenticated Shah research request. No Cloudflare credentials
are accepted, stored, or logged by this module.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

MAX_CONTRACTS = 7500
MAX_AGE = timedelta(hours=6)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Cloudflare snapshot retrieval timestamp is missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Cloudflare snapshot retrieval timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("Cloudflare snapshot retrieval timestamp lacks timezone")
    return parsed.astimezone(UTC)


def _number(value: object, *, nonnegative: bool = False) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    v = float(value)
    if not math.isfinite(v) or (nonnegative and v < 0):
        return None
    return v


def summarize_cloudflare_snapshot(snapshot: dict, symbol: str, trade_date: str, max_dte: int = 60) -> str:
    """Validate a Cloudflare tool payload and return compact OI/IV evidence.

    Origin is asserted by the authenticated ChatGPT caller, not independently
    verified by Render. Never accept raw arbitrary prose into the analyst prompt.
    """
    if not isinstance(snapshot, dict) or snapshot.get("source") != "Schwab Market Data API":
        raise ValueError("Expected a Schwab Market Data API explorer snapshot")
    if snapshot.get("symbol") != symbol or not (1 <= len(symbol) <= 20):
        raise ValueError("Cloudflare snapshot symbol does not match analysis ticker")
    requested = snapshot.get("requested_range")
    if not isinstance(requested, dict) or requested.get("min_dte") != 0 or requested.get("max_dte") != max_dte:
        raise ValueError("Cloudflare snapshot must cover the requested 0-60 DTE range")
    underlying = snapshot.get("underlying")
    if not isinstance(underlying, dict):
        raise ValueError("Cloudflare snapshot lacks underlying metadata")
    spot = _number(underlying.get("last"))
    if spot is None or spot <= 0:
        raise ValueError("Cloudflare snapshot has no valid underlying price")
    retrieved = _timestamp(underlying.get("retrieval_timestamp"))
    age = datetime.now(UTC) - retrieved
    if age > MAX_AGE or age < -timedelta(minutes=10):
        raise ValueError("Cloudflare snapshot was not retrieved recently")
    rows = snapshot.get("contracts")
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_CONTRACTS:
        raise ValueError("Cloudflare options chain missing or exceeds safe contract limit")

    expiry_oi = defaultdict(int)
    strike_oi = defaultdict(int)
    iv_by_expiry = defaultdict(list)
    iv_pairs = defaultdict(dict)
    contract_count = 0
    ignored = 0
    observed = date.today()
    for row in rows:
        if not isinstance(row, dict):
            ignored += 1
            continue
        expiry, side = row.get("expiration"), row.get("call_put")
        strike = _number(row.get("strike"))
        if not isinstance(expiry, str) or side not in ("CALL", "PUT") or strike is None or strike <= 0:
            ignored += 1
            continue
        try:
            expiration = date.fromisoformat(expiry)
        except ValueError:
            ignored += 1
            continue
        days = (expiration - observed).days
        if days < 0 or days > max_dte:
            ignored += 1
            continue
        contract_count += 1
        oi = _number(row.get("open_interest"), nonnegative=True)
        if oi is not None:
            oi_int = int(oi)
            expiry_oi[(expiry, side)] += oi_int
            strike_oi[(expiry, side, strike)] += oi_int
        iv = _number(row.get("implied_volatility_pct"))
        if iv is not None and 0 < iv < 500 and abs(strike / spot - 1) <= 0.05:
            iv_by_expiry[(expiry, side)].append(iv)
            iv_pairs[(expiry, strike)][side] = iv
    if contract_count == 0:
        raise ValueError("Cloudflare snapshot contains no valid contracts within requested range")

    matches = defaultdict(list)
    for (expiry, _strike), pair in iv_pairs.items():
        if "CALL" in pair and "PUT" in pair:
            matches[expiry].append(pair["PUT"] - pair["CALL"])
    skew = []
    for expiry, values in sorted(matches.items()):
        if len(values) < 2 or all(abs(x) < 0.01 for x in values):
            skew.append({"expiration": expiry, "status": "unverified", "matched_strikes": len(values),
                         "reason": "No independently differentiated matched-strike put/call IV observations"})
        else:
            skew.append({"expiration": expiry, "status": "observed", "matched_strikes": len(values),
                         "mean_put_minus_call_iv_percentage_points": round(sum(values) / len(values), 2)})

    output = {
        "source": "Schwab Market Data API via ChatGPT Cloudflare MCP explorer",
        "provenance": "Authenticated caller-supplied payload; service validates structure and freshness, not OAuth provenance",
        "symbol": symbol,
        "analysis_date": trade_date,
        "snapshot_only": True,
        "retrieved_at_utc": retrieved.isoformat(),
        "underlying_last": spot,
        "underlying_quote_time": underlying.get("provider_quote_timestamp") if isinstance(underlying.get("provider_quote_timestamp"), str) else None,
        "provider_realtime_label": underlying.get("realtime_delayed") if underlying.get("realtime_delayed") in ("Realtime", "Delayed") else "Unknown",
        "contract_count": contract_count,
        "unusable_contract_rows": ignored,
        "requested_dte_range": [0, max_dte],
        "open_interest_by_expiry_and_side": [
            {"expiration": exp, "side": side, "oi": value}
            for (exp, side), value in sorted(expiry_oi.items())
        ],
        "largest_oi_strikes": [
            {"expiration": exp, "side": side, "strike": strike, "oi": value}
            for (exp, side, strike), value in sorted(strike_oi.items(), key=lambda kv: kv[1], reverse=True)[:30]
        ],
        "near_atm_iv_pct_by_expiry_side": [
            {"expiration": exp, "side": side, "mean_iv_pct": round(sum(values) / len(values), 2),
             "contracts": len(values)}
            for (exp, side), values in sorted(iv_by_expiry.items())
        ],
        "near_atm_matched_strike_put_call_iv_comparison": skew,
        "limitations": [
            "Provider data is a snapshot, not an OI change or proof of opening trades.",
            "Weekend and closed-market quotes may be stale even when the entitlement says Realtime.",
            "Near-ATM arithmetic IV averages are not standardized 30-day implied volatility.",
            "Identical vendor call/put IV does not establish zero skew.",
            "Client-supplied data are not independently authenticated by this research backend.",
            "A partial chain cannot establish complete market-wide OI walls.",
        ],
    }
    return json.dumps(output, separators=(",", ":"), default=str)
