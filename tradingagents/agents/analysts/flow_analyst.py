# Original analyst source: b3b1df5762f3f712fa7f07c4ecf8125bc727cdf9.
# Only data-fetch dependency injection adapted for existing ChatGPT connectors.
"""Bullflow institutional options-flow analyst."""

from langchain_core.messages import AIMessage

from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction


def create_flow_analyst(llm, *, fetch_flow_bundle):
    def flow_analyst_node(state):
        ticker = state["company_of_interest"]
        trade_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        data = fetch_flow_bundle(ticker, trade_date)

        prompt = f"""You are the Bullflow Flow Analyst inside a multi-agent trading research system.
Analyze institutional-style recorded options activity for {ticker} as of {trade_date}.

{instrument_context}

Use only the Bullflow evidence below. Do not invent missing fields. Bullflow coverage is recorded flow, not complete exchange-wide options volume.

{data}

Produce a concise but decision-useful report with:
1. Directional bias: Strong Bullish / Bullish / Mixed / Bearish / Strong Bearish.
2. Confidence: low / medium / high, explicitly tied to coverage and data quality.
3. Call vs put volume and premium.
4. Ask-side vs bid-side pressure, emphasizing directional premium. Exclude MULTI trades from directional interpretation unless the supplied profile explicitly incorporates them directionally.
5. Sweeps, blocks, unusual/repeat flow, and short-dated concentration when present.
6. Fresh-positioning candidates where volume materially exceeds open interest. Distinguish fresh-positioning evidence from large existing OI.
7. The most important individual contracts/trades, with strike, expiry, side, premium and size when available.
8. A clear 'Flow takeaway' explaining whether Bullflow confirms, contradicts, or is neutral toward a bullish stock thesis.

Do not recommend a final trade; later agents combine this with technicals, fundamentals, OI, news and risk. {get_language_instruction()}"""
        response = llm.invoke(prompt)
        text = response.content
        return {"messages": [AIMessage(content=text)], "flow_report": text}

    return flow_analyst_node
