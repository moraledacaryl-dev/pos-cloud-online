from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response
from redis import Redis
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.customer_display import CustomerDisplayDevice

DISPLAY_COOKIE = 'pos_display'
PAIRING_TTL_SECONDS = 120
DEVICE_TTL_DAYS = 180
SNAPSHOT_TTL_SECONDS = 600
DISPLAY_HEARTBEAT_PERSIST_SECONDS = 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _redis() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)


def create_pairing_code(*, channel: str, register_id: int | None, requester_user_id: int) -> dict:
    code = secrets.token_urlsafe(9).replace('-', '').replace('_', '')[:10].upper()
    digest = _digest(code)
    payload = {
        'channel': channel,
        'register_id': register_id,
        'requester_user_id': requester_user_id,
        'expires_at': _iso(_now() + timedelta(seconds=PAIRING_TTL_SECONDS)),
    }
    client = _redis()
    client.setex(f'pos:customer-display:pair:{digest}', PAIRING_TTL_SECONDS, json.dumps(payload, separators=(',', ':')))
    return {'pairing_code': code, 'expires_in_seconds': PAIRING_TTL_SECONDS, 'channel': channel, 'register_id': register_id}


def _activation_rate_limit(request: Request) -> None:
    host = request.client.host if request.client else 'unknown'
    client = _redis()
    key = f'pos:customer-display:activate-rate:{host}'
    count = client.incr(key)
    if count == 1:
        client.expire(key, 60)
    if count > 10:
        raise HTTPException(status_code=429, detail='Too many pairing attempts. Try again shortly.')


def activate_pairing_code(db: Session, request: Request, response: Response, code: str) -> CustomerDisplayDevice:
    _activation_rate_limit(request)
    normalized = str(code or '').strip().upper()
    if len(normalized) < 8:
        raise HTTPException(status_code=400, detail='Invalid pairing code')
    digest = _digest(normalized)
    raw = _redis().getdel(f'pos:customer-display:pair:{digest}')
    if not raw:
        raise HTTPException(status_code=401, detail='Pairing code is invalid, expired, or already used')
    try:
        data = json.loads(raw)
    except Exception as exc:
        raise HTTPException(status_code=401, detail='Pairing code is invalid') from exc

    credential = secrets.token_urlsafe(48)
    now = _now()
    device = CustomerDisplayDevice(
        device_uuid=secrets.token_hex(16),
        credential_hash=_digest(credential),
        channel=str(data.get('channel') or ''),
        register_id=data.get('register_id'),
        is_active=True,
        expires_at=_iso(now + timedelta(days=DEVICE_TTL_DAYS)),
        last_seen_at=_iso(now),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    response.set_cookie(
        DISPLAY_COOKIE,
        credential,
        httponly=True,
        secure=settings.is_strict_environment,
        samesite='strict',
        path='/api/customer-display',
        max_age=DEVICE_TTL_DAYS * 86400,
    )
    return device


def require_display_device(db: Session, request: Request, channel: str) -> CustomerDisplayDevice:
    credential = request.cookies.get(DISPLAY_COOKIE)
    if not credential:
        raise HTTPException(status_code=401, detail='Customer display is not paired')
    device = db.query(CustomerDisplayDevice).filter(CustomerDisplayDevice.credential_hash == _digest(credential)).first()
    if not device or not device.is_active or device.revoked_at:
        raise HTTPException(status_code=401, detail='Customer display credential is invalid or revoked')
    expires_at = _parse(device.expires_at)
    now = _now()
    if expires_at and expires_at <= now:
        raise HTTPException(status_code=401, detail='Customer display credential has expired')
    if device.channel != channel:
        raise HTTPException(status_code=403, detail='Customer display is paired to another channel')

    # Customer displays poll frequently. Persist presence at most once per minute
    # instead of turning every read into a database write/commit.
    last_seen = _parse(device.last_seen_at)
    if last_seen is None or (now - last_seen).total_seconds() >= DISPLAY_HEARTBEAT_PERSIST_SECONDS:
        device.last_seen_at = _iso(now)
        db.add(device)
        db.commit()
    return device


def revoke_device(db: Session, device: CustomerDisplayDevice) -> None:
    device.is_active = False
    device.revoked_at = _iso(_now())
    db.add(device)
    db.commit()
