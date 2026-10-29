# Phase 2 correction: reuse the existing TradingAgents execution engine

The authoritative implementation is the existing GitHub TradingAgents code, not a parallel ChatGPT-built scoring engine.

## Verified entry points on main
- `tradingagents/graph/trading_graph.py`: `TradingAgentsGraph`.
- `tradingagents/graph/setup.py`: existing graph construction and routing.
- `tradingagents/graph/analyst_execution.py`: currently registers market, social, news and fundamentals.
- `tradingagents/agents/analysts/market_analyst.py`: uses existing stock, indicator, verified-snapshot tools.
- `tradingagents/agents/analysts/sentiment_analyst.py`: existing sentiment report workflow.
- `tradingagents/agents/analysts/news_analyst.py`: existing news/macro tools.
- `tradingagents/agents/analysts/fundamentals_analyst.py`: existing financial-statement tools.

## Implementation decision
1. Keep original analyst prompts, reasoning, orchestration and risk process.
2. Build a thin ChatGPT-to-TradingAgents handoff and read-only tool-data adapters. Do not duplicate the analysts.
3. Preserve current connected Schwab Cloudflare Web, Bullflow and Alpaca access without new infrastructure.
4. Find the pre-existing enhanced flow, OI and dealer components and their execution contracts before registering any additional nodes. Do not claim seven live graph analysts currently exist.
5. Experimental `scripts/chatgpt_*_signal.py` prototypes are research fixtures only and must not replace any existing TradingAgents algorithm or be promoted to production.
6. Run integration and parity checks against the actual existing analyst outputs, then require CI and human approval before merging/deploying.
7. Fail closed where the existing graph cannot be invoked or required data is unavailable. No automatic trade execution.

## Open blocker
Calling a Python/LangGraph graph housed in GitHub from ChatGPT requires an actual execution mechanism. GitHub storage access by itself does not execute its source files. Design a read-only ChatGPT-native orchestration path that uses the existing implementation without creating a new hosted service; test feasibility before claiming end-to-end execution.
