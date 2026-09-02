from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LoginPayload(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str | None = None
    role: str = 'manager'
    role_ids: list[int] = Field(default_factory=list)
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: str | None = None
    role_ids: list[int] | None = None
    is_active: bool | None = None
    password: str | None = None


class OutletCreate(BaseModel):
    code: str
    name: str
    business_unit: str | None = None
    is_active: bool = True
    notes: str | None = None


class OutletUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    business_unit: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class RegisterCreate(BaseModel):
    outlet_id: int
    code: str
    name: str
    register_type: str = 'cash_drawer'
    accounting_financial_account_id: int | None = None
    accounting_financial_account_code: str | None = None
    cash_tender_label: str = 'Cash'
    default_order_type: str = 'dine_in'
    is_active: bool = True
    notes: str | None = None


class RegisterUpdate(BaseModel):
    outlet_id: int | None = None
    code: str | None = None
    name: str | None = None
    register_type: str | None = None
    accounting_financial_account_id: int | None = None
    accounting_financial_account_code: str | None = None
    cash_tender_label: str | None = None
    default_order_type: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class CatalogItemCreate(BaseModel):
    external_menu_item_id: int | None = None
    external_sku_id: int | None = None
    menu_item_name: str
    sku_code: str | None = None
    variant_name: str | None = None
    display_name: str
    category_name: str | None = None
    module_slug: str = 'restaurant'
    prep_station: str | None = None
    price: float = 0
    tax_rate: float = 0
    service_charge_rate: float = 0
    is_active: bool = True
    is_available: bool = True
    availability_override: bool | None = None
    sort_order: int = 0
    accounting_hash: str | None = None
    last_sync_at: str | None = None
    notes: str | None = None


class CatalogItemUpdate(BaseModel):
    menu_item_name: str | None = None
    sku_code: str | None = None
    variant_name: str | None = None
    display_name: str | None = None
    category_name: str | None = None
    module_slug: str | None = None
    prep_station: str | None = None
    price: float | None = None
    tax_rate: float | None = None
    service_charge_rate: float | None = None
    is_active: bool | None = None
    is_available: bool | None = None
    availability_override: bool | None = None
    sort_order: int | None = None
    accounting_hash: str | None = None
    last_sync_at: str | None = None
    notes: str | None = None


class RegisterSessionOpen(BaseModel):
    register_id: int
    business_date: str
    shift_name: str | None = None
    opening_float: float = 0
    opening_note: str | None = None


class CashCountLine(BaseModel):
    line_label: str
    amount: float
    notes: str | None = None
    sort_order: int = 0


class RegisterSessionClose(BaseModel):
    closing_actual_cash: float
    closing_note: str | None = None
    close_mode: str = 'verified'
    blind_close: bool = False
    denomination_lines: list[CashCountLine] = Field(default_factory=list)
    variance_note: str | None = None
    sign_off_name: str | None = None
    sign_off_role: str | None = None


class RegisterSessionReopen(BaseModel):
    reason: str
    approved_by_user_id: int | None = None
    approval_grant_uuid: str | None = None
    note: str | None = None


class OrderLineCreate(BaseModel):
    catalog_item_id: int
    quantity: float = 1
    unit_price: float | None = None
    discount_amount: float = 0
    note: str | None = None
    kitchen_status: str | None = None


class OrderPaymentCreate(BaseModel):
    tender_type: str
    amount_applied: float
    amount_received: float | None = None
    reference_no: str | None = None
    note: str | None = None
    accounting_financial_account_id: int | None = None
    room_charge_service_type: str | None = None
    room_charge_booking_date: str | None = None
    room_charge_service_date: str | None = None
    room_charge_service_time: str | None = None
    room_charge_room_number: str | None = None
    room_charge_guest_label: str | None = None
    room_charge_beds24_booking_id: str | None = None
    room_charge_order_source: str | None = None
    room_charge_note: str | None = None
    room_charge_bill_to: str | None = None
    room_charge_booking_snapshot_id: int | None = None


class OrderCreate(BaseModel):
    register_session_id: int
    approved_by_user_id: int | None = None
    approval_grant_uuid: str | None = None
    order_type: str = 'dine_in'
    source_channel: str | None = None
    guest_name: str | None = None
    service_area: str | None = None
    table_label: str | None = None
    seat_count: int | None = None
    note: str | None = None
    lines: list[OrderLineCreate] = Field(default_factory=list)


class OrderUpdate(BaseModel):
    approved_by_user_id: int | None = None
    approval_grant_uuid: str | None = None
    order_type: str | None = None
    source_channel: str | None = None
    guest_name: str | None = None
    service_area: str | None = None
    table_label: str | None = None
    seat_count: int | None = None
    note: str | None = None
    lines: list[OrderLineCreate] | None = None


class OrderPayPayload(BaseModel):
    payments: list[OrderPaymentCreate] = Field(default_factory=list)
    note: str | None = None


class OrderVoidPayload(BaseModel):
    reason: str
    approved_by_user_id: int | None = None
    approval_grant_uuid: str | None = None


class OrderTableTransferPayload(BaseModel):
    target_table_label: str
    target_service_area: str | None = None


class OrderTableMergePayload(BaseModel):
    target_table_label: str
    target_service_area: str | None = None


class RefundLineCreate(BaseModel):
    order_line_id: int | None = None
    quantity: float | None = None
    amount: float | None = None
    note: str | None = None


class RefundCreate(BaseModel):
    refund_mode: str = 'full'
    amount: float | None = None
    reason_code: str | None = None
    reason_text: str | None = None
    note: str | None = None
    approved_by_user_id: int | None = None
    approval_grant_uuid: str | None = None
    lines: list[RefundLineCreate] = Field(default_factory=list)


class CashMovementCreate(BaseModel):
    register_session_id: int
    approved_by_user_id: int | None = None
    approval_grant_uuid: str | None = None
    direction: str
    movement_type: str
    category: str | None = None
    amount: float
    note: str | None = None
    reference_no: str | None = None
    accounting_financial_account_id: int | None = None
    to_accounting_financial_account_id: int | None = None
    destination_register_id: int | None = None
    requires_approval: bool = False


class KitchenLineStatusPayload(BaseModel):
    kitchen_status: str
    acknowledgement_state: str | None = None
    ready_quantity: float | None = None
    item_readiness: str | None = None
    note: str | None = None


class SyncRunPayload(BaseModel):
    limit: int = 25


class SystemSettingsUpdate(BaseModel):
    accounting_sync: dict[str, Any] | None = None
    ui_preferences: dict[str, Any] | None = None


class RefreshTokenPayload(BaseModel):
    refresh_token: str


class InHouseBookingSnapshotCreate(BaseModel):
    stay_date: str
    room_number: str
    guest_name: str | None = None
    guest_label: str | None = None
    arrival_date: str | None = None
    departure_date: str | None = None
    booking_status: str = 'in_house'
    beds24_booking_id: str | None = None
    source: str = 'manual_snapshot'
    is_active: bool = True
    notes: str | None = None


class InHouseBookingSnapshotUpdate(BaseModel):
    stay_date: str | None = None
    room_number: str | None = None
    guest_name: str | None = None
    guest_label: str | None = None
    arrival_date: str | None = None
    departure_date: str | None = None
    booking_status: str | None = None
    beds24_booking_id: str | None = None
    source: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class RoomChargePostingStatusUpdate(BaseModel):
    posting_status: str
    approved_by_user_id: int | None = None
    approval_grant_uuid: str | None = None
    beds24_posting_reference: str | None = None
    note: str | None = None
    dispute_note: str | None = None
    later_payment_status: str | None = None
    payment_date: str | None = None
    posted_to_beds24_at: str | None = None
    rejected_reason: str | None = None
    bill_to: str | None = None


class AuditLogFilters(BaseModel):
    actor_user_id: int | None = None
    action: str | None = None
    entity_type: str | None = None
    entity_id: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    q: str | None = None
    limit: int = 200


class ManagerApprovalFilters(BaseModel):
    status: str | None = None
    approval_type: str | None = None
    entity_type: str | None = None
    requested_by_user_id: int | None = None
    approved_by_user_id: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    q: str | None = None
    limit: int = 200
