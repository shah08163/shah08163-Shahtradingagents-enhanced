from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bear_researcher(llm):
    def bear_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bear_history = investment_debate_state.get("bear_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bull analyst"
        )
        market_research_report = report_or_absent(state.get("market_report", ""), "market")
        sentiment_report = report_or_absent(state.get("sentiment_report", ""), "sentiment")
        news_report = report_or_absent(state.get("news_report", ""), "news")
        fundamentals_report = report_or_absent(state.get("fundamentals_report", ""), "fundamentals")
        flow_report = report_or_absent(state.get("flow_report", ""), "Bullflow flow")
        oi_report = report_or_absent(state.get("oi_report", ""), "open interest")
        instrument_context = get_instrument_context_from_state(state)
        asset_type = state.get("asset_type", "stock")
        target_label = "stock" if asset_type == "stock" else "asset"
        fundamentals_label = (
            "Company fundamentals report"
            if asset_type == "stock"
            else "Asset fundamentals report (may be unavailable for crypto)"
        )

        prompt = f"""You are a Bear Analyst making the case against investing in the {target_label}. Your goal is to present a well-reasoned argument emphasizing risks, challenges, negative indicators, and bearish institutional options positioning where available.

Key points to focus on:
- Risks and Challenges: Highlight financial, competitive, macro, and execution risks.
- Negative Indicators: Use financial data, technicals, news, and sentiment where supported.
- Options Positioning: Use Bullflow directional flow and OI/fresh-positioning evidence when supplied. Do not treat MULTI trades as directional without leg evidence, and do not claim Bullflow represents complete market-wide volume or OI.
- Bull Counterpoints: Critically analyze the bull argument with specific data and sound reasoning.

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Bullflow institutional options-flow report: {flow_report}
Bullflow OI / fresh-positioning report: {oi_report}
Conversation history of the debate: {history}
Last bull argument: {current_response}
Use this information to deliver a compelling bear argument. Explicitly discuss whether options positioning confirms or contradicts the fundamental/technical bear thesis when those reports are available.
""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Bear Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bear_history": bear_history + "\n" + argument,
            "bull_history": investment_debate_state.get("bull_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bear_node
