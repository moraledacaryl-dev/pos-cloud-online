from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_any_permissions, require_permissions
from app.db.database import engine, get_db
from app.schemas.common import SyncRunPayload
from app.services.inventory_integration import run_inventory_outbox_sync
from app.services.operations_integration import run_operations_outbox_sync
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
    days_back: int = Field(default=1, ge=0, le=90)
    days_forward: int = Field(default=21, ge=0, le=365)
    force: bool = True

router = APIRouter()


@router.get('/outbox')
def outbox(status: str | None = None, limit: int = Query(default=200, ge=1, le=500), db: Session = Depends(get_db), user=Depends(require_permissions('sync.view'))):
    return list_outbox_events(db, status=status, limit=limit)


@router.get('/status')
async def sync_status(db: Session = Depends(get_db), user=Depends(require_any_permissions('sync.view', 'pos.use', 'sessions.manage', 'kitchen.view'))):
    return await build_health_report(db, engine)


@router.post('/run')
async def run_sync(payload: SyncRunPayload, db: Session = Depends(get_db), user=Depends(require_permissions('sync.manage'))):
    results = {}
    runners = (
        ('accounting', run_outbox_sync),
        ('inventory', run_inventory_outbox_sync),
        ('operations', run_operations_outbox_sync),
    )
    for name, runner in runners:
        try:
            results[name] = await runner(db, limit=payload.limit)
        except Exception as exc:
            db.rollback()
            results[name] = {'ok': False, 'processed': 0, 'synced': 0, 'failed': 1, 'blocked': 0, 'error': str(exc)}
    return {
        'ok': all(bool(result.get('ok')) for result in results.values()),
        'processed': sum(int(result.get('processed', 0) or 0) for result in results.values()),
        'synced': sum(int(result.get('synced', 0) or 0) for result in results.values()),
        'failed': sum(int(result.get('failed', result.get('retrying', result.get('retried', 0))) or 0) for result in results.values()),
        'blocked': sum(int(result.get('blocked', 0) or 0) for result in results.values()),
        'results': results,
    }


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
