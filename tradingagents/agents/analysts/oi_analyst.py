"""Bullflow open-interest / fresh-positioning analyst."""

from langchain_core.messages import AIMessage

from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.dataflows.vendors.bullflow import fetch_oi_bundle
from tradingagents.dataflows.vendors.schwab_chain import fetch_chain_summary


def create_oi_analyst(llm):
    def oi_analyst_node(state):
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        data = fetch_oi_bundle(ticker, trade_date)
        schwab = fetch_chain_summary(ticker, trade_date)

        prompt = f"""You are the Options Open Interest Analyst inside a multi-agent trading research system.
Analyze {ticker} as of {trade_date}, focusing on Bullflow recorded flow plus Schwab full-chain OI and implied volatility when available.

{instrument_context}

Use only supplied evidence. Bullflow does NOT provide full-chain OI. When Schwab is available, distinguish snapshot OI concentrations from confirmed barriers; report near-ATM IV by expiration and side; only report put/call skew when matched-strike comparison status is observed, and never infer zero skew from identical vendor IV. The chain scope is 0-60 DTE. A current Schwab snapshot must not be applied to historical trade dates.

{data}

## Schwab full-chain OI / IV data
{schwab}

Produce a decision-useful report with:
1. OI bias: Bullish / Mixed / Bearish / Insufficient.
2. Confidence: low / medium / high.
3. The strongest volume-to-OI anomalies and why they may represent fresh positioning.
4. Existing-position evidence where OI is already large relative to the new trade/volume.
5. Strike/expiration clusters visible in the supplied data.
6. Possible spread/roll/MULTI structures; do not assign directional bias to MULTI without evidence from the legs.
7. 0-7 DTE versus longer-dated positioning when visible.
8. Full-chain OI concentrations and near-ATM IV term structure/skew only when Schwab data is available; otherwise state what Schwab checks are missing.
9. An 'OI takeaway' stating whether the available positioning confirms, contradicts, or is neutral toward a bullish stock thesis.

Do not recommend a final trade. {get_language_instruction()}"""
        response = llm.invoke(prompt)
        text = response.content
        return {"messages": [AIMessage(content=text)], "oi_report": text}

    return oi_analyst_node
