from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_any_permissions
from app.db.database import get_db
from app.schemas.common import InHouseBookingSnapshotCreate, InHouseBookingSnapshotUpdate, RoomChargePostingStatusUpdate
from app.services.pos_service import (
    create_in_house_booking_snapshot,
    get_room_charge_posting,
    list_in_house_bookings,
    list_room_charge_postings,
    update_in_house_booking_snapshot,
    update_room_charge_posting_status,
)
from app.services.room_charge_policy import validate_room_charge_status_update

router = APIRouter()


@router.get('/')
def room_charge_queue(posting_status: str | None = None, stay_date: str | None = None, room_number: str | None = None, q: str | None = None, limit: int = 200, db: Session = Depends(get_db), user=Depends(require_any_permissions('room_charges.view', 'orders.manage', 'pos.use'))):
    return list_room_charge_postings(db, posting_status=posting_status, stay_date=stay_date, room_number=room_number, q=q, limit=limit)


@router.get('/in-house-bookings')
def in_house_bookings(stay_date: str | None = None, room_number: str | None = None, q: str | None = None, active_only: bool = True, limit: int = 200, db: Session = Depends(get_db), user=Depends(require_any_permissions('room_charges.view', 'orders.manage', 'pos.use'))):
    return list_in_house_bookings(db, stay_date=stay_date, room_number=room_number, q=q, active_only=active_only, limit=limit)


@router.post('/in-house-bookings')
def add_in_house_booking(payload: InHouseBookingSnapshotCreate, db: Session = Depends(get_db), user=Depends(require_any_permissions('room_charges.manage', 'orders.manage'))):
    try:
        return create_in_house_booking_snapshot(db, payload)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.put('/in-house-bookings/{snapshot_id}')
def edit_in_house_booking(snapshot_id: int, payload: InHouseBookingSnapshotUpdate, db: Session = Depends(get_db), user=Depends(require_any_permissions('room_charges.manage', 'orders.manage'))):
    try:
        return update_in_house_booking_snapshot(db, snapshot_id, payload)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get('/{posting_id}')
def room_charge_detail(posting_id: int, db: Session = Depends(get_db), user=Depends(require_any_permissions('room_charges.view', 'orders.manage', 'pos.use'))):
    try:
        return get_room_charge_posting(db, posting_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post('/{posting_id}/status')
def room_charge_status(posting_id: int, payload: RoomChargePostingStatusUpdate, db: Session = Depends(get_db), current_user=Depends(require_any_permissions('room_charges.manage', 'orders.manage'))):
    try:
        current = get_room_charge_posting(db, posting_id)
        validate_room_charge_status_update(current, payload)
        return update_room_charge_posting_status(db, posting_id, payload, user_id=getattr(current_user, 'id', None), approved_by_user_id=payload.approved_by_user_id)
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
