"""Deterministic, read-only mapping of existing connector JSON into analyst evidence.

This module deliberately produces PARTIAL inputs, not direction scores or a
certified seven-analyst report. Inputs are saved responses from ChatGPT's
existing Schwab and Bullflow connections. It performs no network calls.
"""

import json

def _mapping(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("Expected connector response object")
    # Some ChatGPT connector responses wrap JSON in a text string.
    if isinstance(payload.get("text"), str):
        return _mapping(payload["text"])
    return payload

def map_connector_data(schwab_quote=None, bullflow_profile=None, schwab_explorer=None, bullflow_gex=None):
    """Return evidence records; no claim of independent source corroboration."""
    evidence = {}
    if schwab_quote is not None:
        quote = _mapping(schwab_quote)
        data = quote.get("data", {})
        symbol = quote.get("symbol")
        stamp = quote.get("retrieved_at_utc")
        if symbol and stamp and isinstance(data, dict) and isinstance(data.get("quote"), dict):
            regular = data.get("quote", {})
            extended = data.get("extended", {})
            evidence["market"] = {
                "status": "PARTIAL", "as_of": stamp,
                "sources": ["Schwab Cloudflare Web quote " + symbol],
                "evidence": [
                    "previous_close_price=" + str(regular.get("closePrice")),
                    "extended_last_price=" + str(extended.get("lastPrice"))],
                "limitations": ["Previous close and extended prices are distinct sessions; further technical context required"]}
    if bullflow_profile is not None:
        prof = _mapping(bullflow_profile)
        obj = prof.get("data", {})
        date, stamp = obj.get("tradingDate"), obj.get("asOf")
        premium = obj.get("premium", {})
        activity = obj.get("activity", {})
        if date and stamp and isinstance(premium, dict) and isinstance(activity, dict):
            evidence["flow"] = {
                "status": "PARTIAL", "as_of": stamp,
                "sources": ["Bullflow optionsProfile session " + date],
                "evidence": [
                    "recorded_option_volume=" + str(activity.get("totalVolume")),
                    "directional_premium=" + str(premium.get("netDirectionalPremium"))],
                "limitations": ["Aggregates do not establish qualifying single-leg SWEEP/BLOCK directional evidence"]}
    if schwab_explorer is not None:
        chain = _mapping(schwab_explorer)
        if chain.get("symbol") and chain.get("contracts") is not None:
            evidence["oi"] = {
                "status": "PARTIAL", "as_of": chain.get("underlying", {}).get("retrieval_timestamp"),
                "sources": ["Schwab options explorer " + chain["symbol"]],
                "evidence": ["contracts_returned=" + str(len(chain["contracts"]))],
                "limitations": ["No independently confirmed OI changes or all-contract quote quality pass"]}
    if bullflow_gex is not None:
        gex = _mapping(bullflow_gex)
        data = gex.get("data", {})
        if data.get("ticker") and data.get("strikes") is not None:
            evidence["dealer"] = {
                "status": "PARTIAL", "as_of": data.get("as_of"),
                "sources": ["Bullflow modeled net GEX " + data["ticker"]],
                "evidence": ["modeled_strike_count=" + str(len(data["strikes"]))],
                "limitations": ["Modeled exposure does not determine actual dealer positioning"]}
    return evidence
