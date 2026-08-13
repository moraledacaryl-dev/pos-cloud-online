from datetime import datetime, timedelta, timezone
import hashlib
import uuid
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.settings import looks_like_placeholder_secret, settings
from app.models.entities import RefreshToken, User
from app.services.permission_service import assign_user_roles, ensure_permissions_seed, list_roles

pwd_context = CryptContext(schemes=['pbkdf2_sha256'], deprecated='auto')
ALGORITHM = 'HS256'


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_access_token(subject: str, session_version: int = 1) -> str:
    now = _utc_now()
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        'sub': subject,
        'exp': expire,
        'typ': 'access',
        'iat': int(now.timestamp()),
        'sv': int(session_version or 1),
        'jti': str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def create_refresh_token(db: Session, user: User, user_agent: str | None = None, ip_address: str | None = None) -> str:
    token = str(uuid.uuid4())
    expire = _utc_now() + timedelta(days=settings.refresh_token_expire_days)
    row = RefreshToken(
        token_uuid=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=_token_hash(token),
        expires_at=expire.replace(microsecond=0).isoformat(),
        session_version=int(user.session_version or 1),
        user_agent=user_agent,
        ip_address=ip_address,
    )
    db.add(row)
    db.commit()
    return token


def _revoke_refresh_row(db: Session, row: RefreshToken):
    row.revoked_at = _iso_now()
    db.add(row)


def rotate_refresh_token(db: Session, token: str, user_agent: str | None = None, ip_address: str | None = None):
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == _token_hash(token), RefreshToken.revoked_at.is_(None)).first()
    if not row:
        return None
    expires = _parse_iso(row.expires_at)
    if not expires or expires < _utc_now():
        _revoke_refresh_row(db, row)
        db.commit()
        return None
    user = db.get(User, row.user_id)
    if not user or not user.is_active:
        _revoke_refresh_row(db, row)
        db.commit()
        return None
    if int(row.session_version or 1) != int(user.session_version or 1):
        _revoke_refresh_row(db, row)
        db.commit()
        return None
    forced_after = _parse_iso(getattr(user, 'force_logout_after_text', None))
    created_at = row.created_at
    if forced_after and created_at is not None:
        if getattr(created_at, 'tzinfo', None) is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at <= forced_after:
            _revoke_refresh_row(db, row)
            db.commit()
            return None
    _revoke_refresh_row(db, row)
    db.commit()
    return {'user': user, 'refresh_token': create_refresh_token(db, user, user_agent=user_agent, ip_address=ip_address)}


def revoke_refresh_token(db: Session, token: str):
    row = db.query(RefreshToken).filter(RefreshToken.token_hash == _token_hash(token), RefreshToken.revoked_at.is_(None)).first()
    if row:
        _revoke_refresh_row(db, row)
        db.commit()
    return {'ok': True}


def revoke_all_sessions(db: Session, user: User | int, reason: str | None = None):
    target = user if isinstance(user, User) else db.get(User, int(user))
    if not target:
        return {'ok': False, 'revoked_tokens': 0}
    target.session_version = int(target.session_version or 1) + 1
    target.force_logout_after_text = _iso_now()
    active_tokens = db.query(RefreshToken).filter(RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None)).all()
    for row in active_tokens:
        row.revoked_at = target.force_logout_after_text
        db.add(row)
    db.add(target)
    db.commit()
    return {'ok': True, 'revoked_tokens': len(active_tokens), 'reason': reason, 'session_version': target.session_version, 'force_logout_after_text': target.force_logout_after_text}


def authenticate_user(db: Session, username: str, password: str):
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def ensure_admin_user(db: Session):
    if not settings.bootstrap_enabled:
        raise RuntimeError('Development admin bootstrap is disabled.')
    username = (settings.development_admin_username or '').strip()
    password = settings.development_admin_password or ''
    if not username:
        raise RuntimeError('DEVELOPMENT_ADMIN_USERNAME is required when development bootstrap is enabled.')
    if looks_like_placeholder_secret(password) or password.lower() == username.lower():
        raise RuntimeError('DEVELOPMENT_ADMIN_PASSWORD must be an explicit non-placeholder password.')

    ensure_permissions_seed(db)
    admin = db.query(User).filter(User.username == username).first()
    if not admin:
        admin = User(username=username, full_name='Development Admin', hashed_password=hash_password(password), role='owner', is_active=True, session_version=1)
        db.add(admin)
        db.commit()
        db.refresh(admin)
    roles = list_roles(db)
    owner_role = next((row for row in roles if row.get('code') == 'owner'), None)
    if owner_role:
        assign_user_roles(db, admin.id, [owner_role['id']])
    return admin
