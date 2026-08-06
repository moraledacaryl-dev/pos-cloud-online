from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.schemas.common import CashMovementCreate
from app.services.payment_control_policy import validate_cash_movement_control
from app.services.pos_service import create_cash_movement, list_cash_movements

router = APIRouter()


@router.get('/')
def cash_movements(session_id: int | None = None, limit: int = 300, db: Session = Depends(get_db), user=Depends(require_permissions('cash.manage'))):
    return list_cash_movements(db, session_id=session_id, limit=limit)


@router.post('/')
def add_cash_movement(payload: CashMovementCreate, db: Session = Depends(get_db), current_user=Depends(require_permissions('cash.manage'))):
    try:
        validate_cash_movement_control(payload)
        return create_cash_movement(db, payload, approved_by_user_id=payload.approved_by_user_id or getattr(current_user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
