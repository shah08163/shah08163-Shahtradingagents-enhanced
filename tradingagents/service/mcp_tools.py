"""Private ChatGPT MCP interface to the existing research engine.

Authentication is enforced by the parent FastAPI app before MCP traffic reaches
its ASGI mount. Never embed access tokens in plugin manifests.
"""
from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextvars import copy_context
from dataclasses import dataclass
import logging
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import HTTPException
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from tradingagents.service.mcp_oauth import SERVICE_URL, current_mcp_identity

logger = logging.getLogger(__name__)

_RESEARCH_JOB_TTL_SECONDS = 30 * 60
_RESEARCH_JOB_LIMIT = 64
_RESEARCH_MAX_WAIT_SECONDS = 20
_research_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shah-research")
_research_jobs: dict[str, _ResearchJob] = {}
_research_jobs_lock = threading.Lock()


@dataclass
class _ResearchJob:
    owner: str
    ticker: str
    analysts: list[str]
    created_at: float
    future: Future


_mcp_public_host = urlsplit(SERVICE_URL).hostname
_mcp_allowed_hosts = [
    "localhost",
    "localhost:*",
    "127.0.0.1",
    "127.0.0.1:*",
    "[::1]",
    "[::1]:*",
]
if _mcp_public_host:
    _mcp_allowed_hosts.extend([_mcp_public_host, f"{_mcp_public_host}:*"])

mcp = FastMCP(
    "Shah TradingAgents",
    instructions=(
        "Run read-only stock research with Shah TradingAgents. "
        "run_trading_research returns a run ID promptly for long runs. "
        "Poll get_trading_research_result until status is completed or failed; "
        "use its wait_seconds argument to wait between polls. "
        "Never treat a queued or running status as a final report. Research does not execute trades."
    ),
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(allowed_hosts=_mcp_allowed_hosts),
)


def _prune_research_jobs_locked(now: float) -> None:
    expired = [
        run_id for run_id, job in _research_jobs.items()
        if job.future.done() and now - job.created_at > _RESEARCH_JOB_TTL_SECONDS
    ]
    for run_id in expired:
        del _research_jobs[run_id]

    while len(_research_jobs) >= _RESEARCH_JOB_LIMIT:
        completed = [
            (job.created_at, run_id)
            for run_id, job in _research_jobs.items()
            if job.future.done()
        ]
        if not completed:
            raise RuntimeError("Research queue is full; retry when a run finishes.")
        _, oldest_run_id = min(completed)
        del _research_jobs[oldest_run_id]


def _format_report(result) -> dict:
    fields = (
        "market_report", "sentiment_report", "news_report", "fundamentals_report",
        "flow_report", "oi_report", "dealer_positioning_report", "evidence_report",
        "final_trade_decision",
    )
    return {
        "ticker": result.ticker,
        "date": result.trade_date,
        "signal": result.signal,
        "analysts": result.analysts,
        "reports": {
            field: str(result.final_state.get(field, ""))[:16000]
            for field in fields
            if result.final_state.get(field)
        },
        "disclaimer": "Research only; no trades placed. Check source timestamps and quality.",
    }


def _execute_research(request) -> dict:
    try:
        from tradingagents.service.api import execute_analysis

        result = execute_analysis(request)
        return {"status": "completed", "result": _format_report(result)}
    except HTTPException as exc:
        return {"status": "failed", "error": str(exc.detail)}
    except Exception as exc:
        logger.error("MCP research job failed (%s)", type(exc).__name__)
        return {"status": "failed", "error": f"Research failed ({type(exc).__name__})."}


def _job_response(run_id: str, job: _ResearchJob, wait_seconds: int) -> dict:
    if isinstance(wait_seconds, bool) or not 0 <= wait_seconds <= _RESEARCH_MAX_WAIT_SECONDS:
        raise ValueError(
            f"wait_seconds must be between 0 and {_RESEARCH_MAX_WAIT_SECONDS}."
        )
    if wait_seconds and not job.future.done():
        try:
            job.future.result(timeout=wait_seconds)
        except FutureTimeout:
            pass

    metadata = {
        "run_id": run_id,
        "ticker": job.ticker,
        "analysts": job.analysts,
    }
    if not job.future.done():
        status = "running" if job.future.running() else "queued"
        return {
            **metadata,
            "status": status,
            "retry_after_seconds": 5,
        }

    try:
        outcome = job.future.result()
    except Exception as exc:
        logger.error("MCP research job failed (%s)", type(exc).__name__)
        outcome = {"status": "failed", "error": f"Research failed ({type(exc).__name__})."}
    return {**metadata, **outcome}


def _owned_research_job(run_id: str) -> _ResearchJob:
    identity = current_mcp_identity.get()
    with _research_jobs_lock:
        _prune_research_jobs_locked(time.monotonic())
        job = _research_jobs.get(run_id)
        if job is None or not identity or job.owner != identity:
            raise ValueError("Research run not found or expired.")
        return job


@mcp.tool()
def run_trading_research(
    ticker: str,
    analysts: list[str] | None = None,
    wait_seconds: int = 5,
) -> dict:
    """Start stock/ETF research and return promptly with its run ID.

    Available analysts: market, social, news, fundamentals, flow, oi, dealer.
    Omit analysts to run all seven. OI uses Schwab full-strike 0-60 DTE data
    and Bullflow where available. Long runs continue in the background.

    If status is queued or running, call get_trading_research_result with the
    returned run_id and wait_seconds=15. Repeat until completed or failed.
    This is read-only and never submits orders.
    """
    identity = current_mcp_identity.get()
    if not identity:
        raise ValueError("Authenticated caller identity is unavailable.")

    if analysts is None:
        selected = ["market", "social", "news", "fundamentals", "flow", "oi", "dealer"]
    else:
        selected = analysts

    from tradingagents.service.web_access import consume_quota
    from tradingagents.service.api import AnalyzeRequest

    consume_quota(identity)
    request = AnalyzeRequest(
        ticker=ticker,
        analysts=selected,
        save_reports=False,
        checkpoint=False,
    )
    normalized_ticker = request.ticker.strip().upper()
    selected_analysts = list(request.analysts)

    with _research_jobs_lock:
        _prune_research_jobs_locked(time.monotonic())
        run_id = secrets.token_urlsafe(18)
        context = copy_context()
        future = _research_executor.submit(context.run, _execute_research, request)
        job = _ResearchJob(
            owner=identity,
            ticker=normalized_ticker,
            analysts=selected_analysts,
            created_at=time.monotonic(),
            future=future,
        )
        _research_jobs[run_id] = job

    return _job_response(run_id, job, wait_seconds)


@mcp.tool()
def get_trading_research_result(run_id: str, wait_seconds: int = 15) -> dict:
    """Get the status or finished report for a research run.

    Use the run_id returned by run_trading_research. This call waits up to
    wait_seconds (maximum 20); if status remains queued or running, repeat it
    until it returns completed or failed. Run results are private to the
    authenticated caller and expire after 30 minutes.
    """
    job = _owned_research_job(run_id)
    return _job_response(run_id, job, wait_seconds)


@mcp.tool()
def get_tradingagents_status() -> dict:
    """Check whether the TradingAgents MCP integration is configured and which analysts are available."""
    from tradingagents.service.api import ANALYST_ORDER
    return {
        "status": "online",
        "analysts": ANALYST_ORDER,
        "oi_scope": "Full strikes, up to 60 calendar days to expiration",
        "execution": "Read-only research",
    }
