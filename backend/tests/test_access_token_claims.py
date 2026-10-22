"""Regression tests for signed access-token claim and revocation requirements.

Tokens, users and database are synthetic. No application credentials or
production records are read or modified.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api import deps
from app.db.database import Base
from app.models.entities import User
from app.services import auth_service
from app.services.browser_auth import ACCESS_COOKIE


def _request(cookie=''):
    headers = [(b'cookie', f'{ACCESS_COOKIE}={cookie}'.encode())] if cookie else []
    return Request({
        'type': 'http',
        'method': 'GET',
        'path': '/api/auth/me',
        'headers': headers,
        'scheme': 'https',
        'server': ('pos.hiddenoasis.app', 443),
        'client': ('127.0.0.1', 1),
        'query_string': b'',
    })


@pytest.fixture
def security_env(monkeypatch):
    monkeypatch.setattr(deps.settings, 'secret_key', 'group11-test-only-strong-jwt-signing-key-not-production')
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as db:
        user = User(
            username='group11-cashier', hashed_password='synthetic-not-a-real-password',
            role='cashier', is_active=True, session_version=1,
        )
        db.add(user)
        db.commit()
        yield db, user
    engine.dispose()


def _claims(**updates):
    now = int(datetime.now(timezone.utc).timestamp())
    payload = {
        'sub': 'group11-cashier',
        'typ': 'access',
        'iat': now - 10,
        'exp': now + 180,
        'sv': 1,
        'jti': 'synthetic-jwt',
    }
    payload.update(updates)
    return payload


def _signed(payload):
    return jwt.encode(payload, deps.settings.secret_key, algorithm='HS256')


def _validate(db, token, *, cookie=False):
    return deps.get_current_user(
        _request(token if cookie else ''),
        db=db,
        bearer_token=None if cookie else token,
    )


def test_real_issued_access_token_is_accepted_with_bearer_or_cookie(security_env):
    db, user = security_env
    token = auth_service.create_access_token(user.username, user.session_version)
    assert _validate(db, token).id == user.id
    assert _validate(db, token, cookie=True).id == user.id


@pytest.mark.parametrize('claim', ['exp', 'iat', 'sv', 'typ', 'sub'])
def test_signed_access_token_missing_required_claim_is_rejected(security_env, claim):
    db, _ = security_env
    payload = _claims()
    del payload[claim]
    with pytest.raises(HTTPException) as err:
        _validate(db, _signed(payload))
    assert err.value.status_code == 401


@pytest.mark.parametrize('overrides', [
    {'iat': 0},
    {'iat': '1000000000'},
    {'iat': True},
    {'exp': '3000000000'},
    {'exp': True},
    {'sv': 0},
    {'sv': True},
    {'sv': '1'},
    {'typ': 'refresh'},
    {'sub': '  '},
])
def test_signed_access_token_invalid_metadata_is_rejected(security_env, overrides):
    db, _ = security_env
    with pytest.raises(HTTPException) as err:
        _validate(db, _signed(_claims(**overrides)))
    assert err.value.status_code == 401


def test_expired_and_future_issued_tokens_are_rejected(security_env):
    db, _ = security_env
    now = int(datetime.now(timezone.utc).timestamp())
    with pytest.raises(HTTPException) as expired:
        _validate(db, _signed(_claims(iat=now-120, exp=now-60)))
    assert expired.value.status_code == 401
    with pytest.raises(HTTPException) as immature:
        _validate(db, _signed(_claims(iat=now+120, exp=now+240)))
    assert immature.value.status_code == 401


def test_forced_logout_cutoff_does_not_accept_old_signed_token(security_env):
    db, user = security_env
    now = datetime.now(timezone.utc).replace(microsecond=0)
    user.force_logout_after_text = (now - timedelta(seconds=60)).isoformat()
    db.add(user)
    db.commit()
    old_issued_at = int((now - timedelta(seconds=120)).timestamp())
    stale = _signed(_claims(iat=old_issued_at))
    with pytest.raises(HTTPException) as err:
        _validate(db, stale)
    assert err.value.status_code == 401
    assert _validate(db, _signed(_claims(iat=int(now.timestamp())))).id == user.id


def test_access_token_session_version_and_active_user_required(security_env):
    db, user = security_env
    stale_version = _signed(_claims(sv=2))
    with pytest.raises(HTTPException) as wrong_session:
        _validate(db, stale_version)
    assert wrong_session.value.status_code == 401
    user.is_active = False
    db.commit()
    with pytest.raises(HTTPException) as disabled:
        _validate(db, _signed(_claims()))
    assert disabled.value.status_code == 401
