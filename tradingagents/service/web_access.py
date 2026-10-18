"""Invite-only browser access. Tokens are hashed at rest; never expose owner credentials."""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

router = APIRouter()
_admin_bearer = HTTPBearer(auto_error=False)
COOKIE = "shah_session"
SESSION_HOURS = 12
ADMIN_COOKIE = "shah_owner_session"
ADMIN_SESSION_HOURS = 12
DAILY_LIMIT = 3


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def owner_token_valid(supplied: str) -> bool:
    """Check the owner bearer credential without exposing it to callers."""
    expected = os.environ.get("SHAHTRADINGAGENTS_API_TOKEN", "")
    return bool(expected) and bool(supplied) and secrets.compare_digest(supplied, expected)


def db():
    return psycopg.connect(os.environ["DATABASE_URL"])


def initialize():
    with db() as conn, conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS shah_invites (
            token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
            redeemed_at TIMESTAMPTZ)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS shah_sessions (
            token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS shah_admin_sessions (
            token_hash TEXT PRIMARY KEY, expires_at TIMESTAMPTZ NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS shah_web_usage (
            email TEXT NOT NULL, run_date DATE NOT NULL, used INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (email, run_date))""")
        conn.commit()


def browser_origin(request: Request):
    origin = request.headers.get("origin", "")
    host = request.headers.get("host", "")
    # The browser posts only same-origin JSON; cross-site submissions are rejected.
    if not host or origin != "https://" + host:
        raise HTTPException(403, "Same-origin HTTPS request required.")
    if not request.headers.get("content-type", "").lower().startswith("application/json"):
        raise HTTPException(415, "JSON required.")


def owner(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_admin_bearer)] = None):
    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    if not owner_token_valid(supplied):
        raise HTTPException(401, "Unauthorized")


class InviteRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class RedeemRequest(BaseModel):
    token: str = Field(min_length=24, max_length=200)


class OwnerLoginRequest(BaseModel):
    api_token: str = Field(min_length=24, max_length=512)


@router.post("/admin/invites", dependencies=[Depends(owner)])
def issue_invite(data: InviteRequest, request: Request):
    """Owner generates a one-use invitation; no email is sent automatically."""
    email = data.email.strip().lower()
    if "@" not in email or any(x in email for x in (" ", "/", "\\", "\n")):
        raise HTTPException(400, "Valid invitee email required.")
    token = secrets.token_urlsafe(36)
    expires = datetime.now(UTC) + timedelta(days=7)
    initialize()
    with db() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO shah_invites (token_hash, email, expires_at) VALUES (%s,%s,%s)",
                    (digest(token), email, expires))
        conn.commit()
    base = str(request.base_url).rstrip("/")
    # Fragment keeps invitation secret out of HTTP access logs and referrers.
    return {"email": email, "invite_url": base + "/app#invite=" + token,
            "expires_at": expires.isoformat(), "single_use": True}


@router.post("/admin/revoke", dependencies=[Depends(owner)])
def revoke_access(data: InviteRequest):
    """Revoke outstanding invitations and all sessions for one invitee."""
    email = data.email.strip().lower()
    initialize()
    with db() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM shah_sessions WHERE email=%s", (email,))
        sessions = cur.rowcount
        cur.execute("DELETE FROM shah_invites WHERE email=%s", (email,))
        invites = cur.rowcount
        conn.commit()
    return {"email": email, "sessions_revoked": sessions, "invites_revoked": invites}


@router.post("/web/redeem")
def redeem(data: RedeemRequest, request: Request, response: Response):
    browser_origin(request)
    initialize()
    now = datetime.now(UTC)
    session = secrets.token_urlsafe(40)
    with db() as conn, conn.cursor() as cur:
        cur.execute("""UPDATE shah_invites SET redeemed_at=%s
            WHERE token_hash=%s AND redeemed_at IS NULL AND expires_at>%s
            RETURNING email""", (now, digest(data.token), now))
        row = cur.fetchone()
        if not row:
            raise HTTPException(403, "Invitation invalid, expired, or already redeemed.")
        cur.execute("INSERT INTO shah_sessions (token_hash,email,expires_at) VALUES (%s,%s,%s)",
                    (digest(session), row[0], now + timedelta(hours=SESSION_HOURS)))
        conn.commit()
    response.set_cookie(COOKIE, session, secure=True, httponly=True,
                        samesite="strict", max_age=SESSION_HOURS * 3600, path="/")
    return {"signed_in": True}


def session_email(request: Request) -> str:
    token = request.cookies.get(COOKIE, "")
    if not token:
        raise HTTPException(401, "Invitation sign-in required.")
    initialize()
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT email FROM shah_sessions WHERE token_hash=%s AND expires_at>NOW()",
                    (digest(token),))
        row = cur.fetchone()
    if not row:
        raise HTTPException(401, "Session expired. Request a new invitation.")
    return row[0]


@router.get("/web/me")
def me(request: Request):
    email = session_email(request)
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT used FROM shah_web_usage WHERE email=%s AND run_date=CURRENT_DATE", (email,))
        row = cur.fetchone()
    return {"email": email, "remaining_today": max(0, DAILY_LIMIT - (row[0] if row else 0))}


@router.post("/web/logout")
def logout(request: Request, response: Response):
    browser_origin(request)
    token = request.cookies.get(COOKIE)
    if token:
        with db() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM shah_sessions WHERE token_hash=%s", (digest(token),))
            conn.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"signed_out": True}


def admin_session_valid(request: Request) -> bool:
    token = request.cookies.get(ADMIN_COOKIE, "")
    if not token:
        return False
    initialize()
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM shah_admin_sessions WHERE token_hash=%s AND expires_at>NOW()",
                    (digest(token),))
        return cur.fetchone() is not None


@router.get("/web/admin/me")
def web_admin_me(request: Request):
    return {"owner": admin_session_valid(request)}


@router.post("/web/admin/login")
def web_admin_login(data: OwnerLoginRequest, request: Request, response: Response):
    browser_origin(request)
    if not owner_token_valid(data.api_token):
        raise HTTPException(401, "The Render API key did not match.")
    initialize()
    token = secrets.token_urlsafe(40)
    expires = datetime.now(UTC) + timedelta(hours=ADMIN_SESSION_HOURS)
    with db() as conn, conn.cursor() as cur:
        cur.execute("INSERT INTO shah_admin_sessions (token_hash,expires_at) VALUES (%s,%s)",
                    (digest(token), expires))
        conn.commit()
    response.set_cookie(ADMIN_COOKIE, token, secure=True, httponly=True,
                        samesite="strict", max_age=ADMIN_SESSION_HOURS * 3600, path="/")
    return {"owner": True, "expires_at": expires.isoformat()}


@router.post("/web/admin/logout")
def web_admin_logout(request: Request, response: Response):
    browser_origin(request)
    token = request.cookies.get(ADMIN_COOKIE, "")
    if token:
        with db() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM shah_admin_sessions WHERE token_hash=%s", (digest(token),))
            conn.commit()
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return {"signed_out": True}


@router.post("/web/admin/invites")
def web_admin_issue_invite(data: InviteRequest, request: Request):
    browser_origin(request)
    if not admin_session_valid(request):
        raise HTTPException(401, "Unlock owner tools first.")
    return issue_invite(data, request)


def consume_quota(email: str):
    """Atomic per-identity daily quota; prevents unrestricted model spending."""
    with db() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO shah_web_usage (email,run_date,used)
            VALUES (%s,CURRENT_DATE,0) ON CONFLICT DO NOTHING""", (email,))
        cur.execute("""UPDATE shah_web_usage SET used=used+1
            WHERE email=%s AND run_date=CURRENT_DATE AND used < %s RETURNING used""",
            (email, DAILY_LIMIT))
        if not cur.fetchone():
            raise HTTPException(429, "Daily analysis limit reached.")
        conn.commit()


@router.post("/web/analyze")
def web_analyze(data: dict, request: Request):
    browser_origin(request)
    email = session_email(request)
    from tradingagents.service.api import AnalyzeRequest, execute_analysis
    try:
        payload = AnalyzeRequest.model_validate(data)
    except Exception:
        raise HTTPException(422, "Invalid analysis request.") from None
    # Prevent file output, historical lookahead, excessive analyst fanout and costs.
    if len(payload.analysts) > 7:
        raise HTTPException(400, "Too many analysts.")
    payload.save_reports = False
    payload.checkpoint = False
    consume_quota(email)
    result = execute_analysis(payload)
    state = result.final_state
    return {"ticker": result.ticker, "trade_date": result.trade_date,
            "signal": result.signal, "analysts": result.analysts,
            "reports": {key: state.get(key, "") for key in (
                "market_report", "sentiment_report", "news_report", "fundamentals_report",
                "flow_report", "oi_report", "dealer_positioning_report", "evidence_report",
                "final_trade_decision")}}


@router.get("/app", response_class=HTMLResponse)
def dashboard():
    from importlib.resources import files
    page = files("tradingagents.service").joinpath("dashboard.html").read_text()
    return HTMLResponse(page, headers={
        "Cache-Control": "no-store",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
    })
