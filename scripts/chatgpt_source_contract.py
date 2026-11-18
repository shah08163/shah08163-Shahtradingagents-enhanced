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
    expected_filters = None

    for index, raw in enumerate(pages):
        response = unwrap_tool_result(raw)
        status = response.get("status")
        if status is not None and not 200 <= int(status) < 300:
            raise ValueError(f"Bullflow page {index + 1} returned status {status}")
        request = response.get("request", {})
        data = response.get("data", response)
        if not isinstance(request, dict) or not isinstance(data, dict):
            raise ValueError("Malformed Bullflow page envelope")
        if str(request.get("ticker", "")).upper() != ticker:
            raise ValueError("Bullflow request ticker missing or mismatched")
        if date_value is not None:
            if request.get("date") != date_value:
                raise ValueError("Bullflow page date missing or mismatched")
        if start is not None:
            if request.get("from") != start or request.get("to") != end:
                raise ValueError("Bullflow page range missing or mismatched")
        filters = {key: value for key, value in request.items()
                   if key not in ("cursor", "link_id")}
        if expected_filters is None:
            expected_filters = filters
        elif filters != expected_filters:
            raise ValueError("Bullflow request filters changed during pagination")
        if data.get("ticker") is not None and str(data["ticker"]).upper() != ticker:
            raise ValueError("Bullflow response ticker mismatch")
        if date_value is not None:
            if data.get("date") not in (None, date_value):
                raise ValueError("Bullflow response date mismatch")
            if data.get("from") not in (None, date_value) or data.get("to") not in (None, date_value):
                raise ValueError("Bullflow response session range mismatch")
        if start is not None and (data.get("from") != start or data.get("to") != end):
            raise ValueError("Bullflow response range missing or mismatched")
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
            if row_date is None:
                timestamp = next((row.get(k) for k in (
                    "timestamp", "tradeTimestamp", "trade_timestamp", "trfTimestampMs"
                ) if row.get(k) is not None), None)
                if isinstance(timestamp, (int, float)) and not isinstance(timestamp, bool):
                    stamp_seconds = timestamp / 1000 if timestamp > 100000000000 else timestamp
                    row_date = datetime.fromtimestamp(stamp_seconds, tz=ZoneInfo("UTC")).isoformat()
                elif isinstance(timestamp, str):
                    row_date = timestamp
            parsed = _as_date(row_date) if row_date is not None else None
            if parsed is None:
                raise ValueError("Bullflow row lacks a valid dated trade timestamp")
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


def validate_market_bars(bars, *, ticker, source_id, start, end, source_as_of=None,
                         as_of_date=None):
    """Validate normalized completed daily bars; caller preserves raw source response."""
    if not isinstance(bars, list) or not bars or not source_id:
        raise ValueError("Market bars and source provenance are required")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    ceiling = date.fromisoformat(as_of_date) if as_of_date else last
    normalized, seen = [], set()
    for bar in bars:
        if not isinstance(bar, dict) or bar.get("completed") is not True:
            raise ValueError("Only completed bars may enter daily market analysis")
        day = _as_date(bar.get("date"))
        close = bar.get("close")
        if day is None or not first <= day <= last or day > ceiling:
            raise ValueError("Bar date is missing or outside the requested/as-of range")
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
        "as_of": source_as_of or normalized[-1][1].get("provider_timestamp"),
        "bars": [row for _, row in normalized],
    }


def select_market_bars(
    schwab_bars, alpaca_bars, *, ticker, start, end,
    schwab_source="Schwab Cloudflare Web",
    alpaca_source="Alpaca IEX",
    schwab_as_of=None,
    alpaca_as_of=None,
    as_of_date=None,
):
    """Schwab is primary; use Alpaca only when Schwab data fails validation."""
    try:
        chosen = validate_market_bars(
            schwab_bars, ticker=ticker, source_id=schwab_source,
            start=start, end=end, source_as_of=schwab_as_of,
            as_of_date=as_of_date,
        )
        chosen["fallback_used"] = False
        return chosen
    except (TypeError, ValueError, KeyError) as schwab_error:
        try:
            chosen = validate_market_bars(
                alpaca_bars, ticker=ticker, source_id=alpaca_source,
                start=start, end=end, source_as_of=alpaca_as_of,
                as_of_date=as_of_date,
            )
            chosen["fallback_used"] = True
            chosen["fallback_reason"] = str(schwab_error)
            return chosen
        except (TypeError, ValueError, KeyError) as alpaca_error:
            raise ValueError(
                "No valid price history: Schwab primary failed "
                f"({schwab_error}); Alpaca fallback failed ({alpaca_error})"
            ) from alpaca_error



def validate_intraday_bars(
    bars, *, ticker, source_id, start, end, source_as_of=None,
):
    """Validate completed 15-minute bars without filling missing intervals."""
    if not isinstance(bars, list) or not bars or not source_id:
        raise ValueError("Completed intraday bars and source provenance are required")
    if not isinstance(source_as_of, str):
        raise ValueError("Intraday history requires the source retrieval timestamp")
    try:
        retrieved = datetime.fromisoformat(source_as_of.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Intraday source timestamp is invalid") from exc
    if retrieved.tzinfo is None:
        raise ValueError("Intraday source timestamp must be timezone-aware")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    parsed, seen = [], set()
    for bar in bars:
        if not isinstance(bar, dict):
            raise ValueError("Intraday bar must be an object")
        stamp = bar.get("timestamp", bar.get("datetime"))
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
            seconds = stamp / 1000 if stamp > 100000000000 else stamp
            dt = datetime.fromtimestamp(seconds, tz=ZoneInfo("UTC"))
        elif isinstance(stamp, str):
            try:
                dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Intraday timestamp is invalid") from exc
            if dt.tzinfo is None:
                raise ValueError("Intraday timestamp must be timezone-aware")
        else:
            raise ValueError("Intraday timestamp is required")
        day = dt.astimezone(ET).date()
        if not first <= day <= last or day > retrieved.astimezone(ET).date():
            raise ValueError("Intraday bar date is outside the requested/as-of window")
        if bar.get("completed", bar.get("complete")) is not True:
            raise ValueError("Incomplete 15-minute bars cannot be used")
        key = dt.isoformat()
        if key in seen:
            raise ValueError("Duplicate 15-minute bar timestamp")
        seen.add(key)
        parsed.append((dt, dict(bar)))
    parsed.sort(key=lambda row: row[0])
    if any(a[0] >= b[0] for a, b in zip(parsed, parsed[1:])):
        raise ValueError("Intraday bars are not strictly chronological")
    gaps = sum(
        1 for (a, _), (b, _) in zip(parsed, parsed[1:])
        if (b - a).total_seconds() > 15 * 60
    )
    return {
        "ticker": ticker.upper(),
        "source_id": source_id,
        "as_of": source_as_of,
        "start": parsed[0][0].astimezone(ET).isoformat(),
        "end": parsed[-1][0].astimezone(ET).isoformat(),
        "bar_count": len(parsed),
        "gap_count": gaps,
        "bars": [bar for _, bar in parsed],
    }


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
    provider_day = _as_date(underlying.get("provider_quote_timestamp"))
    if snapshot_day is None or snapshot_day > target:
        raise ValueError("Schwab chain is missing an as-of time or postdates the requested session")
    stale_snapshot = snapshot_day < target or (provider_day is not None and provider_day < target)
    quote_age = underlying.get("quote_age_seconds")
    if isinstance(quote_age, (int, float)) and quote_age > 900:
        stale_snapshot = True
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
        "status": "VERIFIED" if usable and not stale_snapshot else "PARTIAL",
        "source": obj.get("source", "Schwab Market Data API"),
        "ticker": ticker.upper(),
        "as_of": stamp,
        "snapshot_session_date": snapshot_day.isoformat(),
        "stale_snapshot": stale_snapshot,
        "contract_count": len(contracts),
        "contracts_with_oi": oi_rows,
        "contracts_usable_for_quote_iv": usable,
        "stale_contracts": stale,
        "realtime_delayed": underlying.get("realtime_delayed", "unknown"),
        "limitations": [
            "OI snapshot is not opening/closing intent or an OI change.",
            "Contract quote/IV usability is filtered independently from OI counts.",
            *(["Schwab snapshot predates the requested research date; freshness is reduced"] if stale_snapshot else []),
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
    if str(request.get("ticker", "")).upper() != ticker.upper():
        raise ValueError("Dated-series request ticker missing or mismatched")
    if request.get("from") != start or request.get("to") != end:
        raise ValueError("Dated-series request window missing or mismatched")
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
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    seen_points = set()
    ordered = []
    for point in series:
        if not isinstance(point, dict):
            raise ValueError("Dated-series point is not an object")
        stamp = point.get("timestamp", point.get("date", point.get("tradingDate")))
        if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
            stamp_seconds = stamp / 1000 if stamp > 100000000000 else stamp
            dt = datetime.fromtimestamp(stamp_seconds, tz=ZoneInfo("UTC"))
            observed_day = dt.astimezone(ET).date()
        else:
            observed_day = _as_date(stamp)
            dt = datetime.combine(observed_day, datetime.min.time(), tzinfo=ET) if observed_day else None
        if observed_day is None or not first <= observed_day <= last:
            raise ValueError("Dated-series point is missing a valid in-window timestamp")
        identity = dt.isoformat()
        if identity in seen_points:
            raise ValueError("Dated-series contains duplicate timestamps")
        seen_points.add(identity)
        ordered.append((dt, point))
    ordered.sort(key=lambda pair: pair[0])
    return {
        "status": "VERIFIED",
        "ticker": ticker.upper(),
        "from": start,
        "to": end,
        "row_count": len(ordered),
        "as_of": data.get("asOf", data.get("as_of")),
        "request": request,
        "metadata": {key: value for key, value in data.items()
                     if key not in ("points", "series", "rows", "data")},
        "rows": [point for _, point in ordered],
    }
