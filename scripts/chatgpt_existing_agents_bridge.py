"""Thin adapter to the repository's EXISTING TradingAgentsGraph.

No analyst prompts, scores, or logic are reimplemented. Import and execute
the graph only when an authorized Python runtime with its dependencies exists.
This module does not create hosted infrastructure or place trades.
"""
from datetime import date

DEFAULT_ANALYSTS = ("market", "social", "news", "fundamentals")


def run_existing_graph(ticker, trade_date, *, analysts=DEFAULT_ANALYSTS,
                       graph_factory=None, config=None, evidence_loader=None):
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("ticker required")
    if not isinstance(trade_date, str):
        raise ValueError("trade_date required")
    if date.fromisoformat(trade_date) > date.today():
        raise ValueError("future trade date prohibited")
    if not isinstance(analysts, (list, tuple)) or not analysts:
        raise ValueError("analysts required")
    if set(analysts) - set(DEFAULT_ANALYSTS + ("flow", "oi", "dealer")):
        raise ValueError("unsupported analyst: not registered in existing graph")
    if graph_factory is None:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        graph_factory = TradingAgentsGraph
    if set(analysts) & {"flow", "oi", "dealer"} and evidence_loader is None:
        raise ValueError("unsupported analyst without connected evidence_loader")
    kwargs = {"selected_analysts": tuple(analysts)}
    if config is not None:
        kwargs["config"] = config
    if evidence_loader is not None:
        kwargs["evidence_loader"] = evidence_loader
    graph = graph_factory(**kwargs)
    # The repository's original LangGraph handles analyst tools and reasoning.
    # No assumptions about scoring or trading signals are made here.
    return graph.propagate(ticker.strip().upper(), trade_date)
