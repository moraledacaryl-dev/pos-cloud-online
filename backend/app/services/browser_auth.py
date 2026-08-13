from __future__ import annotations

import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response

from app.core.settings import settings

ACCESS_COOKIE = 'pos_access'
REFRESH_COOKIE = 'pos_refresh'
CSRF_COOKIE = 'pos_csrf'
CSRF_HEADER = 'x-csrf-token'
UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
CSRF_EXEMPT_PATHS = {'/api/auth/login', '/api/auth/bootstrap'}


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_browser_auth_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str | None = None) -> str:
    csrf = csrf_token or issue_csrf_token()
    secure = settings.is_strict_environment
    response.set_cookie(ACCESS_COOKIE, access_token, max_age=max(60, settings.access_token_expire_minutes * 60), httponly=True, secure=secure, samesite='lax', path='/')
    response.set_cookie(REFRESH_COOKIE, refresh_token, max_age=max(3600, settings.refresh_token_expire_days * 86400), httponly=True, secure=secure, samesite='strict', path='/api/auth')
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max(3600, settings.refresh_token_expire_days * 86400), httponly=False, secure=secure, samesite='strict', path='/')
    return csrf


def clear_browser_auth_cookies(response: Response) -> None:
    secure = settings.is_strict_environment
    response.delete_cookie(ACCESS_COOKIE, path='/', secure=secure, samesite='lax')
    response.delete_cookie(REFRESH_COOKIE, path='/api/auth', secure=secure, samesite='strict')
    response.delete_cookie(CSRF_COOKIE, path='/', secure=secure, samesite='strict')


def browser_refresh_token(request: Request) -> str:
    return str(request.cookies.get(REFRESH_COOKIE) or '').strip()


def browser_access_token(request: Request) -> str:
    return str(request.cookies.get(ACCESS_COOKIE) or '').strip()


def _origin_allowed(request: Request) -> bool:
    origin = (request.headers.get('origin') or '').strip()
    referer = (request.headers.get('referer') or '').strip()
    if not origin and not referer:
        return False
    allowed = {value.rstrip('/') for value in settings.cors_origin_list if value.strip()}
    candidate = origin.rstrip('/') if origin else ''
    if not candidate and referer:
        parsed = urlsplit(referer)
        candidate = f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')
    return candidate in allowed


def validate_browser_csrf(request: Request) -> None:
    if request.method.upper() not in UNSAFE_METHODS or not request.url.path.startswith(settings.api_prefix) or request.url.path in CSRF_EXEMPT_PATHS:
        return
    if not (request.cookies.get(ACCESS_COOKIE) or request.cookies.get(REFRESH_COOKIE)):
        return
    if settings.is_strict_environment and not _origin_allowed(request):
        raise HTTPException(status_code=403, detail='Cross-origin mutation rejected')
    cookie_token = str(request.cookies.get(CSRF_COOKIE) or '')
    header_token = str(request.headers.get(CSRF_HEADER) or '')
    if not cookie_token or not header_token or not secrets.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=403, detail='CSRF validation failed')
