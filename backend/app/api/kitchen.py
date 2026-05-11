from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permissions
from app.core.settings import settings
from app.db.database import get_db
from app.models.entities import User
from app.schemas.common import KitchenLineStatusPayload
from app.services.kds_stream import stream_kds_events
from app.services.permission_service import get_user_permission_keys
from app.services.pos_service import list_kitchen_lines, update_kitchen_line_status

router = APIRouter()


def _resolve_stream_user(db: Session, request: Request) -> User:
    token = request.query_params.get('token')
    if not token:
        auth = request.headers.get('authorization') or ''
        if auth.lower().startswith('bearer '):
            token = auth.split(' ', 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail='Missing access token')
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=['HS256'])
        username = payload.get('sub')
    except JWTError:
        raise HTTPException(status_code=401, detail='Could not validate credentials')
    if not username:
        raise HTTPException(status_code=401, detail='Could not validate credentials')
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail='Could not validate credentials')
    permissions = get_user_permission_keys(db, user)
    if 'kitchen.view' not in permissions and '*' not in permissions:
        raise HTTPException(status_code=403, detail='Missing permissions: kitchen.view')
    return user


@router.get('/tickets')
def tickets(station: str | None = None, statuses: list[str] = Query(default=['queued', 'acknowledged', 'in_progress', 'ready']), db: Session = Depends(get_db), user=Depends(require_permissions('kitchen.view'))):
    return list_kitchen_lines(db, station=station, statuses=statuses)


@router.get('/stream')
async def stream(request: Request, station: str | None = None, db: Session = Depends(get_db)):
    _resolve_stream_user(db, request)
    generator = stream_kds_events(station)
    return StreamingResponse(generator, media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no'})


@router.post('/lines/{line_id}/status')
def set_status(line_id: int, payload: KitchenLineStatusPayload, db: Session = Depends(get_db), user=Depends(require_permissions('kitchen.view'))):
    try:
        return update_kitchen_line_status(db, line_id, payload, user_id=getattr(user, 'id', None))
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
