from __future__ import annotations

import asyncio
import hashlib
import re
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI

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
        if "INSERT INTO shah_sessions" in query:
            self.database.sessions[params[0]] = tuple(params[1:])
        elif "DELETE FROM shah_oauth_codes" in query:
            expected = self.database.code
            if expected and tuple(params) == expected[0]:
                self.row = expected[1]
                self.database.code = None
        elif "INSERT INTO shah_oauth_access_tokens" in query:
            self.database.access_token = tuple(params)
        elif "INSERT INTO shah_oauth_refresh_tokens" in query:
            self.database.refresh_tokens[params[0]] = tuple(params[1:])
        elif "SELECT email, resource, scope FROM shah_oauth_refresh_tokens" in query:
            token = self.database.refresh_tokens.get(params[0])
            self.row = (token[1], token[2], token[3]) if token and token[0] == params[1] else None
        elif "DELETE FROM shah_oauth_refresh_tokens" in query:
            token = self.database.refresh_tokens.get(params[0])
            if token and token[0] == params[1]:
                self.row = (token[1], token[2], token[3])
                self.database.refresh_tokens.pop(params[0])
            else:
                self.row = None
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

    def commit(self):
        return None


class _FakeDatabase:
    def __init__(self):
        self.code = None
        self.access_token = None
        self.sessions = {}
        self.refresh_tokens = {}
        self.clients = {}
        self.flows = {}

    def connect(self):
        return _FakeConnection(self)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(mcp_oauth.router)

    class _Client:
        async def _request(self, method, path, **kwargs):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://testserver",
                follow_redirects=False,
            ) as async_client:
                return await async_client.request(method, path, **kwargs)

        def get(self, path, **kwargs):
            return asyncio.run(self._request("GET", path, **kwargs))

        def post(self, path, **kwargs):
            return asyncio.run(self._request("POST", path, **kwargs))

    return _Client()


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
    assert server.json()["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert server.json()["scopes_supported"] == [
        mcp_oauth.RESEARCH_SCOPE,
        mcp_oauth.OFFLINE_ACCESS_SCOPE,
    ]


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
        json={
            "redirect_uris": [CHATGPT_CALLBACK],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
        },
    )
    assert accepted.status_code == 201
    client_id = accepted.json()["client_id"]
    assert client_id.startswith("shah-dcr-")
    assert accepted.json()["token_endpoint_auth_method"] == "none"
    assert accepted.json()["grant_types"] == ["authorization_code", "refresh_token"]
    assert mcp_oauth._client_redirects(client_id) == [CHATGPT_CALLBACK]


def test_authorization_code_flow_uses_invite_identity_and_pkce(client, monkeypatch):
    database = _FakeDatabase()
    monkeypatch.setattr(mcp_oauth, "_ensure_tables", lambda: None)
    monkeypatch.setattr(mcp_oauth, "_db", database.connect)
    monkeypatch.setattr(mcp_oauth, "ISSUER", "https://testserver")
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
            "scope": f"{mcp_oauth.RESEARCH_SCOPE} {mcp_oauth.OFFLINE_ACCESS_SCOPE}",
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
    assert exchanged.json()["scope"] == (
        f"{mcp_oauth.RESEARCH_SCOPE} {mcp_oauth.OFFLINE_ACCESS_SCOPE}"
    )
    assert exchanged.json()["refresh_token"]
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


def test_offline_access_issues_rotating_refresh_tokens(client, monkeypatch):
    database = _FakeDatabase()
    monkeypatch.setattr(mcp_oauth, "_ensure_tables", lambda: None)
    monkeypatch.setattr(mcp_oauth, "_db", database.connect)
    registered = client.post(
        "/oauth/register",
        json={"redirect_uris": [CHATGPT_CALLBACK], "grant_types": ["authorization_code"]},
    )
    client_id = registered.json()["client_id"]
    database.code = (
        (
            mcp_oauth._digest("one-time-code"),
            client_id,
            CHATGPT_CALLBACK,
            CHALLENGE,
            mcp_oauth.MCP_RESOURCE,
        ),
        (
            "invitee@example.com",
            mcp_oauth.MCP_RESOURCE,
            f"{mcp_oauth.RESEARCH_SCOPE} {mcp_oauth.OFFLINE_ACCESS_SCOPE}",
        ),
    )

    exchanged = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": "one-time-code",
            "redirect_uri": CHATGPT_CALLBACK,
            "resource": mcp_oauth.MCP_RESOURCE,
            "code_verifier": VERIFIER,
        },
    )
    first = exchanged.json()
    assert exchanged.status_code == 200
    assert first["scope"] == f"{mcp_oauth.RESEARCH_SCOPE} {mcp_oauth.OFFLINE_ACCESS_SCOPE}"
    assert first["refresh_token"]
    first_refresh_hash = mcp_oauth._digest(first["refresh_token"])
    assert first_refresh_hash in database.refresh_tokens

    refreshed = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": first["refresh_token"],
            "resource": mcp_oauth.MCP_RESOURCE,
        },
    )
    second = refreshed.json()
    assert refreshed.status_code == 200
    assert second["access_token"] != first["access_token"]
    assert second["refresh_token"] != first["refresh_token"]
    assert first_refresh_hash not in database.refresh_tokens
    second_refresh_hash = mcp_oauth._digest(second["refresh_token"])
    assert second_refresh_hash in database.refresh_tokens

    reused = client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": first["refresh_token"],
            "resource": mcp_oauth.MCP_RESOURCE,
        },
    )
    assert reused.status_code == 400
    assert reused.json()["error"] == "invalid_grant"



def test_owner_signin_page_explains_render_key_flow():
    page = mcp_oauth._login_page("flow-123")
    body = page.body.decode()

    assert "SHAHTRADINGAGENTS_API_TOKEN" in body
    assert 'action="/oauth/owner-login"' in body
    assert "you do not need to create an invitation code" in body
    assert "Invitation code" in body


def test_owner_oauth_login_validates_key_and_sets_session(client, monkeypatch):
    database = _FakeDatabase()
    monkeypatch.setattr(mcp_oauth, "_load_flow", lambda flow_id: {"state": "pending"})
    monkeypatch.setattr(mcp_oauth, "ISSUER", "https://testserver")
    monkeypatch.setenv("SHAHTRADINGAGENTS_API_TOKEN", "owner-test-key")

    from tradingagents.service import web_access

    monkeypatch.setattr(web_access, "db", database.connect)
    monkeypatch.setattr(web_access, "initialize", lambda: None)
    response = client.post(
        "/oauth/owner-login",
        data={
            "flow_id": "flow-123",
            "email": "Owner@Example.com",
            "owner_token": "owner-test-key",
        },
        headers={"origin": "https://testserver", "host": "internal.render.local:10000"},
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/oauth/authorize?flow=flow-123"
    assert "shah_session=" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    assert len(database.sessions) == 1
    session_hash, (email, _) = next(iter(database.sessions.items()))
    assert email == "owner@example.com"
    assert session_hash != "owner-test-key"


def test_owner_oauth_login_rejects_bad_key_and_cross_site_form(client, monkeypatch):
    monkeypatch.setattr(mcp_oauth, "_load_flow", lambda flow_id: {"state": "pending"})
    monkeypatch.setattr(mcp_oauth, "ISSUER", "https://testserver")
    monkeypatch.setenv("SHAHTRADINGAGENTS_API_TOKEN", "expected-owner-key")

    rejected = client.post(
        "/oauth/owner-login",
        data={
            "flow_id": "flow-123",
            "email": "owner@example.com",
            "owner_token": "wrong-key",
        },
        headers={"origin": "https://testserver"},
    )
    assert rejected.status_code == 200
    assert "did not match" in rejected.text
    assert "wrong-key" not in rejected.text

    no_origin = client.post(
        "/oauth/owner-login",
        data={
            "flow_id": "flow-123",
            "email": "owner@example.com",
            "owner_token": "wrong-key",
        },
        headers={
            "sec-fetch-site": "same-origin",
            "x-forwarded-host": "testserver",
            "x-forwarded-proto": "https",
        },
    )
    assert no_origin.status_code == 200
    assert "did not match" in no_origin.text

    csrf = client.post(
        "/oauth/owner-login",
        data={
            "flow_id": "flow-123",
            "email": "owner@example.com",
            "owner_token": "expected-owner-key",
        },
        headers={"origin": "https://attacker.example"},
    )
    assert csrf.status_code == 403
