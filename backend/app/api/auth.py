from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permissions
from app.core.settings import settings
from app.db.database import get_db
from app.models.entities import Role, User
from app.schemas.common import LoginPayload, RefreshTokenPayload, UserCreate, UserUpdate
from app.services.audit_service import write_audit_log
from app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    ensure_admin_user,
    hash_password,
    revoke_all_sessions,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.services.permission_service import assign_user_roles, get_user_effective_permissions, get_user_permission_keys, get_user_roles, list_permissions, list_roles
from app.services.security_admin_policy import (
    is_privileged_role_name,
    role_codes_include_owner,
    safe_user_security_audit_details,
    validate_user_admin_change,
)

router = APIRouter()


def _user_payload(db: Session, user: User):
    perms = get_user_effective_permissions(db, user.id)
    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'role': user.role,
        'is_active': user.is_active,
        'session_version': int(user.session_version or 1),
        'force_logout_after_text': user.force_logout_after_text,
        'roles': perms.get('roles', {}).get('roles', []),
        'permissions': perms.get('permissions', []),
    }


def _role_codes_for_ids(db: Session, role_ids) -> list[str]:
    ids = [int(value) for value in (role_ids or [])]
    if not ids:
        return []
    return [str(row.code or '').strip().lower() for row in db.query(Role).filter(Role.id.in_(ids)).all()]


def _is_superuser(db: Session, user: User) -> bool:
    return is_privileged_role_name(user.role) or '*' in get_user_permission_keys(db, user)


def _target_is_superuser(db: Session, user: User) -> bool:
    roles = get_user_roles(db, user.id)
    return is_privileged_role_name(user.role) or role_codes_include_owner([row.get('code') for row in roles.get('roles', [])])


def _security_audit(db: Session, *, action: str, actor: User, target: User, details: dict):
    write_audit_log(
        db,
        action=action,
        entity_type='user',
        entity_id=target.id,
        actor_user_id=actor.id,
        actor_username=actor.username,
        details={'target_username': target.username, **details},
    )


def _validate_or_403(**kwargs):
    try:
        validate_user_admin_change(**kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post('/bootstrap')
def bootstrap(db: Session = Depends(get_db)):
    if not settings.bootstrap_enabled:
        raise HTTPException(status_code=403, detail='Default admin bootstrap is disabled in this environment')
    ensure_admin_user(db)
    return {'ok': True, 'default_admin': 'admin', 'default_password': 'admin123'}


@router.post('/login')
def login(payload: LoginPayload, request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail='Incorrect username or password')
    return {
        'access_token': create_access_token(user.username, session_version=int(user.session_version or 1)),
        'refresh_token': create_refresh_token(db, user, user_agent=request.headers.get('user-agent'), ip_address=request.client.host if request.client else None),
        'token_type': 'bearer',
        'user': _user_payload(db, user),
    }


@router.post('/refresh')
def refresh(payload: RefreshTokenPayload, request: Request, db: Session = Depends(get_db)):
    rotated = rotate_refresh_token(db, payload.refresh_token, user_agent=request.headers.get('user-agent'), ip_address=request.client.host if request.client else None)
    if not rotated:
        raise HTTPException(status_code=401, detail='Refresh token is invalid or expired')
    user = rotated['user']
    return {
        'access_token': create_access_token(user.username, session_version=int(user.session_version or 1)),
        'refresh_token': rotated['refresh_token'],
        'token_type': 'bearer',
        'user': _user_payload(db, user),
    }


@router.post('/logout')
def logout(payload: RefreshTokenPayload, db: Session = Depends(get_db)):
    return revoke_refresh_token(db, payload.refresh_token)


@router.post('/logout-all')
def logout_all(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = revoke_all_sessions(db, current_user, reason='user_logout_all')
    _security_audit(db, action='security.sessions_revoked_self', actor=current_user, target=current_user, details={})
    return result


@router.post('/users/{user_id}/force-logout')
def force_logout_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_permissions('users.manage'))):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail='User not found')
    _validate_or_403(
        actor_user_id=user.id,
        target_user_id=target.id,
        actor_is_superuser=_is_superuser(db, user),
        target_is_superuser=_target_is_superuser(db, target),
        sensitive_fields_present=True,
    )
    result = revoke_all_sessions(db, target, reason=f'forced_by:{user.username}')
    _security_audit(db, action='security.user_force_logout', actor=user, target=target, details={})
    return result


@router.get('/me')
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _user_payload(db, user)


@router.get('/users')
def list_users(db: Session = Depends(get_db), user: User = Depends(require_permissions('users.manage'))):
    rows = db.query(User).order_by(User.username.asc()).all()
    out = []
    for row in rows:
        roles = get_user_roles(db, row.id)
        out.append({
            'id': row.id,
            'username': row.username,
            'full_name': row.full_name,
            'role': row.role,
            'is_active': bool(row.is_active),
            'session_version': int(row.session_version or 1),
            'force_logout_after_text': row.force_logout_after_text,
            'role_ids': roles.get('role_ids', []),
            'roles': roles.get('roles', []),
        })
    return out


@router.post('/users')
def create_user(payload: UserCreate, db: Session = Depends(get_db), user: User = Depends(require_permissions('users.manage'))):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail='Username already exists')
    role_codes = _role_codes_for_ids(db, payload.role_ids)
    _validate_or_403(
        actor_user_id=user.id,
        target_user_id=None,
        actor_is_superuser=_is_superuser(db, user),
        requested_legacy_role=payload.role,
        requested_role_codes=role_codes,
        authorization_fields_present=True,
        sensitive_fields_present=True,
    )
    obj = User(username=payload.username, full_name=payload.full_name, hashed_password=hash_password(payload.password), role=payload.role, is_active=payload.is_active, session_version=1)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    if payload.role_ids:
        assign_user_roles(db, obj.id, payload.role_ids)
    _security_audit(
        db,
        action='security.user_created',
        actor=user,
        target=obj,
        details=safe_user_security_audit_details(changed_fields={'username', 'full_name', 'role', 'role_ids', 'password', 'is_active'}, role_ids=payload.role_ids, is_active=payload.is_active),
    )
    roles = get_user_roles(db, obj.id)
    return {
        'id': obj.id,
        'username': obj.username,
        'full_name': obj.full_name,
        'role': obj.role,
        'is_active': bool(obj.is_active),
        'session_version': int(obj.session_version or 1),
        'force_logout_after_text': obj.force_logout_after_text,
        'role_ids': roles.get('role_ids', []),
        'roles': roles.get('roles', []),
    }


@router.put('/users/{user_id}')
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), user: User = Depends(require_permissions('users.manage'))):
    obj = db.get(User, user_id)
    if not obj:
        raise HTTPException(status_code=404, detail='User not found')
    data = payload.model_dump(exclude_unset=True)
    changed_fields = set(data.keys())
    role_codes = _role_codes_for_ids(db, payload.role_ids) if payload.role_ids is not None else []
    _validate_or_403(
        actor_user_id=user.id,
        target_user_id=obj.id,
        actor_is_superuser=_is_superuser(db, user),
        target_is_superuser=_target_is_superuser(db, obj),
        requested_legacy_role=data.get('role') if 'role' in data else None,
        requested_role_codes=role_codes if payload.role_ids is not None else None,
        requested_is_active=data.get('is_active') if 'is_active' in data else None,
        authorization_fields_present=bool({'role', 'role_ids'} & changed_fields),
        sensitive_fields_present=bool({'password', 'is_active', 'role', 'role_ids'} & changed_fields),
    )
    should_revoke_sessions = False
    if data.get('password'):
        obj.hashed_password = hash_password(data.pop('password'))
        should_revoke_sessions = True
    if 'is_active' in data and not data.get('is_active'):
        should_revoke_sessions = True
    for key, value in data.items():
        if key == 'role_ids':
            continue
        setattr(obj, key, value)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    if payload.role_ids is not None:
        assign_user_roles(db, obj.id, payload.role_ids)
    if should_revoke_sessions:
        revoke_all_sessions(db, obj, reason='user_update_security_change')
        db.refresh(obj)
    _security_audit(
        db,
        action='security.user_updated',
        actor=user,
        target=obj,
        details=safe_user_security_audit_details(changed_fields=changed_fields, role_ids=payload.role_ids if payload.role_ids is not None else None, is_active=payload.is_active if 'is_active' in changed_fields else None),
    )
    roles = get_user_roles(db, obj.id)
    return {
        'id': obj.id,
        'username': obj.username,
        'full_name': obj.full_name,
        'role': obj.role,
        'is_active': bool(obj.is_active),
        'session_version': int(obj.session_version or 1),
        'force_logout_after_text': obj.force_logout_after_text,
        'role_ids': roles.get('role_ids', []),
        'roles': roles.get('roles', []),
    }


@router.get('/roles')
def get_roles(db: Session = Depends(get_db), user: User = Depends(require_permissions('users.manage'))):
    return list_roles(db)


@router.get('/permissions')
def get_permissions(db: Session = Depends(get_db), user: User = Depends(require_permissions('users.manage'))):
    return list_permissions(db)
