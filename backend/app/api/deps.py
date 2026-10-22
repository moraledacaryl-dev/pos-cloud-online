from datetime import datetime

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.database import get_db
from app.models.entities import User
from app.services.browser_auth import browser_access_token
from app.services.permission_service import get_user_permission_keys

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login', auto_error=False)


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def get_current_user(request: Request, db: Session = Depends(get_db), bearer_token: str | None = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail='Could not validate credentials')
    token = browser_access_token(request) or str(bearer_token or '').strip()
    if not token:
        raise credentials_exception
    try:
        # PyJWT verifies supplied temporal claims but does not require them
        # unless explicitly configured. Never accept access tokens lacking
        # expiry or issue-time metadata, particularly after forced logout.
        payload = jwt.decode(
            token, settings.secret_key, algorithms=['HS256'],
            options={'require': ['sub', 'exp', 'iat', 'typ', 'sv']},
        )
        username = payload.get('sub')
        token_type = payload.get('typ')
        issued_at = payload.get('iat')
        expiry = payload.get('exp')
        token_sv = payload.get('sv')
        if (
            not isinstance(username, str) or not username.strip()
            or token_type != 'access'
            or type(issued_at) is not int or issued_at <= 0
            or type(expiry) is not int or expiry <= issued_at
            or type(token_sv) is not int or token_sv <= 0
        ):
            raise credentials_exception
    except Exception:
        raise credentials_exception
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        raise credentials_exception
    if int(user.session_version or 1) != token_sv:
        raise credentials_exception
    forced_after = _parse_iso(getattr(user, 'force_logout_after_text', None))
    if forced_after is not None and issued_at <= int(forced_after.timestamp()):
        raise credentials_exception
    return user


def require_permissions(*permission_keys):
    def inner(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        if not permission_keys:
            return user
        effective = get_user_permission_keys(db, user)
        missing = [key for key in permission_keys if key not in effective and '*' not in effective]
        if missing:
            raise HTTPException(status_code=403, detail=f"Missing permissions: {', '.join(missing)}")
        return user
    return inner


def require_any_permissions(*permission_keys):
    def inner(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
        if not permission_keys:
            return user
        effective = get_user_permission_keys(db, user)
        if '*' in effective:
            return user
        if any(key in effective for key in permission_keys):
            return user
        raise HTTPException(status_code=403, detail=f"Missing any of permissions: {', '.join(permission_keys)}")
    return inner
