"""Browser-assisted ChatGPT sign-in for remote service deployments.

The upstream CLI login uses a localhost callback and terminal paste fallback.
This module exposes the same PKCE flow as two API steps: start the flow, then
paste the final localhost callback URL into the protected completion endpoint.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
import urllib.parse
from dataclasses import dataclass

from tradingagents.llm_clients import chatgpt_auth

_ATTEMPT_TTL = 600
_pending_lock = threading.Lock()
_pending: dict[str, "PendingLogin"] = {}


@dataclass(frozen=True)
class PendingLogin:
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    client_id: str
    host_id: str
    existing_account: dict
    expires_at: float


def _cleanup(now: float) -> None:
    expired = [state for state, attempt in _pending.items() if attempt.expires_at <= now]
    for state in expired:
        _pending.pop(state, None)


def begin_sign_in() -> str:
    data = chatgpt_auth._read()
    host_id = chatgpt_auth._host_id(data)
    account = data.get("account") or {}
    client_id = account.get("client_id") or chatgpt_auth.DYNAMIC_CLIENT_ID
    state = chatgpt_auth._b64url(secrets.token_bytes(32))
    nonce = chatgpt_auth._b64url(secrets.token_bytes(32))
    verifier = chatgpt_auth._b64url(secrets.token_bytes(64))
    redirect_uri = f"http://127.0.0.1:{chatgpt_auth.DEFAULT_PORT}{chatgpt_auth.CALLBACK_PATH}"

    params = {
        "client_id": client_id,
        "ext_agent_host_id": host_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": chatgpt_auth.SCOPE,
        "resource": chatgpt_auth.API_BASE,
        "state": state,
        "nonce": nonce,
        "code_challenge_method": "S256",
        "code_challenge": chatgpt_auth._b64url(hashlib.sha256(verifier.encode()).digest()),
    }
    if client_id == chatgpt_auth.DYNAMIC_CLIENT_ID:
        params["agent_name_hint"] = chatgpt_auth.APP_NAME
    elif account.get("email"):
        params["login_hint"] = account["email"]

    now = time.time()
    attempt = PendingLogin(
        state=state,
        nonce=nonce,
        verifier=verifier,
        redirect_uri=redirect_uri,
        client_id=client_id,
        host_id=host_id,
        existing_account=account,
        expires_at=now + _ATTEMPT_TTL,
    )
    with _pending_lock:
        _cleanup(now)
        _pending[state] = attempt

    return (
        f"{chatgpt_auth.AUTHORIZE_URL}?"
        f"{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"
    )


def complete_sign_in(callback_url: str) -> None:
    parsed = urllib.parse.urlparse(callback_url.strip())
    params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
    callback_path = parsed.path.rstrip("/") or "/"
    expected_path = chatgpt_auth.CALLBACK_PATH.rstrip("/") or "/"
    if callback_path != expected_path:
        raise chatgpt_auth.ChatGPTAuthError("That is not a TradingAgents ChatGPT callback URL.")

    state = params.get("state") or ""
    now = time.time()
    with _pending_lock:
        _cleanup(now)
        attempt = _pending.pop(state, None)
    if not attempt:
        raise chatgpt_auth.ChatGPTAuthError("This ChatGPT sign-in attempt is missing or expired; start again.")
    if params.get("error"):
        raise chatgpt_auth.ChatGPTAuthError(
            f"ChatGPT sign-in was not completed ({params['error']})."
        )

    issued = params.get("client_id") or attempt.client_id
    account = attempt.existing_account
    if issued == chatgpt_auth.DYNAMIC_CLIENT_ID or (
        account.get("client_id") and issued != account["client_id"]
    ):
        raise chatgpt_auth.ChatGPTAuthError(
            "ChatGPT sign-in did not register TradingAgents; start the sign-in again."
        )

    keys = chatgpt_auth._signing_keys()
    body = chatgpt_auth._token_request(
        {
            "grant_type": "authorization_code",
            "client_id": issued,
            "code": params.get("code", ""),
            "code_verifier": attempt.verifier,
            "redirect_uri": attempt.redirect_uri,
            "resource": chatgpt_auth.API_BASE,
        },
        "sign you in to ChatGPT",
        "sign in again",
    )
    claims = chatgpt_auth._validated_claims(
        body.get("id_token") or "", issued, attempt.nonce, keys
    )
    if account.get("subject") and claims["sub"] != account["subject"]:
        raise chatgpt_auth.ChatGPTAuthError(
            "This deployment is already associated with another ChatGPT account."
        )
    if chatgpt_auth.PLAN_SCOPE not in (body.get("scope") or "").split():
        raise chatgpt_auth.ChatGPTAuthError(
            "ChatGPT did not allow TradingAgents to use the signed-in plan."
        )

    replaced = chatgpt_auth._read().get("tokens")
    chatgpt_auth._write(
        {
            "host_id": attempt.host_id,
            "account": {
                "client_id": issued,
                "email": claims.get("email"),
                "subject": claims["sub"],
            },
            "tokens": chatgpt_auth._token_record(body, time.time()),
        }
    )
    if replaced:
        chatgpt_auth._revoke(replaced, issued)
