"""Point-in-time fundamental metrics from explicit filing-period observations.

This is a PARTIAL diagnostic, not a numeric SES direction. Sources must provide
period-matched audited or filed records; stale/incomplete data never promote.
"""
from datetime import date
from math import isfinite


def analyze_fundamentals(latest, prior, *, filing_url, filing_date):
    out = {"status": "UNAVAILABLE", "metrics": {}, "direction": None,
           "limitations": ["Insufficient period-matched filed evidence"]}
    if not isinstance(latest, dict) or not isinstance(prior, dict):
        return out
    if not isinstance(filing_url, str) or not filing_url.startswith("https://"):
        return out
    try:
        published = date.fromisoformat(filing_date)
        current_period = date.fromisoformat(latest["period_end"])
        prior_period = date.fromisoformat(prior["period_end"])
        keys = ("revenue", "operating_income", "operating_cash_flow", "capital_expenditures")
        if published < current_period or current_period <= prior_period:
            return out
        values = [latest[k] for k in keys] + [prior[k] for k in keys]
        if any(isinstance(v, bool) or not isinstance(v, (float, int))
               or not isfinite(v) for v in values):
            return out
        if latest["revenue"] <= 0 or prior["revenue"] <= 0:
            return out
        if latest.get("currency") != prior.get("currency"):
            return out
        if latest.get("period_type") != prior.get("period_type"):
            return out
        if latest.get("fiscal_period") != prior.get("fiscal_period"):
            return out
        if not latest.get("fiscal_period"):
            return out
        revenue_growth = latest["revenue"] / prior["revenue"] - 1
        margin = latest["operating_income"] / latest["revenue"]
        prior_margin = prior["operating_income"] / prior["revenue"]
        current_fcf = latest["operating_cash_flow"] - latest["capital_expenditures"]
        prior_fcf = prior["operating_cash_flow"] - prior["capital_expenditures"]
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return out
    return {
        "status": "PARTIAL", "direction": None,
        "as_of": filing_date, "sources": [filing_url],
        "metrics": {
            "revenue_yoy_growth": round(revenue_growth, 6),
            "operating_margin": round(margin, 6),
            "operating_margin_change": round(margin - prior_margin, 6),
            "free_cash_flow": current_fcf,
            "prior_free_cash_flow": prior_fcf,
            "currency": latest["currency"],
        },
        "limitations": ["No validated forward valuation or balance sheet",
                        "Historical growth does not establish investment direction",
                        "Not a certified SES fundamental score"],
    }
