from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


class StaffIdentity(Base):
    __tablename__ = 'staff_identities'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_staff_id: Mapped[int] = mapped_column(Integer)
    employee_code: Mapped[str] = mapped_column(String(120))
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    department: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    position: Mapped[str | None] = mapped_column(String(160), nullable=True)
    staff_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    primary_department: Mapped[str | None] = mapped_column(String(160), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default='true', index=True)
    last_external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    last_synced_at_text: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('source_staff_id', name='uq_staff_identities_source_staff_id'),
        UniqueConstraint('employee_code', name='uq_staff_identities_employee_code'),
        Index('ix_staff_identities_source_staff_id', 'source_staff_id', unique=True),
        Index('ix_staff_identities_employee_code', 'employee_code', unique=True),
    )


class PosUserStaffLink(Base):
    __tablename__ = 'pos_user_staff_links'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    staff_identity_id: Mapped[int] = mapped_column(ForeignKey('staff_identities.id', ondelete='CASCADE'))
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', name='uq_pos_user_staff_link_user'),
        UniqueConstraint('staff_identity_id', name='uq_pos_user_staff_link_identity'),
        Index('ix_pos_user_staff_links_user_id', 'user_id', unique=True),
        Index('ix_pos_user_staff_links_staff_identity_id', 'staff_identity_id', unique=True),
    )
