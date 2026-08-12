from __future__ import annotations

from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.core.settings import looks_like_placeholder_secret, settings
from app.db.database import get_db
from app.models.entities import User
from app.schemas.staff_identity import PosUserStaffLinkUpdate, StaffEmployeeSyncEnvelope
from app.services.staff_identity_service import (
    list_staff_identities,
    list_user_staff_links,
    set_user_staff_link,
    sync_staff_employees,
)

router = APIRouter()


def require_staff_integration_key(
    x_integration_api_key: str | None = Header(default=None, alias='X-Integration-Api-Key'),
):
    if not settings.staff_integration_enabled:
        raise HTTPException(status_code=503, detail='Staff identity integration is disabled.')
    secret = (settings.staff_integration_key or '').strip()
    if looks_like_placeholder_secret(secret):
        raise HTTPException(status_code=503, detail='Staff identity integration key is not configured.')
    if not x_integration_api_key or not compare_digest(str(x_integration_api_key), secret):
        raise HTTPException(status_code=401, detail='Invalid Staff integration credential.')


@router.post('/employees')
def receive_staff_employees(
    payload: StaffEmployeeSyncEnvelope,
    db: Session = Depends(get_db),
    _=Depends(require_staff_integration_key),
):
    try:
        return sync_staff_employees(db, payload)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/identities')
def staff_identities(
    db: Session = Depends(get_db),
    _: User = Depends(require_permissions('users.manage')),
):
    return list_staff_identities(db)


@router.get('/user-links')
def user_staff_links(
    db: Session = Depends(get_db),
    _: User = Depends(require_permissions('users.manage')),
):
    return list_user_staff_links(db)


@router.put('/user-links/{user_id}')
def update_user_staff_link(
    user_id: int,
    payload: PosUserStaffLinkUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permissions('users.manage')),
):
    try:
        return set_user_staff_link(db, user_id, payload.staff_identity_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
