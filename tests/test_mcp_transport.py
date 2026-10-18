from __future__ import annotations

import json
import threading
from types import SimpleNamespace
from urllib.parse import urlsplit

from tradingagents.service import api, web_access
from tradingagents.service.mcp_oauth import SERVICE_URL


def _tool_payload(response):
    result = response.json()["result"]
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                return json.loads(block.get("text", ""))
            except json.JSONDecodeError:
                continue
    raise AssertionError(f"MCP tool returned no JSON payload: {result!r}")


def _call_tool(client, headers, request_id, name, arguments):
    return client.post(
        "/mcp/",
        headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def test_mcp_transport_security_allows_public_host():
    host = urlsplit(SERVICE_URL).hostname
    security = api.tradingagents_mcp.settings.transport_security

    assert host
    assert security is not None
    assert security.enable_dns_rebinding_protection
    assert host in security.allowed_hosts
    assert f"{host}:*" in security.allowed_hosts


def test_tools_list_and_async_research_call_use_default_analysts(monkeypatch, service_client):
    quota_users = []
    analysts_seen = []
    analysis_started = threading.Event()
    release_analysis = threading.Event()

    monkeypatch.setattr(web_access, "consume_quota", quota_users.append)
    monkeypatch.setattr(
        api,
        "verify_mcp_access_token",
        lambda token: {
            "smoke": "smoke@example.com",
            "other": "other@example.com",
        }.get(token),
    )

    class _AnalyzeRequest:
        def __init__(self, **values):
            self.__dict__.update(values)

    def fake_execute_analysis(request):
        analysts_seen.append(request.analysts)
        analysis_started.set()
        release_analysis.wait(timeout=5)
        return SimpleNamespace(
            ticker=request.ticker,
            trade_date="2026-10-17",
            signal="Bullish",
            analysts=request.analysts,
            final_state={"market_report": "smoke report"},
        )

    monkeypatch.setattr(api, "AnalyzeRequest", _AnalyzeRequest)
    monkeypatch.setattr(api, "execute_analysis", fake_execute_analysis)

    headers = {
        "Authorization": "Bearer smoke",
        "Accept": "application/json, text/event-stream",
    }
    initialized = service_client.post(
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

    listed = service_client.post(
        "/mcp/",
        headers={**headers, "MCP-Protocol-Version": "2025-03-26"},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert listed.status_code == 200, listed.text
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert names == {
        "run_trading_research",
        "get_trading_research_result",
        "get_tradingagents_status",
    }

    started = _call_tool(
        service_client,
        headers,
        3,
        "run_trading_research",
        {"ticker": "AMZN", "wait_seconds": 0},
    )
    assert started.status_code == 200, started.text
    queued = _tool_payload(started)
    assert queued["status"] in {"queued", "running"}
    assert queued["ticker"] == "AMZN"
    assert queued["analysts"] == [
        "market", "social", "news", "fundamentals", "flow", "oi", "dealer"
    ]
    assert analysis_started.wait(timeout=2)

    other_headers = {
        "Authorization": "Bearer other",
        "Accept": "application/json, text/event-stream",
    }
    denied = _call_tool(
        service_client,
        other_headers,
        4,
        "get_trading_research_result",
        {"run_id": queued["run_id"], "wait_seconds": 0},
    )
    assert denied.status_code == 200, denied.text
    assert denied.json()["result"].get("isError") is True

    release_analysis.set()
    completed = _call_tool(
        service_client,
        headers,
        5,
        "get_trading_research_result",
        {"run_id": queued["run_id"], "wait_seconds": 5},
    )
    assert completed.status_code == 200, completed.text
    report = _tool_payload(completed)
    assert report["status"] == "completed"
    assert report["result"]["ticker"] == "AMZN"
    assert report["result"]["reports"]["market_report"] == "smoke report"
    assert quota_users == ["smoke@example.com"]
    assert analysts_seen == [
        ["market", "social", "news", "fundamentals", "flow", "oi", "dealer"]
    ]
