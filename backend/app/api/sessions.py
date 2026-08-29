from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.schemas.common import RegisterSessionClose, RegisterSessionOpen, RegisterSessionReopen
from app.services.approval_guard import consume_protected_approval
from app.services.operations_integration import publish_operations_event
from app.services.pos_service import close_register_session, get_register_session, list_register_sessions, open_register_session, reopen_register_session

router = APIRouter()


@router.get('')
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
def close_session(session_id: int, payload: RegisterSessionClose, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user=Depends(require_permissions('sessions.manage'))):
    try:
        result = close_register_session(db, session_id, payload, user_id=getattr(current_user, 'id', None))
        background_tasks.add_task(
            publish_operations_event,
            'session.closed',
            f'session-closed:{session_id}',
            title=f'POS session closed #{session_id}',
            summary='A register session was closed.',
            payload={'session': result},
            subject_type='register_session',
            subject_id=session_id,
            external_user_id=getattr(current_user, 'id', None),
        )
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/{session_id}/reopen')
def reopen_session(session_id: int, payload: RegisterSessionReopen, db: Session = Depends(get_db), current_user=Depends(require_permissions('sessions.manage'))):
    try:
        with consume_protected_approval(
            db,
            requester=current_user,
            payload=payload,
            approval_type='reopen_session',
            entity_type='register_session',
            entity_id=session_id,
            requested_reason=payload.reason,
        ) as grant:
            return reopen_register_session(db, session_id, payload, user_id=getattr(current_user, 'id', None), approved_by_user_id=grant['approved_by_user_id'])
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
