from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from tradingagents.service import web_access
from tradingagents.service.mcp_oauth import current_mcp_identity
from tradingagents.service.mcp_tools import mcp


@asynccontextmanager
async def _lifespan(app):
    async with mcp.session_manager.run():
        yield


app = FastAPI(lifespan=_lifespan)


@app.middleware("http")
async def _test_auth(request, call_next):
    if request.url.path == "/mcp" or request.url.path.startswith("/mcp/"):
        if request.headers.get("authorization") != "Bearer smoke":
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        context_token = current_mcp_identity.set("smoke@example.com")
        try:
            return await call_next(request)
        finally:
            current_mcp_identity.reset(context_token)
    return await call_next(request)


app.mount("/mcp", mcp.streamable_http_app())


def test_tools_list_and_research_call_use_default_analysts(monkeypatch):
    quota_users = []
    analysts_seen = []
    monkeypatch.setattr(web_access, "consume_quota", quota_users.append)

    class _AnalyzeRequest:
        def __init__(self, **values):
            self.__dict__.update(values)

    def fake_execute_analysis(request):
        analysts_seen.append(request.analysts)
        return SimpleNamespace(
            ticker=request.ticker,
            trade_date="2026-10-17",
            signal="Bullish",
            analysts=request.analysts,
            final_state={"market_report": "smoke report"},
        )

    fake_api = ModuleType("tradingagents.service.api")
    fake_api.AnalyzeRequest = _AnalyzeRequest
    fake_api.execute_analysis = fake_execute_analysis
    monkeypatch.setitem(sys.modules, "tradingagents.service.api", fake_api)

    with TestClient(app, base_url="http://localhost:8000") as client:
        headers = {
            "Authorization": "Bearer smoke",
            "Accept": "application/json, text/event-stream",
        }
        initialized = client.post(
            "/mcp/",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "smoke", "version": "1.0"},
                },
            },
        )
        assert initialized.status_code == 200, initialized.text

        listed = client.post(
            "/mcp/",
            headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        assert listed.status_code == 200, listed.text
        names = {tool["name"] for tool in listed.json()["result"]["tools"]}
        assert names == {"run_trading_research", "get_tradingagents_status"}

        called = client.post(
            "/mcp/",
            headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "run_trading_research",
                    "arguments": {"ticker": "AMZN"},
                },
            },
        )
        assert called.status_code == 200, called.text
        assert "AMZN" in called.text
        assert quota_users == ["smoke@example.com"]
        assert analysts_seen == [
            ["market", "social", "news", "fundamentals", "flow", "oi", "dealer"]
        ]
