"""Bullflow open-interest / fresh-positioning analyst."""

from langchain_core.messages import AIMessage

from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.dataflows.vendors.bullflow import fetch_oi_bundle


def create_oi_analyst(llm):
    def oi_analyst_node(state):
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        data = fetch_oi_bundle(ticker, trade_date)

        prompt = f"""You are the Options Open Interest Analyst inside a multi-agent trading research system.
Analyze {ticker} as of {trade_date}, focusing on fresh positioning and OI structure from Bullflow's recorded-flow data.

{instrument_context}

Use only the supplied evidence. Bullflow's public API does NOT provide a complete option-chain OI snapshot here, so never claim full-chain call walls, put walls, max pain, or total market OI. Full-chain verification will be added through Schwab later.

{data}

Produce a decision-useful report with:
1. OI bias: Bullish / Mixed / Bearish / Insufficient.
2. Confidence: low / medium / high.
3. The strongest volume-to-OI anomalies and why they may represent fresh positioning.
4. Existing-position evidence where OI is already large relative to the new trade/volume.
5. Strike/expiration clusters visible in the supplied data.
6. Possible spread/roll/MULTI structures; do not assign directional bias to MULTI without evidence from the legs.
7. 0-7 DTE versus longer-dated positioning when visible.
8. A 'What we still need from Schwab' section listing full-chain OI checks that cannot be established from this Bullflow evidence.
9. An 'OI takeaway' stating whether the available positioning confirms, contradicts, or is neutral toward a bullish stock thesis.

Do not recommend a final trade. {get_language_instruction()}"""
        response = llm.invoke(prompt)
        text = response.content
        return {"messages": [AIMessage(content=text)], "oi_report": text}

    return oi_analyst_node
