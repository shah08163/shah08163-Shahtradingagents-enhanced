from unittest.mock import MagicMock

import pytest

from tradingagents.service import auth_store


@pytest.mark.parametrize('tokens,expected', [
    (None, 'NO_STORED_SIGN_IN'),
    ({'expires_at': 0}, 'EXPIRED_REAUTH_REQUIRED'),
    ({'expires_at': 0, 'refresh_token': 'secret'}, 'EXPIRED_REFRESH_REQUIRED'),
    ({'expires_at': 99999999999, 'access_token': 'secret'}, 'PRESENT_NOT_MODEL_VERIFIED'),
    ({'access_token': 'secret'}, 'MALFORMED_STORED_SIGN_IN'),
])
def test_status_never_exposes_credentials(monkeypatch, tokens, expected):
    monkeypatch.setattr(auth_store, '_installed', False)
    monkeypatch.setattr(auth_store.chatgpt_auth, '_read', lambda: {'tokens': tokens})
    result = auth_store.model_auth_status()
    assert result['state'] == expected
    assert 'secret' not in str(result)
    assert set(result) == {'storage', 'state'}


def test_storage_failure_distinguished(monkeypatch):
    monkeypatch.setattr(auth_store, '_connect', lambda: (_ for _ in ()).throw(RuntimeError('sensitive')))
    assert auth_store._postgres_read() == {}
    assert auth_store._last_read_status == 'STORE_UNAVAILABLE'


def test_unreadable_encrypted_record_distinguished(monkeypatch):
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (b'broken',)
    manager = MagicMock()
    manager.__enter__.return_value = connection
    monkeypatch.setattr(auth_store, '_connect', lambda: manager)
    monkeypatch.setattr(auth_store, '_ensure_table', lambda c: None)
    monkeypatch.setattr(auth_store, '_decrypt', lambda p: (_ for _ in ()).throw(ValueError('sensitive')))
    assert auth_store._postgres_read() == {}
    assert auth_store._last_read_status == 'STORED_SIGN_IN_UNREADABLE'


@pytest.mark.parametrize('message,state', [
    ('renew invalid_grant secret', 'REFRESH_GRANT_REJECTED'),
    ('Could not reach OpenAI secret', 'AUTH_PROVIDER_UNREACHABLE'),
    ('unrecognized secret', 'AUTH_RENEWAL_FAILED'),
])
def test_renewal_errors_are_allowlisted(monkeypatch, message, state):
    def fail():
        raise auth_store.chatgpt_auth.ChatGPTAuthError(message)
    monkeypatch.setattr(auth_store.chatgpt_auth, 'access_token', fail)
    result = auth_store.renew_model_auth()
    assert result['state'] == state
    assert 'secret' not in str(result)


def test_renewal_never_returns_token(monkeypatch):
    monkeypatch.setattr(auth_store.chatgpt_auth, 'access_token', lambda: 'secret-token')
    assert auth_store.renew_model_auth() == {'state': 'TOKEN_AVAILABLE_NOT_MODEL_VERIFIED'}
