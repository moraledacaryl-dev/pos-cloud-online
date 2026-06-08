from __future__ import annotations

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.database import Base


class TimestampMixin:
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class User(Base, TimestampMixin):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default='manager', index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    force_logout_after_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    user_roles: Mapped[list['UserRole']] = relationship(back_populates='user', cascade='all, delete-orphan')
    permission_overrides: Mapped[list['UserPermissionOverride']] = relationship(back_populates='user', cascade='all, delete-orphan')


class Role(Base, TimestampMixin):
    __tablename__ = 'roles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    permissions: Mapped[list['RolePermission']] = relationship(back_populates='role', cascade='all, delete-orphan')
    users: Mapped[list['UserRole']] = relationship(back_populates='role', cascade='all, delete-orphan')


class Permission(Base, TimestampMixin):
    __tablename__ = 'permissions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(160), default='', index=True)
    group_name: Mapped[str] = mapped_column(String(120), default='General', index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_links: Mapped[list['RolePermission']] = relationship(back_populates='permission', cascade='all, delete-orphan')
    user_overrides: Mapped[list['UserPermissionOverride']] = relationship(back_populates='permission', cascade='all, delete-orphan')


class RolePermission(Base, TimestampMixin):
    __tablename__ = 'role_permissions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey('permissions.id'), index=True)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped['Role'] = relationship(back_populates='permissions')
    permission: Mapped['Permission'] = relationship(back_populates='role_links')
    __table_args__ = (UniqueConstraint('role_id', 'permission_id', name='uq_role_permission'),)


class UserRole(Base, TimestampMixin):
    __tablename__ = 'user_roles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), index=True)
    user: Mapped['User'] = relationship(back_populates='user_roles')
    role: Mapped['Role'] = relationship(back_populates='users')
    __table_args__ = (UniqueConstraint('user_id', 'role_id', name='uq_user_role'),)


class UserPermissionOverride(Base, TimestampMixin):
    __tablename__ = 'user_permission_overrides'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey('permissions.id'), index=True)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    user: Mapped['User'] = relationship(back_populates='permission_overrides')
    permission: Mapped['Permission'] = relationship(back_populates='user_overrides')
    __table_args__ = (UniqueConstraint('user_id', 'permission_id', name='uq_user_permission_override'),)


class SystemSetting(Base, TimestampMixin):
    __tablename__ = 'system_settings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value_json: Mapped[str] = mapped_column(Text, default='{}')
    updated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Outlet(Base, TimestampMixin):
    __tablename__ = 'outlets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    business_unit: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    registers: Mapped[list['Register']] = relationship(back_populates='outlet', cascade='all, delete-orphan')


class Register(Base, TimestampMixin):
    __tablename__ = 'registers'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey('outlets.id'), index=True)
    code: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    register_type: Mapped[str] = mapped_column(String(40), default='cash_drawer', index=True)
    accounting_financial_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    accounting_financial_account_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    cash_tender_label: Mapped[str] = mapped_column(String(80), default='Cash')
    default_order_type: Mapped[str] = mapped_column(String(50), default='dine_in')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outlet: Mapped['Outlet'] = relationship(back_populates='registers')
    sessions: Mapped[list['RegisterSession']] = relationship(back_populates='register', cascade='all, delete-orphan')


class CatalogItem(Base, TimestampMixin):
    __tablename__ = 'catalog_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_menu_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    external_sku_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    menu_item_name: Mapped[str] = mapped_column(String(180), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    variant_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), index=True)
    category_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    module_slug: Mapped[str] = mapped_column(String(80), default='restaurant', index=True)
    prep_station: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    price: Mapped[float] = mapped_column(Float, default=0)
    tax_rate: Mapped[float] = mapped_column(Float, default=0)
    service_charge_rate: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    availability_override: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    accounting_hash: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_sync_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_lines: Mapped[list['PosOrderLine']] = relationship(back_populates='catalog_item')
    __table_args__ = (
        UniqueConstraint('external_sku_id', name='uq_catalog_external_sku'),
    )


class RecipeDocument(Base, TimestampMixin):
    __tablename__ = 'recipe_documents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_menu_item_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    dish_name_snapshot: Mapped[str] = mapped_column(String(180), index=True)
    category_name: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120), default='application/pdf')
    file_size: Mapped[int] = mapped_column(Integer)
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    uploaded_by: Mapped['User'] = relationship()


class RegisterSession(Base, TimestampMixin):
    __tablename__ = 'register_sessions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_code: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    register_id: Mapped[int] = mapped_column(ForeignKey('registers.id'), index=True)
    business_date: Mapped[str] = mapped_column(String(50), index=True)
    shift_name: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default='open', index=True)
    opened_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    closed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    opening_float: Mapped[float] = mapped_column(Float, default=0)
    closing_actual_cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    closing_expected_cash: Mapped[float] = mapped_column(Float, default=0)
    variance_amount: Mapped[float] = mapped_column(Float, default=0)
    opening_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    closing_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_mode: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    blind_close: Mapped[bool] = mapped_column(Boolean, default=False)
    denomination_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    variance_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    close_sign_off_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    close_sign_off_role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reopen_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reopen_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    opened_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    closed_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    register: Mapped['Register'] = relationship(back_populates='sessions')
    opened_by: Mapped['User'] = relationship(foreign_keys=[opened_by_user_id])
    closed_by: Mapped['User'] = relationship(foreign_keys=[closed_by_user_id])
    orders: Mapped[list['PosOrder']] = relationship(back_populates='session')
    cash_movements: Mapped[list['CashMovement']] = relationship(back_populates='session')


class PosOrder(Base, TimestampMixin):
    __tablename__ = 'pos_orders'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_uuid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    order_no: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    register_session_id: Mapped[int] = mapped_column(ForeignKey('register_sessions.id'), index=True)
    register_id: Mapped[int] = mapped_column(ForeignKey('registers.id'), index=True)
    cashier_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    business_date: Mapped[str] = mapped_column(String(50), index=True)
    order_type: Mapped[str] = mapped_column(String(50), default='dine_in', index=True)
    source_channel: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    guest_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    service_area: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    table_label: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    seat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default='draft', index=True)
    kitchen_status: Mapped[str] = mapped_column(String(40), default='queued', index=True)
    subtotal_amount: Mapped[float] = mapped_column(Float, default=0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0)
    service_charge_amount: Mapped[float] = mapped_column(Float, default=0)
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    paid_amount: Mapped[float] = mapped_column(Float, default=0)
    balance_due: Mapped[float] = mapped_column(Float, default=0)
    primary_tender: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    void_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_to_accounting: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_sync_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    session: Mapped['RegisterSession'] = relationship(back_populates='orders')
    register: Mapped['Register'] = relationship()
    cashier: Mapped['User'] = relationship()
    lines: Mapped[list['PosOrderLine']] = relationship(back_populates='order', cascade='all, delete-orphan')
    payments: Mapped[list['PosOrderPayment']] = relationship(back_populates='order', cascade='all, delete-orphan')
    refunds: Mapped[list['Refund']] = relationship(back_populates='order', cascade='all, delete-orphan')


class PosOrderLine(Base, TimestampMixin):
    __tablename__ = 'pos_order_lines'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('pos_orders.id'), index=True)
    catalog_item_id: Mapped[int] = mapped_column(ForeignKey('catalog_items.id'), index=True)
    external_menu_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    external_sku_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    item_name_snapshot: Mapped[str] = mapped_column(String(255), index=True)
    prep_station: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0)
    line_total: Mapped[float] = mapped_column(Float, default=0)
    kitchen_status: Mapped[str] = mapped_column(String(40), default='queued', index=True)
    acknowledgement_state: Mapped[str] = mapped_column(String(40), default='unacknowledged', index=True)
    acknowledged_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    acknowledged_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    prep_started_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    ready_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    served_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    item_readiness: Mapped[str] = mapped_column(String(40), default='not_ready', index=True)
    ready_quantity: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    order: Mapped['PosOrder'] = relationship(back_populates='lines')
    catalog_item: Mapped['CatalogItem'] = relationship(back_populates='order_lines')
    acknowledged_by: Mapped['User | None'] = relationship(foreign_keys=[acknowledged_by_user_id])


class PosOrderPayment(Base, TimestampMixin):
    __tablename__ = 'pos_order_payments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('pos_orders.id'), index=True)
    tender_type: Mapped[str] = mapped_column(String(80), index=True)
    amount_applied: Mapped[float] = mapped_column(Float, default=0)
    amount_received: Mapped[float] = mapped_column(Float, default=0)
    change_given: Mapped[float] = mapped_column(Float, default=0)
    reference_no: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    accounting_financial_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    order: Mapped['PosOrder'] = relationship(back_populates='payments')



class InHouseBookingSnapshot(Base, TimestampMixin):
    __tablename__ = 'in_house_booking_snapshots'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stay_date: Mapped[str] = mapped_column(String(50), index=True)
    room_number: Mapped[str] = mapped_column(String(80), index=True)
    guest_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    guest_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    arrival_date: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    departure_date: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    booking_status: Mapped[str] = mapped_column(String(80), default='in_house', index=True)
    beds24_booking_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(80), default='manual_snapshot', index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RoomChargePosting(Base, TimestampMixin):
    __tablename__ = 'room_charge_postings'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    posting_uuid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('pos_orders.id'), index=True)
    order_payment_id: Mapped[int | None] = mapped_column(ForeignKey('pos_order_payments.id'), nullable=True, index=True)
    booking_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey('in_house_booking_snapshots.id'), nullable=True, index=True)
    booking_date: Mapped[str] = mapped_column(String(50), index=True)
    service_date: Mapped[str] = mapped_column(String(50), index=True)
    service_time: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    room_number: Mapped[str] = mapped_column(String(80), index=True)
    guest_label: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    beds24_booking_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    order_source: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    service_type: Mapped[str] = mapped_column(String(80), default='room_service', index=True)
    charge_amount: Mapped[float] = mapped_column(Float, default=0)
    posting_status: Mapped[str] = mapped_column(String(80), default='pending_frontdesk_post', index=True)
    posted_to_beds24_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    posted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    selected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    later_payment_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    dispute_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    beds24_posting_reference: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    settled_at_frontdesk_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    payment_date: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    bill_to: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_to_accounting: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_sync_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    order: Mapped['PosOrder'] = relationship('PosOrder')
    payment: Mapped['PosOrderPayment | None'] = relationship('PosOrderPayment')
    booking_snapshot: Mapped['InHouseBookingSnapshot | None'] = relationship('InHouseBookingSnapshot')
    posted_by: Mapped['User | None'] = relationship('User', foreign_keys=[posted_by_user_id])
    created_by: Mapped['User | None'] = relationship('User', foreign_keys=[created_by_user_id])
    selected_by: Mapped['User | None'] = relationship('User', foreign_keys=[selected_by_user_id])
    __table_args__ = (UniqueConstraint('order_payment_id', name='uq_room_charge_posting_payment'),)


class CashMovement(Base, TimestampMixin):
    __tablename__ = 'cash_movements'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cash_event_uuid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    register_session_id: Mapped[int] = mapped_column(ForeignKey('register_sessions.id'), index=True)
    register_id: Mapped[int] = mapped_column(ForeignKey('registers.id'), index=True)
    source_order_id: Mapped[int | None] = mapped_column(ForeignKey('pos_orders.id'), nullable=True, index=True)
    event_date: Mapped[str] = mapped_column(String(50), index=True)
    direction: Mapped[str] = mapped_column(String(10), index=True)
    movement_type: Mapped[str] = mapped_column(String(50), index=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_no: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    accounting_financial_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    to_accounting_financial_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    destination_register_id: Mapped[int | None] = mapped_column(ForeignKey('registers.id'), nullable=True, index=True)
    transfer_group_uuid: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    synced_to_accounting: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_sync_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    session: Mapped['RegisterSession'] = relationship(back_populates='cash_movements')
    register: Mapped['Register'] = relationship(foreign_keys=[register_id])
    destination_register: Mapped['Register | None'] = relationship(foreign_keys=[destination_register_id])
    source_order: Mapped['PosOrder'] = relationship()
    approved_by: Mapped['User'] = relationship()


class SyncOutboxEvent(Base, TimestampMixin):
    __tablename__ = 'sync_outbox_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_uuid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    aggregate_type: Mapped[str] = mapped_column(String(60), index=True)
    aggregate_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default='{}')
    status: Mapped[str] = mapped_column(String(40), default='pending', index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    last_attempt_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)




class Refund(Base, TimestampMixin):
    __tablename__ = 'refunds'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refund_uuid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    refund_no: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('pos_orders.id'), index=True)
    register_session_id: Mapped[int] = mapped_column(ForeignKey('register_sessions.id'), index=True)
    register_id: Mapped[int] = mapped_column(ForeignKey('registers.id'), index=True)
    cashier_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    refund_mode: Mapped[str] = mapped_column(String(40), default='full', index=True)
    reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    reason_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    subtotal_amount: Mapped[float] = mapped_column(Float, default=0)
    refunded_amount: Mapped[float] = mapped_column(Float, default=0)
    synced_to_accounting: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    last_sync_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    order: Mapped['PosOrder'] = relationship(back_populates='refunds')
    session: Mapped['RegisterSession'] = relationship()
    register: Mapped['Register'] = relationship()
    cashier: Mapped['User'] = relationship(foreign_keys=[cashier_user_id])
    approved_by: Mapped['User'] = relationship(foreign_keys=[approved_by_user_id])
    lines: Mapped[list['RefundLine']] = relationship(back_populates='refund', cascade='all, delete-orphan')
    payments: Mapped[list['RefundPayment']] = relationship(back_populates='refund', cascade='all, delete-orphan')


class RefundLine(Base, TimestampMixin):
    __tablename__ = 'refund_lines'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey('refunds.id'), index=True)
    order_line_id: Mapped[int | None] = mapped_column(ForeignKey('pos_order_lines.id'), nullable=True, index=True)
    item_name_snapshot: Mapped[str] = mapped_column(String(255), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=0)
    unit_price: Mapped[float] = mapped_column(Float, default=0)
    discount_amount: Mapped[float] = mapped_column(Float, default=0)
    refunded_line_total: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    refund: Mapped['Refund'] = relationship(back_populates='lines')
    order_line: Mapped['PosOrderLine'] = relationship()


class RefundPayment(Base, TimestampMixin):
    __tablename__ = 'refund_payments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refund_id: Mapped[int] = mapped_column(ForeignKey('refunds.id'), index=True)
    tender_type: Mapped[str] = mapped_column(String(80), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    reference_no: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False)
    accounting_financial_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    refund: Mapped['Refund'] = relationship(back_populates='payments')


class ManagerApproval(Base, TimestampMixin):
    __tablename__ = 'manager_approvals'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    approval_uuid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    approval_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default='pending', index=True)
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    requested_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_details_json: Mapped[str] = mapped_column(Text, default='{}')
    requested_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    decided_at_text: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    requested_by: Mapped['User | None'] = relationship('User', foreign_keys=[requested_by_user_id])
    approved_by: Mapped['User | None'] = relationship('User', foreign_keys=[approved_by_user_id])


class RefreshToken(Base, TimestampMixin):
    __tablename__ = 'refresh_tokens'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_uuid: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[str] = mapped_column(String(50), index=True)
    revoked_at: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    session_version: Mapped[int] = mapped_column(Integer, default=1, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    user: Mapped['User'] = relationship()


class AuditLog(Base, TimestampMixin):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'), nullable=True, index=True)
    actor_username: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    request_path: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    request_method: Mapped[str | None] = mapped_column(String(12), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    details_json: Mapped[str] = mapped_column(Text, default='{}')
    actor: Mapped['User'] = relationship()
