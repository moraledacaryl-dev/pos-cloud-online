import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi.encoders import jsonable_encoder

from app.core.settings import settings

logger = logging.getLogger(__name__)


def publish_operations_event(
    event_type: str,
    event_id: str,
    *,
    title: str,
    summary: str = "",
    priority: str = "Normal",
    payload: dict[str, Any] | None = None,
    subject_type: str | None = None,
    subject_id: str | int | None = None,
    external_user_id: str | int | None = None,
) -> None:
    """Best-effort delivery to Operations; POS transactions never depend on it."""
    if not settings.operations_integration_enabled:
        return
    base = settings.operations_api_base.rstrip("/")
    key = settings.operations_integration_key.strip()
    if not base or not key:
        logger.warning("operations.integration_not_configured", extra={"event_type": event_type})
        return
    envelope = {
        "event_id": str(event_id),
        "event_type": event_type,
        "schema_version": 1,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "priority": priority,
        "title": title,
        "summary": summary,
        "payload": payload or {},
        "subject": {
            "type": subject_type,
            "id": str(subject_id) if subject_id is not None else None,
            "external_user_id": str(external_user_id) if external_user_id is not None else None,
        },
    }
    try:
        response = httpx.post(
            f"{base}/integrations/v2/events/{settings.operations_source_app}",
            headers={"X-Integration-Api-Key": key},
            json=jsonable_encoder(envelope),
            timeout=settings.operations_integration_timeout_seconds,
        )
        response.raise_for_status()
    except Exception as exc:
        logger.warning(
            "operations.integration_delivery_failed",
            extra={"event_type": event_type, "event_id": str(event_id), "error": str(exc)},
        )
