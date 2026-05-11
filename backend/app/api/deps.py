from datetime import datetime, timezone

from jose import JWTError, jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.db.database import get_db
from app.models.entities import User
from app.services.permission_service import get_user_permission_keys

oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/api/auth/login')


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail='Could not validate credentials')
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
        username = payload.get('sub')
        token_type = payload.get('typ')
        token_sv = int(payload.get('sv') or 1)
        issued_at = int(payload.get('iat') or 0)
        if not username or token_type != 'access':
            raise credentials_exception
    except Exception:
        raise credentials_exception
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        raise credentials_exception
    if int(user.session_version or 1) != token_sv:
        raise credentials_exception
    forced_after = _parse_iso(getattr(user, 'force_logout_after_text', None))
    if forced_after is not None and issued_at and issued_at <= int(forced_after.timestamp()):
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
