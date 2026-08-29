from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException, Request
import pytest

from app.api import approvals, auth
from app.services import customer_display_security as display_security


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


def _request(*, host='127.0.0.1', forwarded_for=None, cookie=''):
    headers = []
    if forwarded_for is not None:
        headers.append((b'x-forwarded-for', forwarded_for.encode()))
    if cookie:
        headers.append((b'cookie', cookie.encode()))
    return Request({
        'type': 'http',
        'method': 'GET',
        'path': '/',
        'headers': headers,
        'scheme': 'http',
        'server': ('127.0.0.1', 8100),
        'client': (host, 12345),
        'query_string': b'',
    })


def test_customer_display_polling_persists_presence_at_most_once_per_minute(monkeypatch):
    credential = 'display-secret'
    start = datetime(2026, 8, 29, 10, 0, tzinfo=timezone.utc)
    device = SimpleNamespace(
        credential_hash=display_security._digest(credential),
        is_active=True,
        revoked_at=None,
        expires_at=(start + timedelta(days=1)).isoformat(),
        channel='main',
        last_seen_at=start.isoformat(),
    )

    class Query:
        def filter(self, *_args, **_kwargs):
            return self
        def first(self):
            return device

    class DB:
        def __init__(self):
            self.commits = 0
            self.adds = 0
        def query(self, _model):
            return Query()
        def add(self, _obj):
            self.adds += 1
        def commit(self):
            self.commits += 1

    db = DB()
    now = {'value': start}
    monkeypatch.setattr(display_security, '_now', lambda: now['value'])
    request = _request(cookie=f'{display_security.DISPLAY_COOKIE}={credential}')

    for _ in range(100):
        display_security.require_display_device(db, request, 'main')
    assert db.commits == 0
    assert db.adds == 0

    now['value'] = start + timedelta(seconds=61)
    display_security.require_display_device(db, request, 'main')
    assert db.commits == 1
    assert db.adds == 1

    for _ in range(100):
        display_security.require_display_device(db, request, 'main')
    assert db.commits == 1


def test_auth_throttle_keys_use_ip_normalized_username_and_token_fingerprint(monkeypatch):
    calls = []
    monkeypatch.setattr(auth, 'enforce_rate_limit', lambda key, **kwargs: calls.append((key, kwargs)))
    request = _request(host='127.0.0.1')

    auth._enforce_login_limits(request, '  Manager.User  ')
    keys = [row[0] for row in calls]
    assert 'auth:login:ip:127.0.0.1' in keys
    assert 'auth:login:user:manager.user' in keys
    assert 'auth:login:pair:127.0.0.1:manager.user' in keys

    calls.clear()
    auth._enforce_refresh_limits(request, 'raw-refresh-token')
    keys = [row[0] for row in calls]
    assert 'raw-refresh-token' not in ' '.join(keys)
    assert any(key.startswith('auth:refresh:token:') for key in keys)


def test_manager_approval_credentials_have_endpoint_specific_limits(monkeypatch):
    calls = []
    monkeypatch.setattr(approvals, 'enforce_rate_limit', lambda key, **kwargs: calls.append((key, kwargs)))
    approvals._approval_auth_limits(_request(host='127.0.0.1'), '  OWNER  ')
    keys = [row[0] for row in calls]
    assert 'auth:manager-approval:ip:127.0.0.1' in keys
    assert 'auth:manager-approval:user:owner' in keys
    assert 'auth:manager-approval:pair:127.0.0.1:owner' in keys


def test_proxy_trust_flags_are_not_declared_as_unused_app_settings():
    settings_source = (BACKEND_ROOT / 'app/core/settings.py').read_text()
    sample_source = (REPO_ROOT / '.env.production.example').read_text()
    assert 'trusted_proxy_depth' not in settings_source
    assert 'trust_proxy_headers' not in settings_source
    assert 'TRUSTED_PROXY_DEPTH=' not in sample_source
    assert 'TRUST_PROXY_HEADERS=' not in sample_source


def test_detailed_health_is_local_only_and_public_readiness_is_minimal():
    source = (BACKEND_ROOT / 'app/main.py').read_text()
    assert "@app.get('/internal/healthz/details')" in source
    assert "@app.get('/healthz/details')" not in source
    assert "forwarded_for = (request.headers.get('x-forwarded-for')" in source
    assert "content={'ok': sales_ready, 'sales_ready': sales_ready}" in source
    assert "content={'ok': ok, 'integrations_ready': bool(report.get('integrations_ready'))}" in source


def test_collection_routes_do_not_use_redirecting_root_slash_decorators():
    bad = []
    for path in sorted((BACKEND_ROOT / 'app/api').glob('*.py')):
        source = path.read_text()
        for method in ('get', 'post', 'put', 'patch', 'delete'):
            marker = f"@router.{method}('/')"
            if marker in source:
                bad.append(f'{path.name}:{marker}')
    assert bad == []


def test_certification_uses_local_detailed_health_and_rejects_public_details():
    production = (REPO_ROOT / 'scripts/production-certify.sh').read_text()
    adversarial = (REPO_ROOT / 'scripts/adversarial-production-certify.sh').read_text()
    assert '$BACKEND_BASE/internal/healthz/details' in production
    assert '$PUBLIC_BASE/healthz/details' in production
    assert 'instead of 404' in production
    assert 'http_probe GET "$PUBLIC_BASE/healthz/details" 404' in adversarial
    assert 'http_probe GET "$PUBLIC_BASE/internal/healthz/details" 404' in adversarial
