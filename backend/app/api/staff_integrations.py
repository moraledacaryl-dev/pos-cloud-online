from __future__ import annotations

import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import looks_like_placeholder_secret, settings
from app.db.database import get_db
from app.models.entities import SystemSetting

router = APIRouter()

SAFE_FIELDS = {
    "employee_code",
    "display_name",
    "department",
    "position",
    "role",
    "active",
    "primary_department",
    "source_staff_id",
}


def _require_integration_key(
    authorization: str | None,
    x_integration_api_key: str | None,
) -> None:
    configured = settings.integration_api_key.strip()
    if looks_like_placeholder_secret(configured):
        if settings.is_production:
            raise HTTPException(status_code=503, detail="Integration API key is not configured")
        return
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    supplied = x_integration_api_key or bearer
    if not supplied or not hmac.compare_digest(supplied, configured):
        raise HTTPException(status_code=401, detail="Invalid integration API key")


def _setting(db: Session, key: str) -> SystemSetting | None:
    return db.scalar(select(SystemSetting).where(SystemSetting.key == key))


@router.post("/integrations/staff/employees")
def receive_staff_employees(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_integration_api_key: str | None = Header(default=None, alias="X-Integration-Api-Key"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_integration_key(authorization, x_integration_api_key)
    if payload.get("external_source") != "hidden_oasis_staff_payroll":
        raise HTTPException(status_code=422, detail="Unsupported integration source")
    if payload.get("event_type") != "employee.sync":
        raise HTTPException(status_code=422, detail="Only employee.sync is supported")
    external_id = str(payload.get("external_id") or "").strip()
    if not external_id:
        raise HTTPException(status_code=400, detail="external_id is required")

    receipt_key = f"staff_event::{external_id}"
    receipt = _setting(db, receipt_key)
    if receipt:
        return {"status": "already_applied", "external_id": external_id}

    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    employees = body.get("employees") if isinstance(body.get("employees"), list) else []
    applied = 0
    for raw in employees:
        if not isinstance(raw, dict):
            continue
        employee_code = str(raw.get("employee_code") or "").strip()
        display_name = str(raw.get("display_name") or "").strip()
        if not employee_code or not display_name:
            raise HTTPException(status_code=422, detail="Each employee requires employee_code and display_name")
        safe = {key: raw.get(key) for key in SAFE_FIELDS if key in raw}
        key = f"staff_employee::{employee_code}"
        row = _setting(db, key)
        value_json = json.dumps(safe, ensure_ascii=False, sort_keys=True, default=str)
        if row:
            row.value_json = value_json
            row.updated_by = "hidden_oasis_staff_payroll"
        else:
            db.add(SystemSetting(key=key, value_json=value_json, updated_by="hidden_oasis_staff_payroll"))
        applied += 1

    db.add(SystemSetting(
        key=receipt_key,
        value_json=json.dumps({
            "external_id": external_id,
            "schema_version": payload.get("schema_version"),
            "generated_at": payload.get("generated_at"),
            "applied": applied,
        }, sort_keys=True, default=str),
        updated_by="hidden_oasis_staff_payroll",
    ))
    db.commit()
    return {"status": "accepted", "external_id": external_id, "applied": applied}
