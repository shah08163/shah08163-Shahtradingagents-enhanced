from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import urlsplit

from tradingagents.service import api, web_access
from tradingagents.service.mcp_oauth import SERVICE_URL


def test_mcp_transport_security_allows_public_host():
    host = urlsplit(SERVICE_URL).hostname
    security = api.tradingagents_mcp.settings.transport_security

    assert host
    assert security is not None
    assert security.enable_dns_rebinding_protection
    assert host in security.allowed_hosts
    assert f"{host}:*" in security.allowed_hosts


def test_tools_list_and_research_call_use_default_analysts(monkeypatch, service_client):
    quota_users = []
    analysts_seen = []
    monkeypatch.setattr(web_access, "consume_quota", quota_users.append)
    monkeypatch.setattr(api, "verify_mcp_access_token", lambda token: "smoke@example.com")

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
    assert names == {"run_trading_research", "get_tradingagents_status"}

    called = service_client.post(
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
