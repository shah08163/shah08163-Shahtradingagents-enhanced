from tradingagents.agents.context import (
    get_instrument_context_from_state,
    get_language_instruction,
    opponent_argument_or_opening,
    report_or_absent,
)


def create_bull_researcher(llm):
    def bull_node(state) -> dict:
        investment_debate_state = state["investment_debate_state"]
        history = investment_debate_state.get("history", "")
        bull_history = investment_debate_state.get("bull_history", "")

        current_response = opponent_argument_or_opening(
            investment_debate_state.get("current_response", ""), "bear analyst"
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

        prompt = f"""You are a Bull Analyst advocating for investing in the {target_label}. Your task is to build a strong, evidence-based case emphasizing growth potential, competitive advantages, positive market indicators, and institutional options positioning where available. Leverage the provided research and data to address concerns and counter bearish arguments effectively.

Key points to focus on:
- Growth Potential: Highlight the company's market opportunities, revenue projections, and scalability.
- Competitive Advantages: Emphasize factors like unique products, strong branding, or dominant market positioning.
- Positive Indicators: Use financial health, industry trends, technicals, and recent positive news as evidence.
- Options Positioning: Use Bullflow directional flow and OI/fresh-positioning evidence when supplied. Do not treat MULTI trades as directional without leg evidence, and do not claim Bullflow represents complete market-wide volume or OI.
- Bear Counterpoints: Critically analyze the bear argument with specific data and sound reasoning.

Resources available:
{instrument_context}
Market research report: {market_research_report}
Social media sentiment report: {sentiment_report}
Latest world affairs news: {news_report}
{fundamentals_label}: {fundamentals_report}
Bullflow institutional options-flow report: {flow_report}
Bullflow OI / fresh-positioning report: {oi_report}
Conversation history of the debate: {history}
Last bear argument: {current_response}
Use this information to deliver a compelling bull argument. Explicitly discuss whether options positioning confirms or contradicts the fundamental/technical bull thesis when those reports are available.
""" + get_language_instruction()

        response = llm.invoke(prompt)

        argument = f"Bull Analyst: {response.content}"

        new_investment_debate_state = {
            "history": history + "\n" + argument,
            "bull_history": bull_history + "\n" + argument,
            "bear_history": investment_debate_state.get("bear_history", ""),
            "current_response": argument,
            "count": investment_debate_state["count"] + 1,
        }

        return {"investment_debate_state": new_investment_debate_state}

    return bull_node
