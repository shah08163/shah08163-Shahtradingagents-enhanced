"""OAuth authorization for the hosted Shah TradingAgents MCP endpoint.

ChatGPT custom MCP connections accept OAuth rather than static API-key
headers. This small authorization server reuses the service's existing
invite-only identity and issues short-lived, audience-bound bearer tokens.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

SERVICE_URL = os.environ.get(
    "SHAHTRADINGAGENTS_PUBLIC_URL", "https://shah-tradingagents.onrender.com"
).rstrip("/")
ISSUER = os.environ.get("SHAHTRADINGAGENTS_OAUTH_ISSUER", SERVICE_URL).rstrip("/")
MCP_RESOURCE = os.environ.get("SHAHTRADINGAGENTS_MCP_RESOURCE", f"{SERVICE_URL}/mcp/")
RESOURCE_ALIASES = frozenset({MCP_RESOURCE, MCP_RESOURCE.rstrip("/")})
RESOURCE_METADATA_URL = f"{ISSUER}/.well-known/oauth-protected-resource/mcp"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/oauth/authorize"
TOKEN_ENDPOINT = f"{ISSUER}/oauth/token"
REGISTRATION_ENDPOINT = f"{ISSUER}/oauth/register"
RESEARCH_SCOPE = "research:read"
OFFLINE_ACCESS_SCOPE = "offline_access"
SUPPORTED_SCOPES = (RESEARCH_SCOPE, OFFLINE_ACCESS_SCOPE)
FLOW_TTL_SECONDS = 600
CODE_TTL_SECONDS = 600
ACCESS_TOKEN_TTL_SECONDS = 3600
REFRESH_TOKEN_TTL_SECONDS = 90 * 24 * 60 * 60
MAX_REQUEST_BODY = 16_384
MAX_CIMD_BYTES = 65_536

router = APIRouter()
current_mcp_identity: ContextVar[str | None] = ContextVar(
    "shah_tradingagents_mcp_identity", default=None
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _allowed_resource(value: str) -> bool:
    return value in RESOURCE_ALIASES


def _allowed_redirect_uri(value: str) -> bool:
    """Only permit ChatGPT's documented callback forms."""
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return False
    if parsed.path == "/connector_platform_oauth_redirect":
        return True
    return re.fullmatch(r"/connector/oauth/[A-Za-z0-9_-]{1,128}", parsed.path) is not None


def _valid_cimd_url(client_id: str) -> bool:
    """Reject arbitrary URLs before fetching a client metadata document."""
    try:
        parsed = urllib.parse.urlsplit(client_id)
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or parsed.netloc != "chatgpt.com"
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        return False
    return (
        parsed.path == "/oauth/client.json"
        or re.fullmatch(r"/oauth/[A-Za-z0-9_-]{1,128}/client.json", parsed.path) is not None
    )


def _db():
    from tradingagents.service.web_access import db

    return db()


def _ensure_tables() -> None:
    from tradingagents.service.web_access import initialize

    initialize()
    with _db() as connection, connection.cursor() as cursor:
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS shah_oauth_clients (
                client_id TEXT PRIMARY KEY,
                redirect_uris TEXT[] NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS shah_oauth_flows (
                flow_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                state TEXT NOT NULL,
                code_challenge TEXT NOT NULL,
                resource TEXT NOT NULL,
                scope TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL)"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS shah_oauth_codes (
                code_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                redirect_uri TEXT NOT NULL,
                email TEXT NOT NULL,
                code_challenge TEXT NOT NULL,
                resource TEXT NOT NULL,
                scope TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL)"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS shah_oauth_access_tokens (
                token_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                email TEXT NOT NULL,
                resource TEXT NOT NULL,
                scope TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""
        )
        cursor.execute(
            """CREATE TABLE IF NOT EXISTS shah_oauth_refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                email TEXT NOT NULL,
                resource TEXT NOT NULL,
                scope TEXT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""
        )


def _normalize_scope(scope: str, *, allowed: set[str] | None = None) -> str | None:
    scopes = scope.split()
    if not scopes or len(scopes) != len(set(scopes)):
        return None
    values = set(scopes)
    allowed_scopes = set(SUPPORTED_SCOPES) if allowed is None else allowed
    if RESEARCH_SCOPE not in values or not values.issubset(allowed_scopes):
        return None
    return " ".join(item for item in SUPPORTED_SCOPES if item in values)


def _client_metadata(client_id: str) -> dict[str, Any]:
    if not _valid_cimd_url(client_id):
        raise ValueError("Unsupported OAuth client identifier.")
    request = urllib.request.Request(
        client_id,
        headers={"Accept": "application/json", "User-Agent": "ShahTradingAgents/1.0"},
    )
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=5) as response:
            if response.status != 200:
                raise ValueError("Could not read ChatGPT client metadata.")
            raw = response.read(MAX_CIMD_BYTES + 1)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise ValueError("Could not read ChatGPT client metadata.") from exc
    if len(raw) > MAX_CIMD_BYTES:
        raise ValueError("ChatGPT client metadata is too large.")
    try:
        metadata = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("ChatGPT client metadata is invalid.") from exc
    if not isinstance(metadata, dict) or metadata.get("client_id") != client_id:
        raise ValueError("ChatGPT client metadata does not match its URL.")
    redirects = metadata.get("redirect_uris")
    methods = metadata.get("token_endpoint_auth_methods_supported", [])
    if (
        not isinstance(redirects, list)
        or not redirects
        or any(not isinstance(uri, str) or not _allowed_redirect_uri(uri) for uri in redirects)
        or not isinstance(methods, list)
        or "none" not in methods
    ):
        raise ValueError(
            "ChatGPT client metadata is missing a supported public-client configuration."
        )
    return metadata


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _client_redirects(client_id: str) -> list[str] | None:
    """Return registered DCR redirects; CIMD clients are checked remotely."""
    if client_id.startswith("shah-dcr-"):
        _ensure_tables()
        with _db() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT redirect_uris FROM shah_oauth_clients WHERE client_id = %s",
                (client_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return list(row[0])
    metadata = _client_metadata(client_id)
    return metadata["redirect_uris"]


def _store_cimd_client(client_id: str, redirects: list[str]) -> None:
    _ensure_tables()
    with _db() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT redirect_uris FROM shah_oauth_clients WHERE client_id = %s",
            (client_id,),
        )
        row = cursor.fetchone()
        if row and list(row[0]) != redirects:
            raise ValueError("ChatGPT client metadata changed after it was first used.")
        if not row:
            cursor.execute(
                "INSERT INTO shah_oauth_clients (client_id, redirect_uris) VALUES (%s, %s)",
                (client_id, redirects),
            )


def _new_flow(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    resource: str,
    scope: str,
) -> str:
    _ensure_tables()
    flow_id = secrets.token_urlsafe(32)
    with _db() as connection, connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO shah_oauth_flows
                (flow_hash, client_id, redirect_uri, state, code_challenge,
                 resource, scope, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                _digest(flow_id),
                client_id,
                redirect_uri,
                state,
                code_challenge,
                resource,
                scope,
                datetime.now(UTC) + timedelta(seconds=FLOW_TTL_SECONDS),
            ),
        )
    return flow_id


def _load_flow(flow_id: str) -> dict[str, Any] | None:
    if not flow_id or len(flow_id) > 128:
        return None
    _ensure_tables()
    with _db() as connection, connection.cursor() as cursor:
        cursor.execute(
            """SELECT client_id, redirect_uri, state, code_challenge, resource, scope
                FROM shah_oauth_flows WHERE flow_hash = %s AND expires_at > NOW()""",
            (_digest(flow_id),),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "client_id": row[0],
        "redirect_uri": row[1],
        "state": row[2],
        "code_challenge": row[3],
        "resource": row[4],
        "scope": row[5],
    }


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>body{{font:16px system-ui,sans-serif;max-width:36rem;margin:4rem auto;padding:0 1.2rem;color:#202124}}
label,input,button{{display:block;margin:.8rem 0}}input{{box-sizing:border-box;width:100%;padding:.7rem}}
button{{padding:.65rem 1rem;cursor:pointer}}.muted{{color:#5f6368}}</style>
<body><h1>{html.escape(title)}</h1>{body}</body></html>"""
    return HTMLResponse(
        document,
        status_code=status_code,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _login_page(flow_id: str, message: str | None = None) -> HTMLResponse:
    safe_id = html.escape(flow_id, quote=True)
    note = f'<p role="alert">{html.escape(message)}</p>' if message else ""
    body = f"""{note}<p>Sign in with a Shah TradingAgents invitation to connect this read-only research server.</p>
<form method="post" action="/oauth/login">
<input type="hidden" name="flow_id" value="{safe_id}">
<label for="invite">Invitation code</label>
<input id="invite" name="invite" type="password" autocomplete="one-time-code" required>
<button type="submit">Continue</button></form>
<p class="muted">The code is single-use. If you already signed in, return to ChatGPT and retry.</p>"""
    return _page("Sign in to Shah TradingAgents", body)


def _consent_page(flow_id: str, email: str) -> HTMLResponse:
    safe_id = html.escape(flow_id, quote=True)
    safe_email = html.escape(email)
    body = f"""<p><strong>{safe_email}</strong></p>
<p>Allow ChatGPT to use Shah TradingAgents to run read-only stock research with the seven analysts. No trades can be placed.</p>
<form method="post" action="/oauth/consent">
<input type="hidden" name="flow_id" value="{safe_id}">
<button type="submit" name="decision" value="allow">Allow research access</button>
<button type="submit" name="decision" value="deny">Cancel</button>
</form>"""
    return _page("Connect Shah TradingAgents", body)


def _redirect_with_error(flow: dict[str, Any], error: str) -> RedirectResponse:
    query = urllib.parse.urlencode({"error": error, "state": flow["state"], "iss": ISSUER})
    return RedirectResponse(f"{flow['redirect_uri']}?{query}", status_code=303)


def _finish_authorization(flow_id: str, email: str) -> RedirectResponse:
    _ensure_tables()
    with _db() as connection, connection.cursor() as cursor:
        cursor.execute(
            """DELETE FROM shah_oauth_flows
                WHERE flow_hash = %s AND expires_at > NOW()
                RETURNING client_id, redirect_uri, state, code_challenge, resource, scope""",
            (_digest(flow_id),),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(400, "This sign-in request expired. Start again from ChatGPT.")
        code = secrets.token_urlsafe(32)
        cursor.execute(
            """INSERT INTO shah_oauth_codes
                (code_hash, client_id, redirect_uri, email, code_challenge,
                 resource, scope, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                _digest(code),
                row[0],
                row[1],
                email,
                row[3],
                row[4],
                row[5],
                datetime.now(UTC) + timedelta(seconds=CODE_TTL_SECONDS),
            ),
        )
    query = urllib.parse.urlencode({"code": code, "state": row[2], "iss": ISSUER})
    return RedirectResponse(f"{row[1]}?{query}", status_code=303)


@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource_metadata() -> dict[str, Any]:
    return {
        "resource": MCP_RESOURCE,
        "authorization_servers": [ISSUER],
        "scopes_supported": [RESEARCH_SCOPE],
        "bearer_methods_supported": ["header"],
    }


@router.get("/.well-known/oauth-authorization-server")
def authorization_server_metadata() -> dict[str, Any]:
    return {
        "issuer": ISSUER,
        "authorization_endpoint": AUTHORIZATION_ENDPOINT,
        "token_endpoint": TOKEN_ENDPOINT,
        "registration_endpoint": REGISTRATION_ENDPOINT,
        "client_id_metadata_document_supported": True,
        "authorization_response_iss_parameter_supported": True,
        "token_endpoint_auth_methods_supported": ["none"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "response_types_supported": ["code"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": list(SUPPORTED_SCOPES),
    }


@router.post("/oauth/register")
async def register_client(request: Request) -> JSONResponse:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type != "application/json":
        raise HTTPException(415, "JSON required.")
    raw = await request.body()
    if len(raw) > MAX_REQUEST_BODY:
        raise HTTPException(413, "Registration request is too large.")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid registration request.") from None
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid registration request.")
    redirects = payload.get("redirect_uris")
    requested_grants = payload.get("grant_types", ["authorization_code"])
    requested_responses = payload.get("response_types", ["code"])
    requested_auth_method = payload.get("token_endpoint_auth_method", "none")
    if (
        not isinstance(redirects, list)
        or not redirects
        or len(redirects) > 10
        or any(not isinstance(uri, str) or not _allowed_redirect_uri(uri) for uri in redirects)
        or not isinstance(requested_grants, list)
        or not all(isinstance(grant, str) for grant in requested_grants)
        or len(requested_grants) != len(set(requested_grants))
        or set(requested_grants)
        not in (
            {"authorization_code"},
            {"authorization_code", "refresh_token"},
        )
        or requested_responses != ["code"]
        or requested_auth_method != "none"
    ):
        raise HTTPException(400, "Only approved ChatGPT HTTPS callback URLs are supported.")
    client_id = "shah-dcr-" + secrets.token_urlsafe(24)
    _ensure_tables()
    with _db() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO shah_oauth_clients (client_id, redirect_uris) VALUES (%s,%s)",
            (client_id, redirects),
        )
    return JSONResponse(
        {
            "client_id": client_id,
            "client_id_issued_at": int(time.time()),
            "redirect_uris": redirects,
            "grant_types": requested_grants,
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "client_name": str(payload.get("client_name") or "ChatGPT")[:128],
        },
        status_code=201,
    )


@router.get("/oauth/authorize", response_class=HTMLResponse)
def authorize(request: Request):
    flow_id = request.query_params.get("flow")
    if flow_id:
        flow = _load_flow(flow_id)
        if not flow:
            return _page(
                "Sign-in expired", "<p>Return to ChatGPT and start the connection again.</p>", 400
            )
    else:
        params = request.query_params
        client_id = params.get("client_id", "")
        redirect_uri = params.get("redirect_uri", "")
        state = params.get("state", "")
        code_challenge = params.get("code_challenge", "")
        resource = params.get("resource", "")
        requested_scope = _normalize_scope(params.get("scope", RESEARCH_SCOPE))
        try:
            redirects = _client_redirects(client_id) if client_id else None
        except (OSError, ValueError):
            redirects = None
        if (
            params.get("response_type") != "code"
            or params.get("code_challenge_method") != "S256"
            or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", code_challenge)
            or not state
            or len(state) > 512
            or not redirects
            or redirect_uri not in redirects
            or not _allowed_redirect_uri(redirect_uri)
            or not _allowed_resource(resource)
            or requested_scope is None
        ):
            return _page(
                "Cannot connect",
                "<p>The OAuth request is missing valid ChatGPT client, callback, resource, or PKCE settings.</p>",
                400,
            )
        if client_id.startswith("shah-dcr-"):
            pass
        else:
            try:
                _store_cimd_client(client_id, redirects)
            except ValueError as exc:
                return _page("Cannot connect", f"<p>{html.escape(str(exc))}</p>", 400)
        flow_id = _new_flow(
            client_id, redirect_uri, state, code_challenge, resource, requested_scope
        )

    from tradingagents.service.web_access import session_email

    try:
        email = session_email(request)
    except HTTPException:
        return _login_page(flow_id)
    return _consent_page(flow_id, email)


def _parse_form(raw: bytes, content_type: str) -> dict[str, str]:
    if len(raw) > MAX_REQUEST_BODY:
        raise HTTPException(413, "Request is too large.")
    if content_type.split(";", 1)[0].strip().lower() != "application/x-www-form-urlencoded":
        raise HTTPException(415, "Form-encoded request required.")
    try:
        parsed = urllib.parse.parse_qs(
            raw.decode("utf-8"), keep_blank_values=True, strict_parsing=True
        )
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(400, "Invalid form data.") from None
    if any(len(values) != 1 for values in parsed.values()):
        raise HTTPException(400, "Duplicate form fields are not supported.")
    return {key: values[0] for key, values in parsed.items()}


def _same_origin_form(request: Request) -> None:
    host = request.headers.get("host", "")
    if not host or request.headers.get("origin") != f"https://{host}":
        raise HTTPException(403, "Same-origin HTTPS form submission required.")


@router.post("/oauth/login")
async def oauth_login(request: Request):
    _same_origin_form(request)
    fields = _parse_form(await request.body(), request.headers.get("content-type", ""))
    flow_id = fields.get("flow_id", "")
    invite = fields.get("invite", "")
    flow = _load_flow(flow_id)
    if not flow or not invite or len(invite) > 200:
        return _login_page(flow_id, "The invitation or sign-in request is invalid or expired.")

    from tradingagents.service.web_access import COOKIE, SESSION_HOURS, db, digest, initialize

    initialize()
    now = datetime.now(UTC)
    session = secrets.token_urlsafe(40)
    with db() as connection, connection.cursor() as cursor:
        cursor.execute(
            """UPDATE shah_invites SET redeemed_at=%s
                WHERE token_hash=%s AND redeemed_at IS NULL AND expires_at>%s
                RETURNING email""",
            (now, digest(invite), now),
        )
        row = cursor.fetchone()
        if not row:
            return _login_page(flow_id, "The invitation is invalid, expired, or already used.")
        cursor.execute(
            "INSERT INTO shah_sessions (token_hash,email,expires_at) VALUES (%s,%s,%s)",
            (digest(session), row[0], now + timedelta(hours=SESSION_HOURS)),
        )
    response = RedirectResponse(
        f"/oauth/authorize?flow={urllib.parse.quote(flow_id)}", status_code=303
    )
    response.set_cookie(
        COOKIE,
        session,
        secure=True,
        httponly=True,
        samesite="strict",
        max_age=SESSION_HOURS * 3600,
        path="/",
    )
    return response


@router.post("/oauth/consent")
async def oauth_consent(request: Request):
    _same_origin_form(request)
    fields = _parse_form(await request.body(), request.headers.get("content-type", ""))
    flow_id = fields.get("flow_id", "")
    decision = fields.get("decision", "allow")
    flow = _load_flow(flow_id)
    if not flow:
        raise HTTPException(400, "This sign-in request expired. Start again from ChatGPT.")
    if decision not in ("allow", "deny"):
        raise HTTPException(400, "Invalid consent decision.")
    from tradingagents.service.web_access import session_email

    try:
        email = session_email(request)
    except HTTPException:
        return _login_page(flow_id, "Your session expired. Sign in again to continue.")
    if decision == "deny":
        _ensure_tables()
        with _db() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM shah_oauth_flows WHERE flow_hash = %s AND expires_at > NOW() RETURNING flow_hash",
                (_digest(flow_id),),
            )
            if not cursor.fetchone():
                raise HTTPException(400, "This sign-in request expired. Start again from ChatGPT.")
        return _redirect_with_error(flow, "access_denied")
    return _finish_authorization(flow_id, email)


@router.post("/oauth/token")
async def token(request: Request) -> JSONResponse:
    fields = _parse_form(await request.body(), request.headers.get("content-type", ""))
    grant_type = fields.get("grant_type")
    client_id = fields.get("client_id", "")
    if not client_id or len(client_id) > 2048:
        return JSONResponse({"error": "invalid_grant"}, status_code=400)

    _ensure_tables()
    with _db() as connection, connection.cursor() as cursor:
        if grant_type == "authorization_code":
            code = fields.get("code", "")
            redirect_uri = fields.get("redirect_uri", "")
            resource = fields.get("resource", "")
            verifier = fields.get("code_verifier", "")
            if (
                not code
                or len(code) > 256
                or not _allowed_redirect_uri(redirect_uri)
                or not _allowed_resource(resource)
                or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
            ):
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
            cursor.execute(
                """DELETE FROM shah_oauth_codes
                    WHERE code_hash=%s AND client_id=%s AND redirect_uri=%s
                      AND code_challenge=%s AND resource=%s AND expires_at>NOW()
                    RETURNING email, resource, scope""",
                (_digest(code), client_id, redirect_uri, challenge, resource),
            )
            row = cursor.fetchone()
            if not row:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            email, resource, scope = row
        elif grant_type == "refresh_token":
            old_refresh_token = fields.get("refresh_token", "")
            requested_resource = fields.get("resource")
            if (
                not old_refresh_token
                or len(old_refresh_token) > 512
                or (requested_resource and not _allowed_resource(requested_resource))
            ):
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            cursor.execute(
                """SELECT email, resource, scope FROM shah_oauth_refresh_tokens
                    WHERE token_hash=%s AND client_id=%s AND expires_at>NOW()
                    FOR UPDATE""",
                (_digest(old_refresh_token), client_id),
            )
            row = cursor.fetchone()
            if not row or (requested_resource and requested_resource != row[1]):
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            scope = _normalize_scope(fields.get("scope", row[2]), allowed=set(str(row[2]).split()))
            if scope is None:
                return JSONResponse({"error": "invalid_scope"}, status_code=400)
            cursor.execute(
                """DELETE FROM shah_oauth_refresh_tokens
                    WHERE token_hash=%s AND client_id=%s AND expires_at>NOW()
                    RETURNING email, resource, scope""",
                (_digest(old_refresh_token), client_id),
            )
            row = cursor.fetchone()
            if not row:
                return JSONResponse({"error": "invalid_grant"}, status_code=400)
            email, resource = row[0], row[1]
        else:
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

        access_token = secrets.token_urlsafe(48)
        cursor.execute(
            """INSERT INTO shah_oauth_access_tokens
                (token_hash, client_id, email, resource, scope, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s)""",
            (
                _digest(access_token),
                client_id,
                email,
                resource,
                scope,
                datetime.now(UTC) + timedelta(seconds=ACCESS_TOKEN_TTL_SECONDS),
            ),
        )
        payload = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_TTL_SECONDS,
            "scope": scope,
        }
        if OFFLINE_ACCESS_SCOPE in scope.split():
            refresh_token = secrets.token_urlsafe(64)
            cursor.execute(
                """INSERT INTO shah_oauth_refresh_tokens
                    (token_hash, client_id, email, resource, scope, expires_at)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    _digest(refresh_token),
                    client_id,
                    email,
                    resource,
                    scope,
                    datetime.now(UTC) + timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS),
                ),
            )
            payload["refresh_token"] = refresh_token

    return JSONResponse(
        payload,
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


def verify_mcp_access_token(access_token: str) -> str | None:
    """Return the authenticated invite identity for a live, correctly scoped token."""
    if not access_token or len(access_token) > 512:
        return None
    try:
        _ensure_tables()
        with _db() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT email, resource, scope FROM shah_oauth_access_tokens
                    WHERE token_hash=%s AND expires_at>NOW()""",
                (_digest(access_token),),
            )
            row = cursor.fetchone()
    except Exception:
        return None
    if not row or not _allowed_resource(row[1]) or RESEARCH_SCOPE not in str(row[2]).split():
        return None
    return str(row[0])


def bearer_challenge() -> str:
    return f'Bearer resource_metadata="{RESOURCE_METADATA_URL}", scope="{RESEARCH_SCOPE}"'

