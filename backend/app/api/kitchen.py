from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.core.settings import settings
from app.db.database import SessionLocal, get_db
from app.models.entities import User
from app.schemas.common import KitchenLineStatusPayload
from app.services.kds_stream import broadcaster_metrics, stream_kds_events
from app.services.kds_stream_security import (
    acquire_stream_slot,
    active_stream_metrics,
    consume_stream_ticket,
    issue_stream_ticket,
    release_stream_slot,
)
from app.services.permission_service import get_user_permission_keys
from app.services.pos_service import list_kitchen_lines, update_kitchen_line_status

router = APIRouter()


class StreamTicketRequest(BaseModel):
    station: str | None = Field(default=None, max_length=64)
    device_id: str | None = Field(default=None, max_length=128)


def _normalize_station(station: str | None) -> str:
    return (station or '').strip().lower()


def _validate_ticket_user(ticket_payload: dict) -> User:
    with SessionLocal() as db:
        user = db.get(User, int(ticket_payload.get('user_id') or 0))
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail='Stream ticket user is inactive or unavailable.')
        permissions = get_user_permission_keys(db, user)
        if 'kitchen.view' not in permissions and '*' not in permissions:
            raise HTTPException(status_code=403, detail='Missing permissions: kitchen.view')
        db.expunge(user)
        return user


@router.get('/tickets')
def tickets(station: str | None = None, statuses: list[str] = Query(default=['queued', 'acknowledged', 'in_progress', 'ready']), db: Session = Depends(get_db), user=Depends(require_permissions('kitchen.view'))):
    return list_kitchen_lines(db, station=station, statuses=statuses)


@router.post('/stream-ticket')
def create_stream_ticket(payload: StreamTicketRequest, user=Depends(require_permissions('kitchen.view'))):
    try:
        return issue_stream_ticket(
            user_id=user.id,
            station=_normalize_station(payload.station),
            device_id=payload.device_id,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get('/stream')
async def stream(request: Request, ticket: str = Query(min_length=20, max_length=256), station: str | None = None):
    normalized_station = _normalize_station(station)
    try:
        ticket_payload = consume_stream_ticket(ticket, requested_station=normalized_station)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    user = _validate_ticket_user(ticket_payload)
    try:
        await acquire_stream_slot(user.id)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    async def generator():
        try:
            async for frame in stream_kds_events(
                normalized_station or None,
                disconnect_check=request.is_disconnected,
                max_lifetime_seconds=max(60, int(settings.kds_stream_max_lifetime_seconds)),
            ):
                yield frame
        finally:
            await release_stream_slot(user.id)

    return StreamingResponse(
        generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache, no-store',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.get('/stream-metrics')
async def stream_metrics(user=Depends(require_permissions('kitchen.view'))):
    metrics = await active_stream_metrics()
    metrics.update(await broadcaster_metrics())
    return metrics


@router.post('/lines/{line_id}/status')
def set_status(line_id: int, payload: KitchenLineStatusPayload, db: Session = Depends(get_db), user=Depends(require_permissions('kitchen.view'))):
    try:
        return update_kitchen_line_status(db, line_id, payload, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
