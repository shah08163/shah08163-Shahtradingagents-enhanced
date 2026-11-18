"""Fail-closed validation for connected Schwab and Bullflow evidence.

This module makes no network calls. ChatGPT gathers source responses, then the
native runner validates the exact responses before analyst interpretation.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from math import isfinite
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def unwrap_tool_result(value):
    """Unwrap JSON, MCP content text, or structuredContent without losing payload."""
    for _ in range(5):
        if isinstance(value, str):
            value = json.loads(value)
            continue
        if not isinstance(value, dict):
            raise ValueError("Tool response must contain a JSON object")
        structured = value.get("structuredContent")
        if isinstance(structured, dict) and structured:
            value = structured
            continue
        content = value.get("content")
        if isinstance(content, list):
            text = next((x.get("text") for x in content
                         if isinstance(x, dict) and isinstance(x.get("text"), str)), None)
            if text is not None:
                value = text
                continue
        text = value.get("text")
        if isinstance(text, str):
            value = text
            continue
        return value
    raise ValueError("Tool response nesting exceeded safe limit")


def _as_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        if len(raw) == 10:
            return date.fromisoformat(raw)
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            return None
        return stamp.astimezone(ET).date()
    except ValueError:
        return None


def validate_bullflow_pages(
    pages, *, ticker, date_value=None, start=None, end=None,
    rows_key="rows",
):
    """Validate a complete same-filter Bullflow page sequence and de-duplicate IDs."""
    ticker = ticker.upper().strip()
    if not ticker or not isinstance(pages, list) or not pages:
        raise ValueError("Ticker and at least one Bullflow page are required")
    if (date_value is None) == (start is None or end is None):
        raise ValueError("Supply either date_value or both start and end")
    expected_cursor = None
    seen_ids = set()
    rows = []
    duplicates = 0
    terminal = False
    as_of = None

    for index, raw in enumerate(pages):
        response = unwrap_tool_result(raw)
        status = response.get("status")
        if status is not None and not 200 <= int(status) < 300:
            raise ValueError(f"Bullflow page {index + 1} returned status {status}")
        request = response.get("request", {})
        data = response.get("data", response)
        if not isinstance(request, dict) or not isinstance(data, dict):
            raise ValueError("Malformed Bullflow page envelope")
        if str(request.get("ticker", data.get("ticker", ticker))).upper() != ticker:
            raise ValueError("Bullflow ticker mismatch")
        if date_value is not None and request.get("date", date_value) != date_value:
            raise ValueError("Bullflow page date mismatch")
        if start is not None:
            if request.get("from", start) != start or request.get("to", end) != end:
                raise ValueError("Bullflow page range mismatch")
        if request.get("cursor") != expected_cursor:
            raise ValueError("Bullflow pagination cursor discontinuity")
        if terminal:
            raise ValueError("Pages supplied after terminal hasMore=false")

        page_rows = data.get(rows_key)
        if page_rows is None and rows_key == "rows":
            page_rows = data.get("alerts")
        if not isinstance(page_rows, list):
            raise ValueError("Bullflow page rows are missing or malformed")
        for row in page_rows:
            if not isinstance(row, dict):
                raise ValueError("Bullflow row is not an object")
            row_ticker = row.get("ticker")
            if row_ticker and str(row_ticker).upper() not in (ticker,):
                raise ValueError("Bullflow row ticker mismatch")
            row_date = next((row.get(k) for k in (
                "tradeDate", "trade_date", "date", "sessionDate"
            ) if row.get(k) is not None), None)
            parsed = _as_date(row_date) if row_date is not None else None
            if row_date is not None and parsed is None:
                raise ValueError("Bullflow row has an invalid date")
            if parsed is not None:
                if date_value is not None and parsed != date.fromisoformat(date_value):
                    raise ValueError("Bullflow row falls outside requested session")
                if start is not None and not date.fromisoformat(start) <= parsed <= date.fromisoformat(end):
                    raise ValueError("Bullflow row falls outside requested range")
            ident = next((row.get(k) for k in (
                "event_id", "eventId", "trade_id", "tradeId", "id", "uuid"
            ) if row.get(k) not in (None, "")), None)
            if ident is not None:
                if str(ident) in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(str(ident))
            rows.append(row)

        as_of = data.get("asOf", data.get("as_of", as_of))
        has_more = data.get("hasMore")
        next_cursor = data.get("nextCursor")
        if not isinstance(has_more, bool):
            raise ValueError("Bullflow page lacks a boolean hasMore")
        if has_more and (not isinstance(next_cursor, str) or not next_cursor):
            raise ValueError("Bullflow hasMore=true without nextCursor")
        if not has_more and next_cursor not in (None, ""):
            raise ValueError("Bullflow terminal page unexpectedly has nextCursor")
        terminal = not has_more
        expected_cursor = next_cursor if has_more else None

    if not terminal:
        raise ValueError("Bullflow pages are incomplete; terminal page was not retrieved")
    return {
        "status": "VERIFIED",
        "ticker": ticker,
        "as_of": as_of,
        "page_count": len(pages),
        "row_count": len(rows),
        "duplicate_rows_removed": duplicates,
        "rows": rows,
    }


def validate_market_bars(bars, *, ticker, source_id, start, end):
    """Validate normalized completed daily bars; caller preserves raw source response."""
    if not isinstance(bars, list) or not bars or not source_id:
        raise ValueError("Market bars and source provenance are required")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    normalized, seen = [], set()
    for bar in bars:
        if not isinstance(bar, dict) or bar.get("completed") is not True:
            raise ValueError("Only completed bars may enter daily market analysis")
        day = _as_date(bar.get("date"))
        close = bar.get("close")
        if day is None or not first <= day <= last:
            raise ValueError("Bar date is missing or outside the requested range")
        if (isinstance(close, bool) or not isinstance(close, (float, int))
                or not isfinite(close) or close <= 0):
            raise ValueError("Bar close must be finite and positive")
        if day in seen:
            raise ValueError("Duplicate market bar date")
        seen.add(day)
        normalized.append((day, bar))
    normalized.sort(key=lambda item: item[0])
    if any(a[0] >= b[0] for a, b in zip(normalized, normalized[1:])):
        raise ValueError("Market bars are not strictly chronological")
    return {
        "ticker": ticker.upper(),
        "source_id": source_id,
        "start": normalized[0][0].isoformat(),
        "end": normalized[-1][0].isoformat(),
        "bar_count": len(normalized),
        "bars": [row for _, row in normalized],
    }


def select_market_bars(
    schwab_bars, alpaca_bars, *, ticker, start, end,
    schwab_source="Schwab Cloudflare Web",
    alpaca_source="Alpaca IEX",
):
    """Schwab is primary; use Alpaca only when Schwab data fails validation."""
    try:
        chosen = validate_market_bars(
            schwab_bars, ticker=ticker, source_id=schwab_source,
            start=start, end=end,
        )
        chosen["fallback_used"] = False
        return chosen
    except (TypeError, ValueError, KeyError) as schwab_error:
        try:
            chosen = validate_market_bars(
                alpaca_bars, ticker=ticker, source_id=alpaca_source,
                start=start, end=end,
            )
            chosen["fallback_used"] = True
            chosen["fallback_reason"] = str(schwab_error)
            return chosen
        except (TypeError, ValueError, KeyError) as alpaca_error:
            raise ValueError(
                "No valid price history: Schwab primary failed "
                f"({schwab_error}); Alpaca fallback failed ({alpaca_error})"
            ) from alpaca_error


def validate_schwab_chain(snapshot, *, ticker, trade_date, max_dte=60):
    """Keep current chain snapshots out of historical runs; report contract quality."""
    obj = unwrap_tool_result(snapshot)
    if obj.get("symbol", "").upper() != ticker.upper():
        raise ValueError("Schwab chain ticker mismatch")
    contracts = obj.get("contracts")
    if not isinstance(contracts, list):
        raise ValueError("Schwab full-strike contracts missing")
    requested = obj.get("requested_range", {})
    if requested and int(requested.get("max_dte", max_dte)) != max_dte:
        raise ValueError("Schwab chain DTE range mismatch")
    underlying = obj.get("underlying", {})
    stamp = underlying.get("retrieval_timestamp") or underlying.get("provider_quote_timestamp")
    snapshot_day = _as_date(stamp)
    target = date.fromisoformat(trade_date)
    if snapshot_day is None or snapshot_day != target:
        raise ValueError("Current Schwab chain cannot be used for a different historical date")
    usable = 0
    oi_rows = 0
    stale = 0
    for row in contracts:
        if not isinstance(row, dict):
            continue
        oi = row.get("open_interest")
        if isinstance(oi, (int, float)) and not isinstance(oi, bool) and oi >= 0:
            oi_rows += 1
        age = row.get("quote_age_seconds")
        quality = str(row.get("quality_issues", "")).lower()
        iv = row.get("implied_volatility_pct")
        if isinstance(age, (int, float)) and age > 900:
            stale += 1
        if (isinstance(age, (int, float)) and age <= 900
                and "adjusted deliverable" not in quality
                and isinstance(iv, (int, float)) and not isinstance(iv, bool)
                and isfinite(iv) and 0 < iv < 500):
            usable += 1
    return {
        "status": "VERIFIED" if usable else "PARTIAL",
        "source": obj.get("source", "Schwab Market Data API"),
        "ticker": ticker.upper(),
        "as_of": stamp,
        "contract_count": len(contracts),
        "contracts_with_oi": oi_rows,
        "contracts_usable_for_quote_iv": usable,
        "stale_contracts": stale,
        "realtime_delayed": underlying.get("realtime_delayed", "unknown"),
        "limitations": [
            "OI snapshot is not opening/closing intent or an OI change.",
            "Contract quote/IV usability is filtered independently from OI counts.",
        ],
    }


def validate_gex_history(snapshots, *, ticker, trade_date):
    """Validate dated EOD GEX snapshots without filling missing sessions."""
    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError("Dated GEX history is required")
    target = date.fromisoformat(trade_date)
    normalized = []
    seen = set()
    for raw in snapshots:
        obj = unwrap_tool_result(raw)
        data = obj.get("data", obj)
        if str(data.get("ticker", "")).upper() != ticker.upper():
            raise ValueError("GEX history ticker mismatch")
        session = data.get("date")
        day = date.fromisoformat(session) if isinstance(session, str) else None
        if day is None or day > target or day in seen:
            raise ValueError("GEX history date is invalid, duplicated, or postdates analysis")
        oi_date = data.get("open_interest_date")
        if not isinstance(oi_date, str) or date.fromisoformat(oi_date) > day:
            raise ValueError("GEX history OI date is invalid or postdates snapshot")
        if not data.get("as_of") or not isinstance(data.get("strikes"), list):
            raise ValueError("GEX history snapshot lacks timestamp or strike rows")
        seen.add(day)
        normalized.append(data)
    normalized.sort(key=lambda row: row["date"])
    return {
        "status": "VERIFIED",
        "ticker": ticker.upper(),
        "sessions": len(normalized),
        "first_date": normalized[0]["date"],
        "last_date": normalized[-1]["date"],
        "as_of": normalized[-1]["as_of"],
        "gaps_preserved": True,
        "snapshots": normalized,
    }


def validate_range_response(raw, *, ticker, start, end, data_keys=()):
    """Validate a non-paginated dated series against its exact requested window."""
    response = unwrap_tool_result(raw)
    status = response.get("status")
    if status is not None and not 200 <= int(status) < 300:
        raise ValueError(f"Connected source returned status {status}")
    request = response.get("request", {})
    data = response.get("data", response)
    if not isinstance(data, dict) or not isinstance(request, dict):
        raise ValueError("Malformed dated-series envelope")
    if str(request.get("ticker", data.get("ticker", ticker))).upper() != ticker.upper():
        raise ValueError("Dated-series ticker mismatch")
    if request.get("from", start) != start or request.get("to", end) != end:
        raise ValueError("Dated-series request window mismatch")
    if data.get("ticker") and str(data["ticker"]).upper() != ticker.upper():
        raise ValueError("Dated-series payload ticker mismatch")
    observed_start = data.get("from", start)
    observed_end = data.get("to", end)
    if observed_start != start or observed_end != end:
        raise ValueError("Dated-series payload window mismatch")
    series = next((data.get(key) for key in data_keys
                   if isinstance(data.get(key), list)), None)
    if series is None:
        series = next((value for value in data.values() if isinstance(value, list)), None)
    if not isinstance(series, list) or not series:
        raise ValueError("Dated series is empty or missing")
    return {
        "status": "VERIFIED",
        "ticker": ticker.upper(),
        "from": start,
        "to": end,
        "row_count": len(series),
        "as_of": data.get("asOf", data.get("as_of")),
        "rows": series,
    }
