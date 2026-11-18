# Original analyst source: b3b1df5762f3f712fa7f07c4ecf8125bc727cdf9.
# Only data-fetch dependency injection adapted for existing ChatGPT connectors.
"""Bullflow GEX/VEX dealer-positioning analyst."""

from langchain_core.messages import AIMessage

from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction


def create_dealer_positioning_analyst(llm, *, fetch_dealer_positioning_bundle):
    def dealer_positioning_node(state):
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        data = fetch_dealer_positioning_bundle(ticker, trade_date)

        prompt = f"""You are the Dealer Positioning Analyst inside a multi-agent trading research system.
Analyze Bullflow GEX and VEX evidence for {ticker} as of {trade_date}.

{instrument_context}

Use only the supplied Bullflow evidence. Do not invent missing values, and do not claim GEX/VEX reveals verified dealer inventory. These are model-derived exposure estimates from option Greeks weighted by observed OI or volume.

{data}

Produce a concise, decision-useful report with:
1. Regime: Stabilizing / Destabilizing / Mixed / Indeterminate.
2. Confidence: low / medium / high, explicitly tied to freshness, coverage and agreement between OI-weighted and volume-weighted GEX.
3. OI-weighted GEX: total directional character and the most important positive/negative strike-expiration nodes.
4. Volume-weighted GEX: whether current-session positioning reinforces or diverges from OI-weighted structure.
5. VEX / vanna: largest positive/negative nodes and whether the vanna map adds directional or volatility sensitivity near spot.
6. Spot proximity: identify the most relevant nearby nodes and their approximate distance from spot when the data permits.
7. GEX alerts: incorporate proximity or node-movement alerts when present, including classification/severity, without over-weighting a single alert.
8. A clear 'Dealer-positioning takeaway' explaining whether the exposure map likely dampens moves, amplifies moves, creates pinning/magnet risk, or leaves the setup mixed.

Do not recommend a final trade. Later agents combine this with technicals, fundamentals, flow, OI, news and risk. {get_language_instruction()}"""
        response = llm.invoke(prompt)
        text = response.content
        return {"messages": [AIMessage(content=text)], "dealer_positioning_report": text}

    return dealer_positioning_node
