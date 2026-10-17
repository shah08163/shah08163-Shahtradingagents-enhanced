"""HTTP access controls and dashboard smoke tests (no external LLM calls)."""
from importlib import import_module

import pytest

pytest.importorskip('fastapi', reason='Optional service dependencies are not installed')
TestClient = import_module('fastapi.testclient').TestClient
app = import_module('tradingagents.service.api').app


def test_dashboard_and_api_docs_are_served():
    with TestClient(app) as client:
        dashboard = client.get("/app")
        assert dashboard.status_code == 200
        assert "Shah TradingAgents" in dashboard.text
        assert "EXPLORER_ACCESS_TOKEN" not in dashboard.text
        assert "SHAHTRADINGAGENTS_API_TOKEN" not in dashboard.text
        assert client.get("/docs").status_code == 200


def test_invite_only_access_and_owner_route_authentication():
    with TestClient(app) as client:
        assert client.get("/web/me").status_code == 401
        assert client.post("/web/analyze", json={"ticker": "AMZN"},
                           headers={"Origin": "https://testserver"}).status_code == 401
        assert client.post("/admin/invites", json={"email": "invitee@example.com"}).status_code == 401


def test_mcp_requires_dedicated_bearer_token(monkeypatch):
    monkeypatch.setenv("SHAHTRADINGAGENTS_MCP_TOKEN", "local-only-test")
    with TestClient(app) as client:
        response = client.post("/mcp/", json={"jsonrpc": "2.0", "id": 1,
                                               "method": "tools/list"})
        assert response.status_code == 401
        assert "local-only-test" not in response.text
