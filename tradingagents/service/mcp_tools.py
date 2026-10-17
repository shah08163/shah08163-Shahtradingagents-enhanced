"""Private ChatGPT MCP interface to the existing research engine.

Authentication is enforced by the parent FastAPI app before MCP traffic reaches
its ASGI mount. Never embed access tokens in plugin manifests.
"""
from mcp.server.fastmcp import FastMCP

from tradingagents.service.api import AnalyzeRequest, execute_analysis

mcp = FastMCP(
    "Shah TradingAgents",
    instructions="Run read-only stock research with Shah TradingAgents. Research does not execute trades.",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
)


@mcp.tool()
def run_trading_research(ticker: str, analysts: list[str] | None = None) -> dict:
    """Run stock/ETF research using selected analysts and return a bounded report.

    Available analysts: market, social, news, fundamentals, flow, oi, dealer.
    OI uses Schwab full-strike 0-60 DTE snapshot and Bullflow where available.
    Runs can take multiple minutes and may incur LLM usage costs.
    This tool never submits orders.
    """
    selected = analysts if analysts is not None else [
        "market", "social", "news", "fundamentals", "flow", "oi", "dealer"
    ]
    request = AnalyzeRequest(ticker=ticker, analysts=selected, save_reports=False,
                             checkpoint=False)
    result = execute_analysis(request)
    fields = (
        "market_report", "sentiment_report", "news_report", "fundamentals_report",
        "flow_report", "oi_report", "dealer_positioning_report", "evidence_report",
        "final_trade_decision",
    )
    return {
        "ticker": result.ticker, "date": result.trade_date, "signal": result.signal,
        "analysts": result.analysts,
        "reports": {field: str(result.final_state.get(field, ""))[:16000]
                    for field in fields if result.final_state.get(field)},
        "disclaimer": "Research only; no trades placed. Check source timestamps and quality.",
    }


@mcp.tool()
def get_tradingagents_status() -> dict:
    """Check whether the TradingAgents MCP integration is configured and which analysts are available."""
    from tradingagents.service.api import ANALYST_ORDER
    return {"status": "online", "analysts": ANALYST_ORDER,
            "oi_scope": "Full strikes, up to 60 calendar days to expiration",
            "execution": "Read-only research"}
