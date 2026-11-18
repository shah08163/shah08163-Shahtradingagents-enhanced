"""Dated, provenance-preserving mapping of ChatGPT connector evidence.

This module does not call a network or infer an analyst direction. It unwraps
ChatGPT tool envelopes, validates date windows/pagination, and emits evidence
metadata for the native analyst adapters and SES scorer.
"""
from datetime import date

from scripts.chatgpt_source_contract import (
    select_market_bars,
    unwrap_tool_result,
    validate_bullflow_pages,
    validate_gex_history,
    validate_intraday_bars,
    validate_range_response,
    validate_schwab_chain,
)


def _mapping(payload):
    return unwrap_tool_result(payload)


def _source(source_id, provider, dataset, as_of, *, share=1.0,
            evidence_ids=(), dependence_group=None):
    return {
        "source_id": source_id,
        "provider": provider,
        "dataset": dataset,
        "as_of": as_of,
        "weight_share": share,
        "evidence_ids": sorted({str(x) for x in evidence_ids if x not in (None, "")}),
        "dependence_group": dependence_group,
    }


def _finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and value == value and abs(value) != float("inf"))


def _premium_persistence(rows):
    """Summarize observed cumulative call/put series without assigning intent."""
    points = [
        row for row in rows
        if isinstance(row, dict)
        and _finite_number(row.get("callsNetPremium"))
        and _finite_number(row.get("putsNetPremium"))
    ]
    if len(points) < 2:
        return {"status": "UNAVAILABLE", "reason": "fewer than two valid premium points"}
    result = {"status": "PARTIAL", "points": len(points)}
    for key, label in (("callsNetPremium", "calls"), ("putsNetPremium", "puts")):
        values = [float(row[key]) for row in points]
        deltas = [b - a for a, b in zip(values, values[1:])]
        nonzero = [1 if delta > 0 else -1 for delta in deltas if delta != 0]
        result[label] = {
            "first_value_usd": values[0],
            "last_value_usd": values[-1],
            "change_usd": values[-1] - values[0],
            "directional_persistence_fraction": (
                max(nonzero.count(1), nonzero.count(-1)) / len(nonzero)
                if nonzero else None
            ),
            "nonzero_intervals": len(nonzero),
        }
    result["interpretation_limit"] = (
        "Call and put series are reported separately; persistence is descriptive, "
        "not proof of opening intent or a directional recommendation"
    )
    return result


def _darkpool_summary(rows):
    valid = [row for row in rows if isinstance(row, dict)]
    notionals = [float(row["notional"]) for row in valid if _finite_number(row.get("notional"))]
    sizes = [float(row["size"]) for row in valid if _finite_number(row.get("size"))]
    return {
        "status": "PARTIAL",
        "dated_print_count": len(valid),
        "reported_notional_usd": sum(notionals) if notionals else None,
        "reported_share_size": sum(sizes) if sizes else None,
        "prints_with_notional": len(notionals),
        "prints_with_size": len(sizes),
        "interpretation_limit": "Non-directional price/size/notional context; no buyer/seller intent is established",
    }


def _gex_history_summary(snapshots):
    series = []
    for snapshot in snapshots:
        rows = snapshot.get("strikes", [])
        values = [float(row["net_gex"]) for row in rows
                  if isinstance(row, dict) and _finite_number(row.get("net_gex"))]
        if not values:
            continue
        series.append({
            "date": snapshot["date"],
            "net_gex_usd_per_1pct": sum(values),
            "strike_count": len(values),
            "spot_price": snapshot.get("spot_price"),
        })
    if not series:
        return {"status": "UNAVAILABLE", "reason": "no valid dated net GEX rows"}
    result = {"status": "PARTIAL", "observations": series}
    if len(series) >= 2:
        first, last = series[0], series[-1]
        result["window_change"] = {
            "from_date": first["date"],
            "to_date": last["date"],
            "net_gex_change_usd_per_1pct": (
                last["net_gex_usd_per_1pct"] - first["net_gex_usd_per_1pct"]
            ),
            "elapsed_calendar_days": (
                date.fromisoformat(last["date"]) - date.fromisoformat(first["date"])
            ).days,
        }
        result["interpretation_limit"] = (
            "Dated model-derived exposure comparison; gaps are retained and values do not establish dealer inventory"
        )
    return result


def _response_parts(payload):
    obj = _mapping(payload)
    return obj, obj.get("data", obj)


def _bars(payload):
    if payload is None:
        return None
    obj, data = _response_parts(payload)
    for key in ("bars", "candles", "data"):
        value = data.get(key) if isinstance(data, dict) else None
        if isinstance(value, list):
            return value
    return data if isinstance(data, list) else None


def _source_as_of(payload):
    if payload is None:
        return None
    obj, data = _response_parts(payload)
    for key in ("as_of", "asOf", "retrieved_at_utc", "retrieval_timestamp", "source_timestamp"):
        value = obj.get(key) if isinstance(obj, dict) else None
        if value:
            return value
        value = data.get(key) if isinstance(data, dict) else None
        if value:
            return value
    bars = data.get("bars", data.get("candles", [])) if isinstance(data, dict) else []
    if isinstance(bars, list) and bars:
        return bars[-1].get("provider_timestamp")
    return None


def map_connector_data(
    schwab_quote=None,
    bullflow_profile=None,
    schwab_explorer=None,
    bullflow_gex=None,
    *,
    ticker=None,
    trade_date=None,
    start=None,
    end=None,
    schwab_bars=None,
    schwab_intraday_bars=None,
    intraday_start=None,
    intraday_end=None,
    alpaca_bars=None,
    bullflow_flow_pages=None,
    bullflow_oi_pages=None,
    bullflow_premium_series=None,
    bullflow_darkpool_pages=None,
    bullflow_gex_history=None,
    bullflow_vex=None,
):
    """Return seven-role evidence metadata plus directionless supplemental context."""
    evidence = {}
    ticker = ticker.upper().strip() if isinstance(ticker, str) else None

    if schwab_bars is not None or alpaca_bars is not None:
        if not (ticker and start and end):
            evidence["market"] = {
                "status": "UNAVAILABLE", "as_of": None, "sources": [], "evidence": [],
                "limitations": ["Ticker and exact bar window are required for source selection"],
            }
        else:
            try:
                selected = select_market_bars(
                    _bars(schwab_bars), _bars(alpaca_bars),
                    ticker=ticker, start=start, end=end,
                    schwab_as_of=_source_as_of(schwab_bars),
                    alpaca_as_of=_source_as_of(alpaca_bars),
                )
                evidence["market"] = {
                    "status": "PARTIAL",
                    "as_of": selected["as_of"],
                    "sources": [selected["source_id"]],
                    "source_provenance": [_source(
                        selected["source_id"], selected["source_id"], "equity_daily_bars",
                        selected["as_of"], share=1.0,
                    )],
                    "evidence": [
                        f"completed_daily_bars={selected['bar_count']}",
                        f"validated_window={selected['start']}..{selected['end']}",
                    ],
                    "observation_end": selected["end"],
                    "limitations": (
                        ["Schwab failed validation; Alpaca IEX fallback used: "
                         + selected.get("fallback_reason", "Schwab data unavailable")]
                        if selected["fallback_used"] else
                        ["Price history is validated; analyst interpretation remains separate"]
                    ),
                }
            except ValueError as exc:
                evidence["market"] = {
                    "status": "UNAVAILABLE", "as_of": None, "sources": [], "evidence": [],
                    "limitations": [str(exc)],
                }

    if schwab_quote is not None and "market" not in evidence:
        quote, data = _response_parts(schwab_quote)
        symbol = quote.get("symbol") or data.get("symbol")
        stamp = quote.get("retrieved_at_utc") or data.get("retrieved_at_utc")
        if symbol and stamp and isinstance(data, dict) and isinstance(data.get("quote"), dict):
            regular = data.get("quote", {})
            extended = data.get("extended", {})
            evidence["market"] = {
                "status": "PARTIAL", "as_of": stamp,
                "sources": ["Schwab Cloudflare Web quote " + symbol],
                "source_provenance": [_source(
                    f"schwab:quote:{symbol}:{stamp}", "Schwab", "equity_quote", stamp,
                )],
                "evidence": [
                    "previous_close_price=" + str(regular.get("closePrice")),
                    "extended_last_price=" + str(extended.get("lastPrice")),
                ],
                "limitations": [
                    "Previous close and extended prices are distinct sessions; price history is required for technical analysis"
                ],
            }

    if schwab_intraday_bars is not None:
        day_start = intraday_start or trade_date
        day_end = intraday_end or trade_date
        try:
            if not (ticker and day_start and day_end):
                raise ValueError("Ticker and exact intraday date window are required")
            intraday = validate_intraday_bars(
                _bars(schwab_intraday_bars), ticker=ticker,
                source_id="Schwab Cloudflare Web 15Min",
                start=day_start, end=day_end,
                source_as_of=_source_as_of(schwab_intraday_bars),
            )
            record = evidence.setdefault("market", {
                "status": "PARTIAL", "as_of": intraday["as_of"],
                "sources": [], "source_provenance": [], "evidence": [],
                "limitations": [],
            })
            if record.get("source_provenance"):
                record["source_provenance"][0]["weight_share"] = 0.80
            record["sources"].append(intraday["source_id"])
            record["source_provenance"].append(_source(
                f"schwab:15min:{ticker}:{day_start}:{day_end}",
                "Schwab", "equity_intraday_15min", intraday["as_of"], share=0.20,
            ))
            record["evidence"].append(
                f"completed_15min_bars={intraday['bar_count']}; "
                f"gaps_over_15m={intraday['gap_count']}; "
                f"window={intraday['start']}..{intraday['end']}"
            )
            record["context_sources"] = {"schwab_15min_bars": intraday}
            record.setdefault("limitations", []).append(
                "Intraday bars are a market-context checkpoint; missing intervals are not filled"
            )
        except (TypeError, ValueError, KeyError) as exc:
            record = evidence.setdefault("market", {
                "status": "PARTIAL", "as_of": None, "sources": [],
                "source_provenance": [], "evidence": [], "limitations": [],
            })
            record["limitations"].append("Schwab 15-minute history unavailable: " + str(exc))

    prof = _mapping(bullflow_profile) if bullflow_profile is not None else None
    prof_data = prof.get("data", prof) if isinstance(prof, dict) else {}
    if isinstance(prof_data, dict) and prof_data.get("tradingDate") and prof_data.get("asOf"):
        session = prof_data["tradingDate"]
        premium = prof_data.get("premium", {})
        activity = prof_data.get("activity", {})
        evidence["flow"] = {
            "status": "PARTIAL", "as_of": prof_data["asOf"],
            "sources": [f"Bullflow optionsProfile session {session}"],
            "source_provenance": [_source(
                f"bullflow:optionsProfile:{ticker or prof_data.get('symbol')}:{session}",
                "Bullflow", "options_profile", prof_data["asOf"],
                share=0.25,
                dependence_group=f"bullflow-flow-session:{ticker or prof_data.get('symbol')}:{session}",
            )],
            "evidence": [
                "recorded_option_volume=" + str(activity.get("totalVolume")),
                "directional_premium=" + str(premium.get("netDirectionalPremium")),
            ],
            "limitations": [
                "Recorded-feed aggregates do not alone establish opening intent or directional trade intent"
            ],
        }
        unusual = prof_data.get("unusualContracts")
        if unusual:
            oi_record = evidence.setdefault("oi", {
                "status": "PARTIAL", "as_of": prof_data["asOf"],
                "sources": [], "source_provenance": [], "evidence": [],
                "limitations": [],
            })
            oi_src = f"bullflow:optionsProfile:oi-context:{ticker or prof_data.get('symbol')}:{session}"
            oi_record["sources"].append(oi_src)
            oi_record["source_provenance"].append(_source(
                oi_src, "Bullflow", "options_profile_oi_context", prof_data["asOf"],
                share=0.20,
                dependence_group=f"bullflow-oi-context:{ticker or prof_data.get('symbol')}:{session}",
            ))
            oi_record["evidence"].append(
                "unusual_contract_oi_context_count=" + str(len(unusual))
            )
            oi_record["limitations"].append(
                "Bullflow profile OI ratios are a recorded-contract sample, not full-chain OI"
            )

    if bullflow_flow_pages is not None:
        if not (ticker and trade_date):
            page_summary = None
            page_error = "Ticker and exact trading date are required for flow-page validation"
        else:
            try:
                page_summary = validate_bullflow_pages(
                    bullflow_flow_pages, ticker=ticker, date_value=trade_date,
                )
                page_error = None
            except (TypeError, ValueError, KeyError) as exc:
                page_summary, page_error = None, str(exc)
        if page_summary:
            record = evidence.setdefault("flow", {
                "status": "PARTIAL", "as_of": page_summary["as_of"],
                "sources": [], "source_provenance": [], "evidence": [], "limitations": [],
            })
            event_ids = [
                row.get("event_id", row.get("eventId", row.get("trade_id", row.get("tradeId", row.get("id")))))
                for row in page_summary["rows"]
            ]
            src = f"bullflow:historicalOptionsFlow:{ticker}:{trade_date}"
            record["sources"].append(src)
            record["source_provenance"].append(_source(
                src, "Bullflow", "historical_options_flow", page_summary["as_of"],
                share=0.50, evidence_ids=event_ids,
                dependence_group=f"bullflow-flow-session:{ticker}:{trade_date}",
            ))
            record["evidence"].append(
                f"complete_historical_flow_pages={page_summary['page_count']}; "
                f"unique_rows={page_summary['row_count']}; "
                f"duplicates_removed={page_summary['duplicate_rows_removed']}"
            )
            record["limitations"].append(
                "Ask/bid execution side is not proof of opening, closing, or trader intent"
            )
            record["observation_end"] = trade_date
            record["pagination_complete"] = True
        else:
            evidence.setdefault("flow", {
                "status": "PARTIAL", "as_of": None, "sources": [],
                "source_provenance": [], "evidence": [], "limitations": [],
            })["limitations"].append("Historical-flow pagination/date validation failed: " + page_error)
            evidence["flow"]["pagination_complete"] = False

    if bullflow_premium_series is not None:
        if not (ticker and start and end):
            series_error = "Ticker and exact premium-series window are required"
            series = None
        else:
            try:
                series = validate_range_response(
                    bullflow_premium_series, ticker=ticker, start=start, end=end,
                    data_keys=("series", "rows", "data"),
                )
                series_error = None
            except (TypeError, ValueError, KeyError) as exc:
                series, series_error = None, str(exc)
        if series:
            record = evidence.setdefault("flow", {
                "status": "PARTIAL", "as_of": series["as_of"], "sources": [],
                "source_provenance": [], "evidence": [], "limitations": [],
            })
            src = f"bullflow:netPremiumSeries:{ticker}:{start}:{end}"
            record["sources"].append(src)
            record["source_provenance"].append(_source(
                src, "Bullflow", "net_premium_series", series["as_of"],
                share=0.25,
                dependence_group=f"bullflow-premium-series:{ticker}:{start}:{end}",
            ))
            record["evidence"].append(
                f"net_premium_series_rows={series['row_count']} "
                f"window={series['from']}..{series['to']}"
            )
            record.setdefault("features", {})["net_premium_persistence"] = _premium_persistence(series["rows"])
            record["observation_end"] = end
        else:
            evidence.setdefault("flow", {
                "status": "PARTIAL", "as_of": None, "sources": [],
                "source_provenance": [], "evidence": [], "limitations": [],
            })["limitations"].append("Premium-series window validation failed: " + series_error)

    if bullflow_darkpool_pages is not None:
        if not (ticker and start and end):
            dark = None
            dark_error = "Ticker and exact dark-pool window are required"
        else:
            try:
                dark = validate_bullflow_pages(
                    bullflow_darkpool_pages, ticker=ticker, start=start, end=end,
                )
                dark_error = None
            except (TypeError, ValueError, KeyError) as exc:
                dark, dark_error = None, str(exc)
        supplemental = evidence.setdefault("supplemental", {})
        if dark:
            supplemental["dark_pool_context"] = {
                "status": "PARTIAL",
                "source": f"Bullflow darkPoolTrades {ticker} {start}..{end}",
                "as_of": dark["as_of"],
                "rows": dark["row_count"],
                "pages": dark["page_count"],
                "pagination_complete": True,
                "observation_end": end,
                "features": _darkpool_summary(dark["rows"]),
                "limitations": [
                    "Prints provide price/size/notional context only; no buyer/seller side is established"
                ],
            }
        else:
            supplemental["dark_pool_context"] = {
                "status": "UNAVAILABLE", "limitations": [dark_error],
            }

    if schwab_explorer is not None:
        try:
            if not (ticker and trade_date):
                raise ValueError("Ticker and trade date required for Schwab chain validation")
            chain = validate_schwab_chain(
                schwab_explorer, ticker=ticker, trade_date=trade_date, max_dte=60,
            )
            oi_record = evidence.setdefault("oi", {
                "status": chain["status"], "as_of": chain["as_of"],
                "sources": [], "source_provenance": [], "evidence": [],
                "limitations": [],
            })
            oi_record["status"] = "PARTIAL"
            oi_record["as_of"] = chain["as_of"]
            oi_record["sources"].append(chain["source"])
            oi_record["source_provenance"].append(_source(
                f"schwab:options-chain:{ticker}:{chain['as_of']}",
                "Schwab", "full_strike_options_chain", chain["as_of"],
                share=0.65,
            ))
            oi_record["evidence"].extend([
                f"contracts_returned={chain['contract_count']}",
                f"contracts_with_oi={chain['contracts_with_oi']}",
                f"contracts_quote_iv_usable={chain['contracts_usable_for_quote_iv']}",
                f"quote_freshness={chain['realtime_delayed']}",
            ])
            oi_record["limitations"].extend(chain["limitations"])
        except (TypeError, ValueError, KeyError) as exc:
            oi_record = evidence.setdefault("oi", {
                "status": "UNAVAILABLE", "as_of": None, "sources": [],
                "source_provenance": [], "evidence": [], "limitations": [],
            })
            if oi_record["sources"]:
                oi_record["status"] = "PARTIAL"
            oi_record["limitations"].append("Schwab chain unavailable: " + str(exc))


    if bullflow_oi_pages is not None:
        if not (ticker and trade_date):
            oi_pages, oi_error = None, "Ticker and exact trading date are required for OI flow-context validation"
        else:
            try:
                oi_pages = validate_bullflow_pages(
                    bullflow_oi_pages, ticker=ticker, date_value=trade_date,
                )
                oi_error = None
            except (TypeError, ValueError, KeyError) as exc:
                oi_pages, oi_error = None, str(exc)
        record = evidence.setdefault("oi", {
            "status": "PARTIAL", "as_of": None, "sources": [],
            "source_provenance": [], "evidence": [], "limitations": [],
        })
        if oi_pages:
            event_ids = [
                row.get("event_id", row.get("eventId", row.get("trade_id", row.get("tradeId", row.get("id")))))
                for row in oi_pages["rows"]
            ]
            src = f"bullflow:historicalOptionsFlow:oi-context:{ticker}:{trade_date}"
            record["sources"].append(src)
            record.setdefault("source_provenance", []).append(_source(
                src, "Bullflow", "recorded_flow_oi_context", oi_pages["as_of"],
                share=0.15, evidence_ids=event_ids,
                dependence_group=f"bullflow-flow-session:{ticker}:{trade_date}",
            ))
            record.setdefault("evidence", []).append(
                f"complete_oi_context_pages={oi_pages['page_count']}; "
                f"unique_rows={oi_pages['row_count']}"
            )
            record.setdefault("limitations", []).append(
                "Recorded trade OI context is not a full chain or proof of opening intent"
            )
        else:
            record.setdefault("limitations", []).append(
                "Bullflow OI-context validation failed: " + oi_error
            )

    if bullflow_gex is not None:
        obj, data = _response_parts(bullflow_gex)
        if isinstance(data, dict) and data.get("ticker") and isinstance(data.get("strikes"), list):
            stamp = data.get("as_of")
            evidence["dealer"] = {
                "status": "PARTIAL", "as_of": stamp,
                "sources": [f"Bullflow modeled net GEX {data['ticker']}"],
                "source_provenance": [_source(
                    f"bullflow:netgex:{data['ticker']}:{stamp}", "Bullflow", "net_gex", stamp,
                    dependence_group=data.get("snapshot_id"),
                )],
                "evidence": [
                    "modeled_strike_count=" + str(len(data["strikes"])),
                    "spot_price=" + str(data.get("spot_price")),
                ],
                "limitations": [
                    "GEX is modeled exposure, not verified dealer inventory",
                    "Snapshot is current-only unless returned with an explicit historical session date",
                ],
            }

    if bullflow_vex is not None:
        _, data = _response_parts(bullflow_vex)
        if isinstance(data, dict) and data.get("ticker") and isinstance(data.get("strikes"), list):
            stamp = data.get("as_of")
            rec = evidence.setdefault("dealer", {
                "status": "PARTIAL", "as_of": stamp, "sources": [],
                "source_provenance": [], "evidence": [], "limitations": [],
            })
            src = f"bullflow:netvex:{data['ticker']}:{stamp}"
            rec["sources"].append(src)
            rec["source_provenance"].append(_source(
                src, "Bullflow", "net_vex", stamp, dependence_group=data.get("snapshot_id"),
            ))
            rec["evidence"].append("modeled_vex_strike_count=" + str(len(data["strikes"])))
            rec["limitations"].append("VEX and GEX spots/timestamps must be aligned before combining")

    if bullflow_gex_history is not None:
        if not (ticker and trade_date):
            history, history_error = None, "Ticker and trade date required for dated GEX history"
        else:
            try:
                history = validate_gex_history(
                    bullflow_gex_history, ticker=ticker, trade_date=trade_date,
                )
                history_error = None
            except (TypeError, ValueError, KeyError) as exc:
                history, history_error = None, str(exc)
        rec = evidence.setdefault("dealer", {
            "status": "PARTIAL", "as_of": None, "sources": [],
            "source_provenance": [], "evidence": [], "limitations": [],
        })
        if history:
            src = f"bullflow:eodGex:{ticker}:{history['first_date']}..{history['last_date']}"
            rec["sources"].append(src)
            rec["source_provenance"].append(_source(
                src, "Bullflow", "dated_eod_gex_history", history["as_of"],
                share=1.0,
                dependence_group=f"bullflow-eod-gex-history:{ticker}",
            ))
            rec["evidence"].append(
                f"dated_eod_gex_sessions={history['sessions']} "
                f"window={history['first_date']}..{history['last_date']}"
            )
            rec.setdefault("features", {})["historical_gex_changes"] = _gex_history_summary(history["snapshots"])
            rec["observation_end"] = history["last_date"]
            rec["limitations"].append(
                "Missing GEX dates remain gaps; no interpolation or current-to-historical substitution"
            )
        else:
            rec["limitations"].append("Dated GEX validation failed: " + history_error)

    return evidence
