from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StaffEmployeeIdentity(BaseModel):
    model_config = ConfigDict(extra='forbid')

    employee_code: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=255)
    department: str | None = Field(default=None, max_length=160)
    position: str | None = Field(default=None, max_length=160)
    role: str | None = Field(default=None, max_length=120)
    active: bool = True
    primary_department: str | None = Field(default=None, max_length=160)
    source_staff_id: int = Field(gt=0)


class StaffEmployeeSyncPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')

    employees: list[StaffEmployeeIdentity] = Field(min_length=1, max_length=500)


class StaffEmployeeSyncEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')

    external_source: str
    external_id: str = Field(min_length=1, max_length=255)
    event_type: str
    source_record_type: str | None = None
    source_record_id: int | str | None = None
    generated_at: str | None = None
    schema_version: str | None = None
    payload: StaffEmployeeSyncPayload


class PosUserStaffLinkUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')

    staff_identity_id: int | None = Field(default=None, gt=0)
