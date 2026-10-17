"""HTTP access controls and dashboard smoke tests (no external LLM calls)."""

import pytest

pytest.importorskip("fastapi", reason="Optional service dependencies are not installed")


def test_dashboard_and_api_docs_are_served(service_client):
    dashboard = service_client.get("/app")
    assert dashboard.status_code == 200
    assert "Shah TradingAgents" in dashboard.text
    assert "EXPLORER_ACCESS_TOKEN" not in dashboard.text
    assert "SHAHTRADINGAGENTS_API_TOKEN" not in dashboard.text
    assert service_client.get("/docs").status_code == 200


def test_invite_only_access_and_owner_route_authentication(service_client):
    assert service_client.get("/web/me").status_code == 401
    assert service_client.post(
        "/web/analyze",
        json={"ticker": "AMZN"},
        headers={"Origin": "https://localhost:8000"},
    ).status_code == 401
    assert service_client.post(
        "/admin/invites", json={"email": "invitee@example.com"}
    ).status_code == 401


def test_mcp_requires_dedicated_bearer_token(service_client, monkeypatch):
    monkeypatch.setenv("SHAHTRADINGAGENTS_MCP_TOKEN", "local-only-test")
    response = service_client.post(
        "/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    )
    assert response.status_code == 401
    assert "local-only-test" not in response.text
