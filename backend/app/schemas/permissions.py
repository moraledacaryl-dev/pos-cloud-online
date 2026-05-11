from pydantic import BaseModel, Field


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    is_active: bool = True


class RoleUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class RoleAssignmentsPayload(BaseModel):
    permission_keys: list[str] = Field(default_factory=list)
