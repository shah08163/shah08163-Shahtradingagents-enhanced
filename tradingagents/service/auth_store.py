"""Persistent ChatGPT auth storage for stateless service deployments.

When ``DATABASE_URL`` is configured, this module replaces TradingAgents'
file-backed auth read/write helpers with an encrypted single-row Postgres store.
The API bearer secret is used only as key material; plaintext OAuth credentials
are never written to the database.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from tradingagents.llm_clients import chatgpt_auth

DATABASE_URL_ENV = "DATABASE_URL"
API_TOKEN_ENV = "SHAHTRADINGAGENTS_API_TOKEN"
_RECORD_KEY = "chatgpt-auth"
_ASSOCIATED_DATA = b"shah-tradingagents:chatgpt-auth:v1"
_install_lock = threading.Lock()
_installed = False


def _encryption_key() -> bytes:
    secret = os.environ.get(API_TOKEN_ENV)
    if not secret:
        raise RuntimeError(f"{API_TOKEN_ENV} is required for encrypted auth storage.")
    return hashlib.sha256(("auth-store:v1:" + secret).encode("utf-8")).digest()


def _connect():
    import psycopg

    database_url = os.environ.get(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured.")
    return psycopg.connect(database_url)


def _ensure_table(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS shah_tradingagents_secrets (
                key TEXT PRIMARY KEY,
                payload BYTEA NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    connection.commit()


def _encrypt(data: dict) -> bytes:
    nonce = os.urandom(12)
    plaintext = json.dumps(data, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, plaintext, _ASSOCIATED_DATA)
    return nonce + ciphertext


def _decrypt(payload: bytes) -> dict:
    if len(payload) < 13:
        return {}
    nonce, ciphertext = payload[:12], payload[12:]
    plaintext = AESGCM(_encryption_key()).decrypt(nonce, ciphertext, _ASSOCIATED_DATA)
    value = json.loads(plaintext.decode("utf-8"))
    return value if isinstance(value, dict) else {}


def _postgres_read() -> dict:
    try:
        with _connect() as connection:
            _ensure_table(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload FROM shah_tradingagents_secrets WHERE key = %s",
                    (_RECORD_KEY,),
                )
                row = cursor.fetchone()
        return _decrypt(bytes(row[0])) if row else {}
    except Exception:
        # Match the upstream file-backed reader's fail-closed behavior: an
        # unavailable/corrupt store means no usable sign-in, never guessed data.
        return {}


def _postgres_write(data: dict) -> None:
    payload = _encrypt(data)
    with _connect() as connection:
        _ensure_table(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO shah_tradingagents_secrets (key, payload, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE
                SET payload = EXCLUDED.payload, updated_at = NOW()
                """,
                (_RECORD_KEY, payload),
            )
        connection.commit()


def install_postgres_auth_store() -> bool:
    """Use Postgres for ChatGPT auth when DATABASE_URL is configured.

    Returns True when Postgres storage is active, False when the normal local
    file store remains in use.
    """
    global _installed
    if not os.environ.get(DATABASE_URL_ENV):
        return False
    with _install_lock:
        if _installed:
            return True
        chatgpt_auth._read = _postgres_read
        chatgpt_auth._write = _postgres_write
        _installed = True
    return True
