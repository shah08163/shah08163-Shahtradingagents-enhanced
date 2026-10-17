"""Bullflow REST adapter for hosted TradingAgents deployments.

The service uses a Bullflow API key supplied through the BULLFLOW_API_KEY
environment variable. Functions degrade to explicit <unavailable> blocks so a
missing/limited vendor never crashes the research graph.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

import requests

BASE_URL = os.environ.get("BULLFLOW_API_BASE", "https://api.bullflow.io").rstrip("/")
API_KEY_ENV = "BULLFLOW_API_KEY"
TIMEOUT_SECONDS = 20


def configured() -> bool:
    return bool(os.environ.get(API_KEY_ENV))


def _get(path: str, **params: Any) -> dict[str, Any]:
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{API_KEY_ENV} is not configured")
    clean = {k: v for k, v in params.items() if v is not None}
    clean["key"] = key
    response = requests.get(f"{BASE_URL}{path}", params=clean, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    if isinstance(payload, dict):
        return payload
    return {"result": payload}


def _safe(label: str, fn) -> str:
    try:
        return json.dumps(fn(), indent=2, sort_keys=True, default=str)
    except Exception as exc:
        return f"<unavailable source=\"Bullflow {label}\" reason=\"{type(exc).__name__}: {exc}\">"


def fetch_flow_bundle(ticker: str, trade_date: str) -> str:
    """Return the Bullflow flow evidence used by the Flow Analyst."""
    start = (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=5)).strftime("%Y-%m-%d")
    profile = _safe("optionsProfile", lambda: _get("/v1/data/optionsProfile", symbol=ticker))
    series = _safe(
        "netPremiumSeries",
        lambda: _get(
            "/v1/data/netPremiumSeries",
            ticker=ticker,
            **{"from": start, "to": trade_date, "period": "1D", "include_multileg": "false"},
        ),
    )
    high_signal = _safe(
        "historicalOptionsFlow",
        lambda: _get(
            "/v1/data/historicalOptionsFlow",
            date=trade_date,
            ticker=ticker,
            minScore=0.80,
            minPremium=100000,
            limit=250,
        ),
    )
    return (
        "## Bullflow options activity profile\n" + profile
        + "\n\n## Bullflow net directional premium series\n" + series
        + "\n\n## Bullflow high-signal / $100k+ recorded trades\n" + high_signal
    )


def fetch_oi_bundle(ticker: str, trade_date: str) -> str:
    """Return Bullflow OI-oriented evidence.

    Bullflow's public API does not expose a complete option-chain OI snapshot.
    This bundle therefore uses the options-profile unusual-contract section and
    recorded trade metadata (volume vs OI) and must not claim full-chain OI walls.
    Full-chain OI verification belongs to the Schwab provider layer.
    """
    profile = _safe("optionsProfile", lambda: _get("/v1/data/optionsProfile", symbol=ticker))
    trades = _safe(
        "historicalOptionsFlow",
        lambda: _get(
            "/v1/data/historicalOptionsFlow",
            date=trade_date,
            ticker=ticker,
            minSize=1,
            limit=500,
        ),
    )
    return (
        "## Bullflow options profile (includes unusual contract volume/open-interest ratios)\n"
        + profile
        + "\n\n## Bullflow recorded option trades for OI/volume context\n"
        + trades
        + "\n\nIMPORTANT: This is recorded-flow OI context, not a complete market-wide option-chain OI snapshot."
    )
