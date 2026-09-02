from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import require_any_permissions, require_permissions
from app.db.database import engine, get_db
from app.schemas.common import SyncRunPayload
from app.services.ops_service import build_health_report
from app.services.pos_service import list_outbox_events
from app.services.sync_service import (
    archive_outbox_event,
    resolve_outbox_event,
    retry_outbox_event,
    run_outbox_sync,
    sync_in_house_bookings_from_accounting,
    unblock_outbox_event,
)


class ArchiveRequest(BaseModel):
    reason: str = 'Manual archive'


class ResolveRequest(BaseModel):
    resolution: str = 'Manually resolved'


class RoomChargeBookingSyncRequest(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    days_back: int = 1
    days_forward: int = 21
    force: bool = True

router = APIRouter()


@router.get('/outbox')
def outbox(status: str | None = None, limit: int = 200, db: Session = Depends(get_db), user=Depends(require_permissions('sync.view'))):
    return list_outbox_events(db, status=status, limit=limit)


@router.get('/status')
async def sync_status(db: Session = Depends(get_db), user=Depends(require_any_permissions('sync.view', 'pos.use', 'sessions.manage', 'kitchen.view'))):
    return await build_health_report(db, engine)


@router.post('/run')
async def run_sync(payload: SyncRunPayload, db: Session = Depends(get_db), user=Depends(require_permissions('sync.manage'))):
    try:
        return await run_outbox_sync(db, limit=payload.limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/room-charge-bookings')
async def sync_room_charge_bookings(payload: RoomChargeBookingSyncRequest, db: Session = Depends(get_db), user=Depends(require_permissions('sync.manage'))):
    try:
        return await sync_in_house_bookings_from_accounting(
            db,
            start_date=payload.start_date,
            end_date=payload.end_date,
            days_back=payload.days_back,
            days_forward=payload.days_forward,
            force=payload.force,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/retry/{event_id}')
async def retry_event(event_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('sync.manage'))):
    try:
        return await retry_outbox_event(db, event_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/unblock/{event_id}')
async def unblock_event(event_id: int, db: Session = Depends(get_db), user=Depends(require_permissions('sync.manage'))):
    try:
        return await unblock_outbox_event(db, event_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/archive/{event_id}')
async def archive_event(event_id: int, payload: ArchiveRequest, db: Session = Depends(get_db), user=Depends(require_permissions('sync.manage'))):
    try:
        return await archive_outbox_event(db, event_id, payload.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post('/resolve/{event_id}')
async def resolve_event(event_id: int, payload: ResolveRequest, db: Session = Depends(get_db), user=Depends(require_permissions('sync.manage'))):
    try:
        return await resolve_outbox_event(db, event_id, payload.resolution)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
