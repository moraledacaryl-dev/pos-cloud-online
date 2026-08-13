import inspect

import pytest
from fastapi import HTTPException, Request, Response

from app.api import auth, deps
from app.services.browser_auth import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    set_browser_auth_cookies,
    validate_browser_csrf,
)


def _request(*, method='POST', path='/api/orders', cookie='', csrf='', origin='https://pos.hiddenoasis.app'):
    headers = []
    if cookie:
        headers.append((b'cookie', cookie.encode()))
    if csrf:
        headers.append((b'x-csrf-token', csrf.encode()))
    if origin:
        headers.append((b'origin', origin.encode()))
    return Request({'type': 'http', 'method': method, 'path': path, 'headers': headers, 'scheme': 'https', 'server': ('pos.hiddenoasis.app', 443), 'client': ('127.0.0.1', 1), 'query_string': b''})


def test_browser_session_cookies_have_expected_security_flags(monkeypatch):
    monkeypatch.setattr('app.services.browser_auth.settings.environment', 'production')
    response = Response()
    set_browser_auth_cookies(response, 'access-value', 'refresh-value', 'csrf-value')
    cookies = [value.decode() for key, value in response.raw_headers if key.lower() == b'set-cookie']
    access = next(row for row in cookies if row.startswith(f'{ACCESS_COOKIE}='))
    refresh = next(row for row in cookies if row.startswith(f'{REFRESH_COOKIE}='))
    csrf = next(row for row in cookies if row.startswith(f'{CSRF_COOKIE}='))
    assert 'HttpOnly' in access and 'Secure' in access and 'SameSite=lax' in access
    assert 'HttpOnly' in refresh and 'Secure' in refresh and 'SameSite=strict' in refresh and 'Path=/api/auth' in refresh
    assert 'HttpOnly' not in csrf and 'Secure' in csrf and 'SameSite=strict' in csrf


def test_cookie_authenticated_mutation_requires_matching_csrf(monkeypatch):
    monkeypatch.setattr('app.services.browser_auth.settings.environment', 'production')
    monkeypatch.setattr('app.services.browser_auth.settings.cors_origins', 'https://pos.hiddenoasis.app')
    request = _request(cookie=f'{ACCESS_COOKIE}=abc; {CSRF_COOKIE}=expected', csrf='wrong')
    with pytest.raises(HTTPException, match='CSRF'):
        validate_browser_csrf(request)


def test_cookie_authenticated_mutation_accepts_matching_csrf(monkeypatch):
    monkeypatch.setattr('app.services.browser_auth.settings.environment', 'production')
    monkeypatch.setattr('app.services.browser_auth.settings.cors_origins', 'https://pos.hiddenoasis.app')
    request = _request(cookie=f'{ACCESS_COOKIE}=abc; {CSRF_COOKIE}=expected', csrf='expected')
    validate_browser_csrf(request)


def test_cookie_authenticated_cross_origin_mutation_is_rejected(monkeypatch):
    monkeypatch.setattr('app.services.browser_auth.settings.environment', 'production')
    monkeypatch.setattr('app.services.browser_auth.settings.cors_origins', 'https://pos.hiddenoasis.app')
    request = _request(cookie=f'{ACCESS_COOKIE}=abc; {CSRF_COOKIE}=expected', csrf='expected', origin='https://evil.example')
    with pytest.raises(HTTPException, match='Cross-origin'):
        validate_browser_csrf(request)


def test_auth_dependency_supports_browser_cookie_and_bearer_fallback():
    source = inspect.getsource(deps.get_current_user)
    assert 'browser_access_token(request)' in source
    assert 'bearer_token' in source


def test_strict_browser_login_does_not_need_refresh_token_request_body():
    assert 'payload: RefreshTokenPayload | None = None' in inspect.getsource(auth.refresh)
    assert 'browser_refresh_token(request)' in inspect.getsource(auth.refresh)
