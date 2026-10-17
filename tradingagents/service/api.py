"""HTTP API for the Shah TradingAgents deployment layer.

This module intentionally wraps the upstream TradingAgentsGraph rather than
modifying its research graph. That keeps upstream merges small and gives us a
stable boundary for hosted deployment and, later, MCP.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from tradingagents.dataflows.date_window import get_current_date
from tradingagents.default_config import build_default_config
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.llm_clients import chatgpt_auth
from tradingagents.service.auth_store import install_postgres_auth_store
from tradingagents.service.web_chatgpt_auth import begin_sign_in, complete_sign_in

DEFAULT_ANALYSTS = ["market", "social", "news", "fundamentals"]
ALLOWED_ANALYSTS = frozenset(DEFAULT_ANALYSTS)
API_TOKEN_ENV = "SHAHTRADINGAGENTS_API_TOKEN"
DATABASE_URL_ENV = "DATABASE_URL"

install_postgres_auth_store()

app = FastAPI(
    title="Shah TradingAgents API",
    version="0.2.0",
    description="Service wrapper around the TradingAgents multi-agent research graph.",
)

_bearer = HTTPBearer(auto_error=False)


class AnalyzeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    trade_date: str | None = Field(
        default=None,
        description="Analysis date in YYYY-MM-DD. Defaults to today's market date.",
    )
    asset_type: Literal["stock", "crypto"] = "stock"
    analysts: list[str] = Field(default_factory=lambda: DEFAULT_ANALYSTS.copy())
    checkpoint: bool | None = None
    save_reports: bool = False
    html_report: bool = True


class AnalyzeResponse(BaseModel):
    ticker: str
    trade_date: str
    asset_type: str
    signal: str
    analysts: list[str]
    provider: str | None
    quick_model: str | None
    deep_model: str | None
    final_state: dict
    report_path: str | None = None


class ChatGPTAuthStartResponse(BaseModel):
    authorize_url: str
    expires_in_seconds: int = 600
    instructions: str


class ChatGPTAuthCompleteRequest(BaseModel):
    callback_url: str = Field(min_length=1)


class ChatGPTAuthCompleteResponse(BaseModel):
    signed_in: bool


def _json_safe(value):
    """Convert LangGraph/model objects to JSON-safe primitives without losing text."""
    return json.loads(json.dumps(value, default=str))


def _validated_analysts(names: list[str]) -> list[str]:
    cleaned = [name.strip().lower() for name in names if name and name.strip()]
    if not cleaned:
        raise ValueError("At least one analyst is required.")
    unknown = sorted(set(cleaned) - ALLOWED_ANALYSTS)
    if unknown:
        raise ValueError(
            f"Unsupported analysts: {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(ALLOWED_ANALYSTS))}."
        )
    selected = set(cleaned)
    return [name for name in DEFAULT_ANALYSTS if name in selected]


def _require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> None:
    """Require a Bearer token for privileged and cost-incurring endpoints."""
    expected = os.environ.get(API_TOKEN_ENV)
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service authentication is not configured; set {API_TOKEN_ENV}.",
        )
    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
def health() -> dict:
    """Cheap liveness probe that never exposes account identity or credentials."""
    config = build_default_config()
    return {
        "status": "ok",
        "service": "shah-tradingagents",
        "provider": config.get("llm_provider"),
        "quick_model": config.get("quick_think_llm"),
        "deep_model": config.get("deep_think_llm"),
        "api_auth_configured": bool(os.environ.get(API_TOKEN_ENV)),
        "persistent_auth_configured": bool(os.environ.get(DATABASE_URL_ENV)),
    }


@app.get("/ready")
def ready() -> dict:
    """Readiness details without leaking which ChatGPT account is signed in."""
    config = build_default_config()
    provider = config.get("llm_provider")
    chatgpt_ready = bool(chatgpt_auth.signed_in_as()) if provider == "chatgpt" else None
    auth_ready = bool(os.environ.get(API_TOKEN_ENV))
    persistence_ready = bool(os.environ.get(DATABASE_URL_ENV))
    ready_now = auth_ready and persistence_ready and (chatgpt_ready is not False)
    return {
        "ready": ready_now,
        "provider": provider,
        "api_auth_configured": auth_ready,
        "persistent_auth_configured": persistence_ready,
        "chatgpt_signed_in": chatgpt_ready,
    }


@app.post(
    "/auth/chatgpt/start",
    response_model=ChatGPTAuthStartResponse,
    dependencies=[Depends(_require_api_token)],
)
def auth_chatgpt_start() -> ChatGPTAuthStartResponse:
    if not os.environ.get(DATABASE_URL_ENV):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Persistent auth storage is not configured; set {DATABASE_URL_ENV}.",
        )
    try:
        return ChatGPTAuthStartResponse(
            authorize_url=begin_sign_in(),
            instructions=(
                "Open authorize_url and complete ChatGPT sign-in. The browser will finish on a "
                "127.0.0.1 URL that may not load. Copy that entire final URL and submit it to "
                "POST /auth/chatgpt/complete within 10 minutes."
            ),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not start ChatGPT sign-in ({type(exc).__name__}).",
        ) from exc


@app.post(
    "/auth/chatgpt/complete",
    response_model=ChatGPTAuthCompleteResponse,
    dependencies=[Depends(_require_api_token)],
)
def auth_chatgpt_complete(request: ChatGPTAuthCompleteRequest) -> ChatGPTAuthCompleteResponse:
    try:
        complete_sign_in(request.callback_url)
        return ChatGPTAuthCompleteResponse(signed_in=True)
    except chatgpt_auth.ChatGPTAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not complete ChatGPT sign-in ({type(exc).__name__}).",
        ) from exc


@app.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(_require_api_token)])
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    try:
        ticker = request.ticker.strip().upper()
        if not ticker:
            raise ValueError("Ticker cannot be blank.")

        analysts = _validated_analysts(request.analysts)
        trade_date = request.trade_date or get_current_date()
        config = build_default_config()
        if request.checkpoint is not None:
            config["checkpoint_enabled"] = request.checkpoint

        graph = TradingAgentsGraph(
            selected_analysts=analysts,
            config=config,
            debug=False,
        )
        final_state, signal = graph.propagate(
            ticker,
            trade_date,
            asset_type=request.asset_type,
        )

        report_path: Path | None = None
        if request.save_reports:
            report_path = graph.save_reports(
                final_state,
                ticker,
                html=request.html_report,
            )

        return AnalyzeResponse(
            ticker=ticker,
            trade_date=trade_date,
            asset_type=request.asset_type,
            signal=str(signal),
            analysts=analysts,
            provider=config.get("llm_provider"),
            quick_model=config.get("quick_think_llm"),
            deep_model=config.get("deep_think_llm"),
            final_state=_json_safe(final_state),
            report_path=str(report_path) if report_path else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"TradingAgents analysis failed ({type(exc).__name__}).",
        ) from exc
