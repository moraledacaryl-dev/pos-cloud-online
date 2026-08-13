from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.api.deps import require_any_permissions
from app.db.database import get_db
from app.services.approval_service import authorize_approval_with_credentials, list_manager_approvals, approve_manager_approval, reject_manager_approval

router = APIRouter()


class ApprovalDecisionRequest(BaseModel):
    decision_note: str | None = None


class ApprovalAuthorizeRequest(BaseModel):
    manager_username: str = Field(min_length=1, max_length=100)
    manager_password: str = Field(min_length=1, max_length=255)
    approval_type: str
    entity_type: str
    entity_id: str | int | None = None
    requested_reason: str | None = None
    protected_payload: dict | list | None = None


@router.post('/authorize')
def authorize_approval(request: ApprovalAuthorizeRequest, db: Session = Depends(get_db), user=Depends(require_any_permissions('pos.use', 'orders.manage', 'cash.manage', 'sessions.manage', 'room_charges.manage'))):
    try:
        return authorize_approval_with_credentials(
            db,
            requester=user,
            manager_username=request.manager_username,
            manager_password=request.manager_password,
            approval_type=request.approval_type,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            requested_reason=request.requested_reason,
            protected_payload=request.protected_payload,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(e))


@router.get('/')
def approvals(status: str | None = None, approval_type: str | None = None, entity_type: str | None = None, requested_by_user_id: int | None = None, approved_by_user_id: int | None = None, date_from: str | None = None, date_to: str | None = None, q: str | None = None, limit: int = 200, db: Session = Depends(get_db), user=Depends(require_any_permissions('settings.manage', 'users.manage', 'reports.view', 'approvals.view'))):
    return list_manager_approvals(db, status=status, approval_type=approval_type, entity_type=entity_type, requested_by_user_id=requested_by_user_id, approved_by_user_id=approved_by_user_id, date_from=date_from, date_to=date_to, q=q, limit=limit)


@router.get('/{approval_id}')
def get_approval(approval_id: int, db: Session = Depends(get_db), user=Depends(require_any_permissions('settings.manage', 'users.manage', 'reports.view', 'approvals.view'))):
    approvals = list_manager_approvals(db, limit=1, approval_id=approval_id)
    if not approvals:
        raise HTTPException(status_code=404, detail='Approval not found')
    return approvals[0]


@router.post('/{approval_id}/approve')
def approve_approval(approval_id: int, request: ApprovalDecisionRequest, db: Session = Depends(get_db), user=Depends(require_any_permissions('settings.manage', 'users.manage', 'approvals.manage'))):
    try:
        return approve_manager_approval(db, approval_id, user.id, request.decision_note)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{approval_id}/reject')
def reject_approval(approval_id: int, request: ApprovalDecisionRequest, db: Session = Depends(get_db), user=Depends(require_any_permissions('settings.manage', 'users.manage', 'approvals.manage'))):
    try:
        return reject_manager_approval(db, approval_id, user.id, request.decision_note)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
