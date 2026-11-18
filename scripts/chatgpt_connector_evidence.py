"""Dated, provenance-preserving mapping of ChatGPT connector evidence.

This module does not call a network or infer an analyst direction. It unwraps
ChatGPT tool envelopes, validates date windows/pagination, and emits evidence
metadata for the native analyst adapters and SES scorer.
"""
from scripts.chatgpt_source_contract import (
    select_market_bars,
    unwrap_tool_result,
    validate_bullflow_pages,
    validate_gex_history,
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
                )
                evidence["market"] = {
                    "status": "PARTIAL",
                    "as_of": selected["end"],
                    "sources": [selected["source_id"]],
                    "source_provenance": [_source(
                        selected["source_id"], selected["source_id"], "equity_daily_bars",
                        selected["end"], share=1.0,
                    )],
                    "evidence": [
                        f"completed_daily_bars={selected['bar_count']}",
                        f"validated_window={selected['start']}..{selected['end']}",
                    ],
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
        else:
            evidence.setdefault("flow", {
                "status": "PARTIAL", "as_of": None, "sources": [],
                "source_provenance": [], "evidence": [], "limitations": [],
            })["limitations"].append("Historical-flow pagination/date validation failed: " + page_error)

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
            evidence["oi"] = {
                "status": chain["status"], "as_of": chain["as_of"],
                "sources": [chain["source"]],
                "source_provenance": [_source(
                    f"schwab:options-chain:{ticker}:{chain['as_of']}",
                    "Schwab", "full_strike_options_chain", chain["as_of"],
                    share=0.65,
                )],
                "evidence": [
                    f"contracts_returned={chain['contract_count']}",
                    f"contracts_with_oi={chain['contracts_with_oi']}",
                    f"contracts_quote_iv_usable={chain['contracts_usable_for_quote_iv']}",
                    f"quote_freshness={chain['realtime_delayed']}",
                ],
                "limitations": chain["limitations"],
            }
        except (TypeError, ValueError, KeyError) as exc:
            evidence["oi"] = {
                "status": "UNAVAILABLE", "as_of": None, "sources": [],
                "evidence": [], "limitations": [str(exc)],
            }


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
                share=0.35, evidence_ids=event_ids,
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
                src, "Bullflow", "dated_eod_gex_history", history["last_date"],
                dependence_group=f"bullflow-eod-gex-history:{ticker}",
            ))
            rec["evidence"].append(
                f"dated_eod_gex_sessions={history['sessions']} "
                f"window={history['first_date']}..{history['last_date']}"
            )
            rec["limitations"].append(
                "Missing GEX dates remain gaps; no interpolation or current-to-historical substitution"
            )
        else:
            rec["limitations"].append("Dated GEX validation failed: " + history_error)

    return evidence
