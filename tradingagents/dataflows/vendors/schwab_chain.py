"""Read-only Schwab full-chain OI and IV snapshot from the protected bridge."""
from __future__ import annotations

import json
import math
import os
from datetime import date
from urllib.parse import urlsplit

import requests

URL_ENV = "SCHWAB_BRIDGE_URL"
TOKEN_ENV = "SCHWAB_EXPLORER_ACCESS_TOKEN"


def configured() -> bool:
    return bool(os.environ.get(URL_ENV) and os.environ.get(TOKEN_ENV))


def fetch_chain_summary(symbol: str, trade_date: str, max_dte: int = 60) -> str:
    """Return a bounded, auditable chain summary; never log credentials/URLs."""
    if not configured():
        return "<unavailable: Schwab bridge URL or access token not configured>"
    url = os.environ[URL_ENV].rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return "<unavailable: Schwab bridge endpoint configuration invalid>"
    # Current snapshots must never masquerade as historical point-in-time chains.
    if trade_date != date.today().isoformat():
        return "<unavailable: Schwab explorer provides current snapshots only, not historical as-of OI/IV>"
    try:
        response = requests.post(
            url + "/explorer/snapshot",
            headers={"Authorization": "Bearer " + os.environ[TOKEN_ENV]},
            json={"symbol": symbol, "min_dte": 0, "max_dte": max_dte},
            timeout=(15, 180),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("contracts"), list):
            return "<unavailable: Schwab explorer returned malformed chain>"
        rows = payload["contracts"]
        by_expiry = {}
        by_strike = {}
        iv_by_expiry = {}
        paired_iv = {}
        underlying = (payload.get("underlying") or {}).get("last")
        for row in rows:
            if not isinstance(row, dict):
                continue
            expiry, side, strike = row.get("expiration"), row.get("call_put"), row.get("strike")
            oi, iv = row.get("open_interest"), row.get("implied_volatility_pct")
            if not expiry or side not in ("CALL", "PUT") or not isinstance(strike, (int, float)):
                continue
            key = (expiry, side)
            if isinstance(oi, (int, float)) and oi >= 0:
                by_expiry[key] = by_expiry.get(key, 0) + oi
                wall_key = (expiry, side, strike)
                by_strike[wall_key] = by_strike.get(wall_key, 0) + oi
            # Only usable near-ATM IV; avoid deep ITM IV artifacts and missing Greeks.
            if (isinstance(iv, (int, float)) and not isinstance(iv, bool)
                    and math.isfinite(iv) and 0 < iv < 500
                    and isinstance(underlying, (int, float)) and underlying > 0
                    and abs(strike / underlying - 1) <= 0.05):
                iv_by_expiry.setdefault(key, []).append(iv)
                paired_iv.setdefault((expiry, strike), {})[side] = iv
        top = sorted(by_strike.items(), key=lambda kv: kv[1], reverse=True)[:30]
        # Same-strike comparisons avoid calling the difference between disjoint
        # average strike sets "skew". Identical provider IVs are inconclusive.
        differences = {}
        for (expiry, _strike), sides in paired_iv.items():
            if "CALL" in sides and "PUT" in sides:
                differences.setdefault(expiry, []).append(sides["PUT"] - sides["CALL"])
        skew = []
        for expiry, values in sorted(differences.items()):
            if len(values) < 2 or all(abs(v) < 0.01 for v in values):
                skew.append({"expiration": expiry, "status": "unverified",
                             "matched_strikes": len(values),
                             "reason": "Insufficient independently differentiated put/call IV observations"})
            else:
                skew.append({"expiration": expiry, "status": "observed",
                             "matched_strikes": len(values),
                             "mean_put_minus_call_iv_percentage_points": round(sum(values) / len(values), 2)})

        result = {
            "source": "Schwab Market Data API via authenticated Schwab bridge",
            "symbol": symbol,
            "analysis_date": trade_date,
            "snapshot_only": True,
            "underlying": payload.get("underlying"),
            "contract_count": len(rows),
            "requested_dte_range": [0, max_dte],
            "notes": payload.get("notes", []),
            "open_interest_by_expiry_and_side": [
                {"expiration": e, "side": side, "oi": value}
                for (e, side), value in sorted(by_expiry.items())
            ],
            "largest_oi_strikes": [
                {"expiration": e, "side": side, "strike": strike, "oi": value}
                for (e, side, strike), value in top
            ],
            "near_atm_iv_pct_by_expiry_side": [
                {"expiration": e, "side": side, "mean_iv_pct": round(sum(values) / len(values), 2), "contracts": len(values)}
                for (e, side), values in sorted(iv_by_expiry.items())
            ],
            "near_atm_matched_strike_put_call_iv_comparison": skew,
            "limitations": [
                "OI is a provider snapshot, not opening/closing intent or next-day OI change.",
                "Near-ATM IV arithmetic means are descriptive, not standardized 30-day IV.",
                "Identical call and put IV values do not prove zero skew; use matched-strike comparison status.",
                "Provider fields and quote timestamps may be stale outside market hours.",
                "A missing/partial chain cannot establish reliable full-market walls.",
            ],
        }
        return json.dumps(result, default=str)
    except Exception as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        return f"<unavailable: Schwab bridge request failed ({type(exc).__name__}" + (f" HTTP {code}" if code else "") + ")>"
