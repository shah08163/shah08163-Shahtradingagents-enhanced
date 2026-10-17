from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tradingagents.service import mcp_oauth

CHATGPT_CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
CLIENT_ID = "shah-dcr-test-client"
VERIFIER = "v" * 43
CHALLENGE = mcp_oauth._b64url(hashlib.sha256(VERIFIER.encode("ascii")).digest())


class _FakeCursor:
    def __init__(self, database):
        self.database = database
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        if "DELETE FROM shah_oauth_codes" in query:
            expected = self.database.code
            if expected and tuple(params) == expected[0]:
                self.row = expected[1]
                self.database.code = None
        elif "INSERT INTO shah_oauth_access_tokens" in query:
            self.database.access_token = tuple(params)
        elif "INSERT INTO shah_oauth_clients" in query:
            self.database.clients[params[0]] = list(params[1])
        elif "SELECT redirect_uris FROM shah_oauth_clients" in query:
            redirects = self.database.clients.get(params[0])
            self.row = (redirects,) if redirects else None
        elif "INSERT INTO shah_oauth_flows" in query:
            self.database.flows[params[0]] = tuple(params[1:7])
        elif "SELECT client_id, redirect_uri, state, code_challenge, resource, scope" in query:
            self.row = self.database.flows.get(params[0])
        elif "DELETE FROM shah_oauth_flows" in query:
            self.row = self.database.flows.pop(params[0], None)
        elif "INSERT INTO shah_oauth_codes" in query:
            self.database.code = (
                (params[0], params[1], params[2], params[4], params[5]),
                (params[3], params[5], params[6]),
            )
        else:
            raise AssertionError(f"Unexpected SQL in OAuth token test: {query}")

    def fetchone(self):
        return self.row


class _FakeConnection:
    def __init__(self, database):
        self.database = database

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self.database)


class _FakeDatabase:
    def __init__(self):
        self.code = None
        self.access_token = None
        self.clients = {}
        self.flows = {}

    def connect(self):
        return _FakeConnection(self)


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(mcp_oauth.router)
    return TestClient(app, follow_redirects=False)


def test_discovery_metadata_advertises_supported_oauth_contract(client):
    resource = client.get("/.well-known/oauth-protected-resource/mcp")
    server = client.get("/.well-known/oauth-authorization-server")

    assert resource.status_code == 200
    assert resource.json()["resource"] == mcp_oauth.MCP_RESOURCE
    assert resource.json()["authorization_servers"] == [mcp_oauth.ISSUER]
    assert resource.json()["scopes_supported"] == [mcp_oauth.RESEARCH_SCOPE]

    assert server.status_code == 200
    assert server.json()["authorization_response_iss_parameter_supported"] is True
    assert server.json()["client_id_metadata_document_supported"] is True
    assert "S256" in server.json()["code_challenge_methods_supported"]
    assert server.json()["token_endpoint_auth_methods_supported"] == ["none"]


@pytest.mark.parametrize(
    "callback",
    [
        CHATGPT_CALLBACK,
        "https://chatgpt.com/connector/oauth/callback_123",
    ],
)
def test_allows_chatgpt_oauth_callbacks(callback):
    assert mcp_oauth._allowed_redirect_uri(callback)


@pytest.mark.parametrize(
    "callback",
    [
        "https://attacker.example/callback",
        "http://chatgpt.com/connector_platform_oauth_redirect",
        "https://chatgpt.com.evil.example/connector_platform_oauth_redirect",
        "https://chatgpt.com/connector_platform_oauth_redirect?next=https://attacker.example",
    ],
)
def test_rejects_non_chatgpt_or_mutated_callbacks(callback):
    assert not mcp_oauth._allowed_redirect_uri(callback)


def test_authorize_rejects_unrecognized_oauth_client_without_redirect(client):
    response = client.get(
        "/oauth/authorize",
        params={
            "client_id": "https://evil.example/client.json",
            "redirect_uri": CHATGPT_CALLBACK,
            "response_type": "code",
            "state": "opaque-state",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "resource": mcp_oauth.MCP_RESOURCE,
        },
    )

    assert response.status_code == 400
    assert "Cannot connect" in response.text
    assert "evil.example" not in response.headers.get("location", "")


def test_dynamic_client_registration_only_accepts_chatgpt_callbacks(client, monkeypatch):
    database = _FakeDatabase()
    monkeypatch.setattr(mcp_oauth, "_ensure_tables", lambda: None)
    monkeypatch.setattr(mcp_oauth, "_db", database.connect)

    rejected = client.post(
        "/oauth/register",
        json={"redirect_uris": ["https://attacker.example/callback"]},
    )
    assert rejected.status_code == 400
    assert database.clients == {}

    accepted = client.post(
        "/oauth/register",
        json={"redirect_uris": [CHATGPT_CALLBACK], "token_endpoint_auth_method": "none"},
    )
    assert accepted.status_code == 201
    client_id = accepted.json()["client_id"]
    assert client_id.startswith("shah-dcr-")
    assert accepted.json()["token_endpoint_auth_method"] == "none"
    assert mcp_oauth._client_redirects(client_id) == [CHATGPT_CALLBACK]


def test_authorization_code_flow_uses_invite_identity_and_pkce(client, monkeypatch):
    database = _FakeDatabase()
    monkeypatch.setattr(mcp_oauth, "_ensure_tables", lambda: None)
    monkeypatch.setattr(mcp_oauth, "_db", database.connect)
    registered = client.post("/oauth/register", json={"redirect_uris": [CHATGPT_CALLBACK]})
    client_id = registered.json()["client_id"]

    from tradingagents.service import web_access

    monkeypatch.setattr(web_access, "session_email", lambda request: "invitee@example.com")
    authorization = client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": CHATGPT_CALLBACK,
            "response_type": "code",
            "state": "opaque-state",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "resource": mcp_oauth.MCP_RESOURCE,
            "scope": mcp_oauth.RESEARCH_SCOPE,
        },
    )
    assert authorization.status_code == 200
    assert "invitee@example.com" in authorization.text
    flow_id = re.search(r'name="flow_id" value="([^"]+)"', authorization.text).group(1)
    consent = client.post(
        "/oauth/consent",
        data={"flow_id": flow_id, "decision": "allow"},
        headers={"origin": "https://testserver"},
    )
    assert consent.status_code == 303
    callback = consent.headers["location"]
    callback_params = parse_qs(urlsplit(callback).query)
    assert callback.startswith(CHATGPT_CALLBACK + "?")
    assert callback_params["state"] == ["opaque-state"]
    assert callback_params["iss"] == [mcp_oauth.ISSUER]

    exchanged = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": callback_params["code"][0],
            "redirect_uri": CHATGPT_CALLBACK,
            "resource": mcp_oauth.MCP_RESOURCE,
            "code_verifier": VERIFIER,
        },
    )
    assert exchanged.status_code == 200
    assert exchanged.json()["scope"] == mcp_oauth.RESEARCH_SCOPE
    assert database.access_token[2] == "invitee@example.com"


def test_token_exchange_requires_the_matching_pkce_verifier(client, monkeypatch):
    database = _FakeDatabase()
    code = "one-time-code"
    database.code = (
        (
            mcp_oauth._digest(code),
            CLIENT_ID,
            CHATGPT_CALLBACK,
            CHALLENGE,
            mcp_oauth.MCP_RESOURCE,
        ),
        ("invitee@example.com", mcp_oauth.MCP_RESOURCE, mcp_oauth.RESEARCH_SCOPE),
    )
    monkeypatch.setattr(mcp_oauth, "_ensure_tables", lambda: None)
    monkeypatch.setattr(mcp_oauth, "_db", database.connect)

    rejected = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": CHATGPT_CALLBACK,
            "resource": mcp_oauth.MCP_RESOURCE,
            "code_verifier": "x" * 43,
        },
    )
    assert rejected.status_code == 400
    assert database.access_token is None
    assert database.code is not None

    accepted = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": CHATGPT_CALLBACK,
            "resource": mcp_oauth.MCP_RESOURCE,
            "code_verifier": VERIFIER,
        },
    )
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["token_type"] == "Bearer"
    assert payload["scope"] == mcp_oauth.RESEARCH_SCOPE
    assert database.access_token[0] == mcp_oauth._digest(payload["access_token"])
    assert database.access_token[2] == "invitee@example.com"
    assert database.code is None


def test_token_verification_checks_scope_and_resource(monkeypatch):
    database = _FakeDatabase()
    database.token_row = ("invitee@example.com", mcp_oauth.MCP_RESOURCE, mcp_oauth.RESEARCH_SCOPE)

    class _LookupCursor(_FakeCursor):
        def execute(self, query, params=None):
            if "SELECT email, resource, scope" in query:
                self.row = self.database.token_row
            else:
                raise AssertionError(f"Unexpected SQL in token validation test: {query}")

    class _LookupConnection(_FakeConnection):
        def cursor(self):
            return _LookupCursor(self.database)

    database.connect = lambda: _LookupConnection(database)
    monkeypatch.setattr(mcp_oauth, "_ensure_tables", lambda: None)
    monkeypatch.setattr(mcp_oauth, "_db", database.connect)

    assert mcp_oauth.verify_mcp_access_token("opaque-token") == "invitee@example.com"
    database.token_row = (
        "invitee@example.com",
        "https://attacker.example/mcp",
        mcp_oauth.RESEARCH_SCOPE,
    )
    assert mcp_oauth.verify_mcp_access_token("opaque-token") is None
    database.token_row = ("invitee@example.com", mcp_oauth.MCP_RESOURCE, "profile")
    assert mcp_oauth.verify_mcp_access_token("opaque-token") is None
