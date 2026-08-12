from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


class StaffIdentity(Base):
    __tablename__ = 'staff_identities'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_staff_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    employee_code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    department: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    position: Mapped[str | None] = mapped_column(String(160), nullable=True)
    staff_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    primary_department: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_synced_at_text: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PosUserStaffLink(Base):
    __tablename__ = 'pos_user_staff_links'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), unique=True, index=True)
    staff_identity_id: Mapped[int] = mapped_column(ForeignKey('staff_identities.id', ondelete='CASCADE'), unique=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', name='uq_pos_user_staff_link_user'),
        UniqueConstraint('staff_identity_id', name='uq_pos_user_staff_link_identity'),
    )
