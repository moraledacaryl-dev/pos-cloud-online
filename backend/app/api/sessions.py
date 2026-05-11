from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.schemas.common import RegisterSessionClose, RegisterSessionOpen, RegisterSessionReopen
from app.services.pos_service import close_register_session, get_register_session, list_register_sessions, open_register_session, reopen_register_session

router = APIRouter()


@router.get('/')
def sessions(status: str | None = None, register_id: int | None = None, limit: int = 200, db: Session = Depends(get_db), user=Depends(require_permissions('registers.view'))):
    return list_register_sessions(db, status=status, register_id=register_id, limit=limit)


@router.get('/{session_id}')
def session_detail(session_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('registers.view'))):
    try:
        return get_register_session(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post('/open')
def open_session(payload: RegisterSessionOpen, db: Session = Depends(get_db), current_user=Depends(require_permissions('sessions.manage'))):
    try:
        return open_register_session(db, payload, user_id=getattr(current_user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{session_id}/close')
def close_session(session_id: int, payload: RegisterSessionClose, db: Session = Depends(get_db), current_user=Depends(require_permissions('sessions.manage'))):
    try:
        return close_register_session(db, session_id, payload, user_id=getattr(current_user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{session_id}/reopen')
def reopen_session(session_id: int, payload: RegisterSessionReopen, db: Session = Depends(get_db), current_user=Depends(require_permissions('sessions.manage'))):
    try:
        return reopen_register_session(db, session_id, payload, user_id=getattr(current_user, 'id', None), approved_by_user_id=payload.approved_by_user_id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
