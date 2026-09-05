from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.settings import settings
from app.models.entities import (
    CashMovement,
    CatalogItem,
    InHouseBookingSnapshot,
    Outlet,
    PosOrder,
    PosOrderLine,
    PosOrderPayment,
    Refund,
    RefundLine,
    RefundPayment,
    Register,
    RegisterSession,
    RoomChargePosting,
    SyncOutboxEvent,
    SystemSetting,
    User,
)
from app.schemas.common import (
    CashMovementCreate,
    CatalogItemCreate,
    CatalogItemUpdate,
    InHouseBookingSnapshotCreate,
    InHouseBookingSnapshotUpdate,
    OrderCreate,
    OrderPayPayload,
    OrderUpdate,
    OutletCreate,
    OutletUpdate,
    RefundCreate,
    RegisterCreate,
    RegisterSessionClose,
    RegisterSessionOpen,
    RegisterSessionReopen,
    RegisterUpdate,
    RoomChargePostingStatusUpdate,
)
from app.services.approval_service import create_manager_approval
from app.services.audit_service import write_audit_log
from app.services.kds_stream import publish_kds_event
from app.services.permission_service import get_user_permission_keys

logger = logging.getLogger(__name__)

LEGACY_ACCOUNTING_ROOT_API = 'https://hiddenoasis.app/api'
ACCOUNTING_SUBDOMAIN_API = 'https://accounting.hiddenoasis.app/api'

TENDER_TYPES = ['cash', 'gcash', 'card', 'bank_transfer', 'room_charge', 'mixed']
IMMEDIATE_SETTLEMENT_TENDERS = {'cash', 'gcash', 'card', 'bank_transfer'}
FOLIO_PENDING_TENDERS = {'room_charge'}
ACTIVE_TABLE_ORDER_STATUSES = {'draft', 'held', 'open', 'sent', 'served', 'unpaid'}
INACTIVE_TABLE_ORDER_STATUSES = {'paid', 'voided', 'cancelled', 'refunded', 'merged', 'closed', 'folio_pending'}
KDS_STATION_ALIASES = {
    '': 'kitchen',
    'restaurant': 'kitchen',
    'resto': 'kitchen',
    'breakfast': 'kitchen',
    'food': 'kitchen',
    'f&b': 'kitchen',
    'fnb': 'kitchen',
    'kitchen': 'kitchen',
    'cafe': 'cafe',
    'café': 'cafe',
    'coffee': 'cafe',
    'bar': 'bar',
    'expo': 'expo',
    'pass': 'expo',
}
KDS_STATION_FILTER_ALIASES = {
    'kitchen': {'kitchen', 'restaurant', 'resto', 'breakfast', 'food', 'f&b', 'fnb', '', None},
    'cafe': {'cafe', 'café', 'coffee'},
    'bar': {'bar'},
}
TENDER_SETTLEMENT_META = {
    'cash': {
        'destination': 'drawer_account',
        'destination_label': 'Drawer Account',
        'settlement_state': 'settled',
        'requires_account': True,
        'validation_error': 'Cash tender requires a mapped drawer account on the register.',
    },
    'gcash': {
        'destination': 'gcash_receiving_account',
        'destination_label': 'GCash Receiving Account',
        'settlement_state': 'settled',
        'requires_account': True,
        'validation_error': 'GCash tender requires a mapped GCash receiving account.',
    },
    'card': {
        'destination': 'card_clearing_account',
        'destination_label': 'Card Clearing Account',
        'settlement_state': 'settled',
        'requires_account': True,
        'validation_error': 'Card tender requires a mapped card clearing account.',
    },
    'bank_transfer': {
        'destination': 'bank_account_or_clearing',
        'destination_label': 'Bank Account / Clearing',
        'settlement_state': 'settled',
        'requires_account': True,
        'validation_error': 'Bank transfer tender requires a mapped bank account or bank clearing account.',
    },
    'room_charge': {
        'destination': 'folio_pending',
        'destination_label': 'Pending Folio Post',
        'settlement_state': 'pending_folio_post',
        'requires_account': False,
        'validation_error': None,
    },
}
CASH_EVENT_TYPES_IN = {'opening_float', 'cash_sale', 'paid_in', 'float_addition'}
CASH_EVENT_TYPES_OUT = {'paid_out', 'refund', 'safe_drop', 'owner_withdrawal', 'adjustment_out'}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def utc_iso(value: datetime | None) -> str | None:
    """Serialize database timestamps as unambiguous UTC for browser clients."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.isoformat().replace('+00:00', 'Z')


def parse_utc_iso(value: str | None) -> datetime | None:
    """Parse current or legacy naive ISO timestamps as UTC-aware values."""
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def business_now() -> datetime:
    try:
        return datetime.now(ZoneInfo(settings.business_timezone))
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning('Invalid business timezone %s; falling back to UTC.', settings.business_timezone)
        return datetime.now(UTC)


def today_iso() -> str:
    return business_now().date().isoformat()


def _actor_username(db: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    user = db.get(User, int(user_id))
    return user.username if user else None


def _audit_event(db: Session, *, action: str, entity_type: str, entity_id: int | str | None = None, user_id: int | None = None, details: dict | list | None = None, commit: bool = True):
    try:
        write_audit_log(db, action=action, entity_type=entity_type, entity_id=entity_id, actor_user_id=user_id, actor_username=_actor_username(db, user_id), details=details or {}, commit=commit)
    except Exception:
        logger.exception('Failed to write audit event action=%s entity_type=%s entity_id=%s', action, entity_type, entity_id)


def _record_approval(db: Session, *, approval_type: str, entity_type: str, entity_id: int | str | None = None, requested_by_user_id: int | None = None, approved_by_user_id: int | None = None, requested_reason: str | None = None, decision_note: str | None = None, request_details: dict | list | None = None, required: bool = False, commit: bool = True):
    try:
        approval = create_manager_approval(db, approval_type=approval_type, entity_type=entity_type, entity_id=entity_id, requested_by_user_id=requested_by_user_id, approved_by_user_id=approved_by_user_id, requested_reason=requested_reason, decision_note=decision_note, request_details=request_details, commit=commit)
        if required and approval.get('status') != 'approved':
            raise ValueError('Manager approval is required before this action can be completed.')
        return approval
    except Exception as exc:
        logger.exception('Failed to record manager approval approval_type=%s entity_type=%s entity_id=%s', approval_type, entity_type, entity_id)
        if required:
            raise ValueError('Manager approval could not be recorded. Please retry.') from exc
        return None


def _run_async(coro):
    try:
        asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()


def _publish_kds_refresh(stations: list[str] | None = None, reason: str = 'refresh', payload: dict | None = None):
    try:
        _run_async(publish_kds_event(reason, payload or {}, stations=stations or []))
    except Exception:
        pass


def normalize_kds_station(value: str | None) -> str:
    raw = str(value or '').strip().lower()
    return KDS_STATION_ALIASES.get(raw, raw or 'kitchen')


def _order_stations(order: PosOrder | None) -> list[str]:
    if not order:
        return []
    stations = []
    for line in (order.lines or []):
        station = normalize_kds_station(line.prep_station)
        if station not in stations:
            stations.append(station)
    return stations


def _normalize_tender_type(value: str | None) -> str:
    return str(value or '').strip().lower()


def _tender_meta(tender_type: str | None) -> dict:
    tender = _normalize_tender_type(tender_type)
    return TENDER_SETTLEMENT_META.get(tender, {
        'destination': tender or 'unmapped',
        'destination_label': tender.replace('_', ' ').title() if tender else 'Unmapped',
        'settlement_state': 'settled',
        'requires_account': False,
        'validation_error': None,
    })


def _payment_settlement_snapshot(payment: PosOrderPayment) -> dict:
    meta = _tender_meta(payment.tender_type)
    return {
        'destination': meta['destination'],
        'destination_label': meta['destination_label'],
        'settlement_state': meta['settlement_state'],
        'requires_account': bool(meta['requires_account']),
        'is_immediate_settlement': _normalize_tender_type(payment.tender_type) in IMMEDIATE_SETTLEMENT_TENDERS,
        'is_folio_pending': _normalize_tender_type(payment.tender_type) in FOLIO_PENDING_TENDERS,
    }


def _order_settlement_totals(row: PosOrder) -> tuple[float, float]:
    immediate_amount = 0.0
    folio_pending_amount = 0.0
    for payment in (row.payments or []):
        amount = float(payment.amount_applied or 0)
        tender = _normalize_tender_type(payment.tender_type)
        if tender in FOLIO_PENDING_TENDERS:
            folio_pending_amount += amount
        else:
            immediate_amount += amount
    return round(immediate_amount, 2), round(folio_pending_amount, 2)


def _order_settlement_state(row: PosOrder) -> str:
    immediate_amount, folio_pending_amount = _order_settlement_totals(row)
    total_amount = round(float(row.total_amount or 0), 2)
    covered_amount = round(immediate_amount + folio_pending_amount, 2)
    if total_amount <= 0 and covered_amount <= 0:
        return 'unpaid'
    if folio_pending_amount > 0.009 and immediate_amount > 0.009:
        return 'mixed_with_folio_pending'
    if folio_pending_amount > 0.009:
        return 'folio_pending'
    if covered_amount > 0.009:
        return 'settled'
    return 'unpaid'



ROOM_CHARGE_STATUSES = {
    'pending_selection',
    'pending_frontdesk_post',
    'posted_to_beds24',
    'rejected',
    'disputed',
    'settled_at_frontdesk',
    'written_off',
    'cancelled',
}
ALLOWED_ROOM_CHARGE_TRANSITIONS = {
    'pending_selection': {'pending_frontdesk_post', 'posted_to_beds24', 'rejected', 'disputed', 'cancelled'},
    'pending_frontdesk_post': {'posted_to_beds24', 'rejected', 'disputed', 'cancelled'},
    'posted_to_beds24': {'settled_at_frontdesk', 'disputed', 'written_off'},
    'disputed': {'settled_at_frontdesk', 'rejected', 'written_off'},
    'settled_at_frontdesk': set(),
    'written_off': set(),
    'rejected': set(),
    'cancelled': set(),
}
ROOM_CHARGE_SERVICE_TYPES = {'room_service', 'signed_from_cafe'}
ROOM_CHARGE_ORDER_SOURCES = {'cafe', 'room_service', 'restaurant'}


def _clean_text(value: str | None) -> str | None:
    text = str(value or '').strip()
    return text or None


def _room_charge_status_label(value: str | None) -> str:
    if value == 'posted_to_beds24':
        return 'Manually Marked Posted'
    return str(value or 'pending_frontdesk_post').replace('_', ' ').title()

def _infer_room_number(*values) -> str | None:
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        match = re.search(r'(?:room|rm)[^0-9]{0,3}(\d{1,4}[A-Za-z]?)', text, flags=re.I)
        if match:
            return match.group(1)
        if re.fullmatch(r'\d{1,4}[A-Za-z]?', text):
            return text
    return None


def _serialize_in_house_booking_snapshot(row: InHouseBookingSnapshot) -> dict:
    return {
        'id': row.id,
        'stay_date': row.stay_date,
        'room_number': row.room_number,
        'guest_name': row.guest_name,
        'guest_label': row.guest_label or row.guest_name or row.room_number,
        'arrival_date': row.arrival_date,
        'departure_date': row.departure_date,
        'booking_status': row.booking_status,
        'beds24_booking_id': row.beds24_booking_id,
        'source': row.source,
        'is_active': bool(row.is_active),
        'notes': row.notes,
        'created_at': utc_iso(row.created_at),
        'updated_at': utc_iso(row.updated_at),
    }


def _serialize_room_charge_posting(row: RoomChargePosting) -> dict:
    return {
        'id': row.id,
        'posting_uuid': row.posting_uuid,
        'order_id': row.order_id,
        'order_no': row.order.order_no if row.order else None,
        'order_payment_id': row.order_payment_id,
        'booking_snapshot_id': row.booking_snapshot_id,
        'booking_date': row.booking_date,
        'service_date': row.service_date,
        'service_time': row.service_time,
        'room_number': row.room_number,
        'guest_label': row.guest_label,
        'beds24_booking_id': row.beds24_booking_id,
        'order_source': row.order_source,
        'service_type': row.service_type,
        'charge_amount': row.charge_amount,
        'posting_status': row.posting_status,
        'posting_status_label': _room_charge_status_label(row.posting_status),
        'posted_to_beds24_at': row.posted_to_beds24_at_text,
        'posted_by_user_id': row.posted_by_user_id,
        'posted_by_name': row.posted_by.full_name if row.posted_by and row.posted_by.full_name else (row.posted_by.username if row.posted_by else None),
        'created_by_user_id': row.created_by_user_id,
        'created_by_name': row.created_by.full_name if row.created_by and row.created_by.full_name else (row.created_by.username if row.created_by else None),
        'selected_by_user_id': row.selected_by_user_id,
        'selected_by_name': row.selected_by.full_name if row.selected_by and row.selected_by.full_name else (row.selected_by.username if row.selected_by else None),
        'later_payment_status': row.later_payment_status,
        'note': row.note,
        'dispute_note': row.dispute_note,
        'beds24_posting_reference': row.beds24_posting_reference,
        'settled_at_frontdesk_at': row.settled_at_frontdesk_at_text,
        'payment_date': row.payment_date,
        'bill_to': row.bill_to,
        'rejected_reason': row.rejected_reason,
        'synced_to_accounting': bool(row.synced_to_accounting),
        'last_sync_at': row.last_sync_at,
        'created_at': utc_iso(row.created_at),
        'updated_at': utc_iso(row.updated_at),
        'booking_snapshot': _serialize_in_house_booking_snapshot(row.booking_snapshot) if row.booking_snapshot else None,
    }


def _get_room_charge_postings_for_order(db: Session, order_id: int) -> list[RoomChargePosting]:
    return db.query(RoomChargePosting).options(
        selectinload(RoomChargePosting.order),
        selectinload(RoomChargePosting.booking_snapshot),
        selectinload(RoomChargePosting.posted_by),
        selectinload(RoomChargePosting.created_by),
        selectinload(RoomChargePosting.selected_by),
    ).filter(RoomChargePosting.order_id == int(order_id)).order_by(RoomChargePosting.id.asc()).all()


def _resolve_room_charge_snapshot(db: Session, payment) -> InHouseBookingSnapshot | None:
    snapshot_id = getattr(payment, 'room_charge_booking_snapshot_id', None)
    if not snapshot_id:
        return None
    row = db.get(InHouseBookingSnapshot, int(snapshot_id))
    if not row or not row.is_active:
        raise ValueError('Selected in-house booking snapshot is not available.')
    return row


def _derive_room_charge_order_source(row: PosOrder, payment) -> str:
    explicit = _clean_text(getattr(payment, 'room_charge_order_source', None))
    if explicit:
        norm = explicit.strip().lower().replace(' ', '_')
        if norm in ROOM_CHARGE_ORDER_SOURCES:
            return norm
    if str(row.order_type or '').strip().lower() == 'room_service':
        return 'room_service'
    return 'restaurant' if str(row.order_type or '').strip().lower() == 'dine_in' else 'cafe'


def _build_room_charge_posting(db: Session, row: PosOrder, payment_row: PosOrderPayment, payment, user_id: int | None = None) -> RoomChargePosting:
    snapshot = _resolve_room_charge_snapshot(db, payment)
    booking_date = _clean_text(getattr(payment, 'room_charge_booking_date', None)) or (snapshot.stay_date if snapshot else None) or row.business_date
    room_number = _clean_text(getattr(payment, 'room_charge_room_number', None)) or (snapshot.room_number if snapshot else None) or _infer_room_number(getattr(payment, 'reference_no', None), row.guest_name, row.table_label, getattr(payment, 'room_charge_guest_label', None))
    guest_label = _clean_text(getattr(payment, 'room_charge_guest_label', None)) or (snapshot.guest_label if snapshot else None) or (snapshot.guest_name if snapshot else None) or row.guest_name or room_number
    service_type = _clean_text(getattr(payment, 'room_charge_service_type', None)) or ('room_service' if str(row.order_type or '').strip().lower() == 'room_service' else 'signed_from_cafe')
    service_type = service_type.strip().lower().replace(' ', '_')
    if service_type not in ROOM_CHARGE_SERVICE_TYPES:
        raise ValueError('Room charge service type must be room_service or signed_from_cafe.')
    if not booking_date:
        raise ValueError('Room charge requires a booking date / stay date.')
    if not room_number:
        raise ValueError('Room charge requires a room number or selected in-house booking.')
    beds24_booking_id = _clean_text(getattr(payment, 'room_charge_beds24_booking_id', None)) or (snapshot.beds24_booking_id if snapshot else None)
    posting = RoomChargePosting(
        posting_uuid=str(uuid.uuid4()),
        order_id=row.id,
        order_payment_id=payment_row.id,
        booking_snapshot_id=snapshot.id if snapshot else None,
        booking_date=booking_date,
        service_date=_clean_text(getattr(payment, 'room_charge_service_date', None)) or row.business_date,
        service_time=_clean_text(getattr(payment, 'room_charge_service_time', None)) or now_iso(),
        room_number=room_number,
        guest_label=guest_label,
        beds24_booking_id=beds24_booking_id,
        order_source=_derive_room_charge_order_source(row, payment),
        service_type=service_type,
        charge_amount=round(float(payment_row.amount_applied or 0), 2),
        posting_status='pending_frontdesk_post',
        later_payment_status='pending',
        note=_clean_text(getattr(payment, 'room_charge_note', None)) or _clean_text(getattr(payment, 'note', None)),
        created_by_user_id=user_id,
        selected_by_user_id=user_id,
        bill_to=_clean_text(getattr(payment, 'room_charge_bill_to', None)),
    )
    db.add(posting)
    db.flush()
    _audit_event(db, action='room_charge.created', entity_type='room_charge_posting', entity_id=posting.id, user_id=user_id, details={'room_charge_posting_id': posting.id, 'order_id': row.id, 'room_number': posting.room_number, 'booking_date': posting.booking_date, 'charge_amount': posting.charge_amount}, commit=False)
    _audit_event(db, action='room_charge.booking_selected', entity_type='room_charge_posting', entity_id=posting.id, user_id=user_id, details={'room_charge_posting_id': posting.id, 'order_id': row.id, 'booking_snapshot_id': posting.booking_snapshot_id, 'room_number': posting.room_number, 'guest_label': posting.guest_label}, commit=False)
    return posting

def setting_json(db: Session, key: str, default: dict | list | None = None):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return default if default is not None else {}
    try:
        return json.loads(row.value_json or '{}')
    except Exception:
        return default if default is not None else {}


def save_setting_json(db: Session, key: str, value, username: str | None = None):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        row = SystemSetting(key=key, value_json='{}', updated_by=username)
    row.value_json = json.dumps(value or {}, ensure_ascii=False)
    row.updated_by = username
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def repair_accounting_sync_api_base(db: Session) -> bool:
    row = db.query(SystemSetting).filter(SystemSetting.key == 'accounting_sync').first()
    if not row or LEGACY_ACCOUNTING_ROOT_API not in (row.value_json or ''):
        return False
    try:
        value = json.loads(row.value_json or '{}')
    except Exception:
        value = None
    if isinstance(value, dict):
        if value.get('api_base') != LEGACY_ACCOUNTING_ROOT_API:
            return False
        value['api_base'] = ACCOUNTING_SUBDOMAIN_API
        row.value_json = json.dumps(value, ensure_ascii=False)
    else:
        row.value_json = (row.value_json or '').replace(LEGACY_ACCOUNTING_ROOT_API, ACCOUNTING_SUBDOMAIN_API)
    row.updated_by = 'startup-repair'
    db.add(row)
    db.commit()
    return True


def ensure_default_outlet_registers(db: Session):
    if not db.query(Outlet).count():
        outlet = Outlet(code='RESTAURANT', name='Restaurant / Cafe', business_unit='F&B', is_active=True)
        db.add(outlet)
        db.commit()
        db.refresh(outlet)
        register = Register(
            outlet_id=outlet.id,
            code='MAINPOS',
            name='Main POS Drawer',
            register_type='cash_drawer',
            cash_tender_label='Cash',
            default_order_type='dine_in',
            is_active=True,
        )
        db.add(register)
        db.commit()
    default_sync = {
        'mode': 'current_erp',
        'api_base': settings.accounting_api_base,
        'api_token': '',
        'integration_secret': settings.accounting_integration_secret,
        'integration_token_path': settings.accounting_integration_token_path,
        'sync_orders': True,
        'sync_cash_movements': True,
        'sync_reconciliations': True,
        'catalog_items_path': '/menu/items',
        'catalog_skus_path': '/menu/skus',
        'current_erp_sales_path': '/menu/sales',
        'current_erp_cashflow_path': '/cashflow/transactions',
        'current_erp_reconciliation_path': '/reconciliations',
        'current_erp_transactions_lookup_path': '/cashflow/transactions',
        'current_erp_sales_lookup_path': '/menu/sales',
        'current_erp_reconciliations_lookup_path': '/reconciliations',
        'current_erp_financial_accounts_path': '/financial-accounts',
        'current_erp_transfers_path': '/transfers',
        'current_erp_receivables_path': '/receivables',
        'healthcheck_path': '/healthz',
    }
    if not db.query(SystemSetting).filter(SystemSetting.key == 'accounting_sync').first():
        save_setting_json(db, 'accounting_sync', default_sync, username='system')
    else:
        repair_accounting_sync_api_base(db)
    if not db.query(SystemSetting).filter(SystemSetting.key == 'ui_preferences').first():
        save_setting_json(db, 'ui_preferences', {'currency': 'PHP'}, username='system')



def _serialize_outlet(row: Outlet) -> dict:
    return {
        'id': row.id,
        'code': row.code,
        'name': row.name,
        'business_unit': row.business_unit,
        'is_active': bool(row.is_active),
        'notes': row.notes,
    }



def _serialize_register(row: Register) -> dict:
    return {
        'id': row.id,
        'outlet_id': row.outlet_id,
        'outlet_name': row.outlet.name if row.outlet else None,
        'code': row.code,
        'name': row.name,
        'register_type': row.register_type,
        'accounting_financial_account_id': row.accounting_financial_account_id,
        'accounting_financial_account_code': row.accounting_financial_account_code,
        'cash_tender_label': row.cash_tender_label,
        'default_order_type': row.default_order_type,
        'is_active': bool(row.is_active),
        'notes': row.notes,
    }



def _serialize_catalog_item(row: CatalogItem) -> dict:
    return {
        'id': row.id,
        'external_menu_item_id': row.external_menu_item_id,
        'external_sku_id': row.external_sku_id,
        'menu_item_name': row.menu_item_name,
        'sku_code': row.sku_code,
        'variant_name': row.variant_name,
        'display_name': row.display_name,
        'category_name': row.category_name,
        'module_slug': row.module_slug,
        'prep_station': normalize_kds_station(row.prep_station or row.module_slug),
        'price': row.price,
        'tax_rate': row.tax_rate,
        'service_charge_rate': row.service_charge_rate,
        'is_active': bool(row.is_active),
        'is_available': bool(row.is_available),
        'availability_override': row.availability_override,
        'sort_order': row.sort_order,
        'accounting_hash': row.accounting_hash,
        'last_sync_at': row.last_sync_at,
        'notes': row.notes,
    }



def compute_session_expected_cash(db: Session, session_id: int, *, commit: bool = True) -> float:
    session = db.get(RegisterSession, int(session_id))
    if not session:
        raise ValueError('Register session not found.')
    total_in = db.query(func.coalesce(func.sum(CashMovement.amount), 0)).filter(
        CashMovement.register_session_id == session.id,
        CashMovement.direction == 'in',
    ).scalar() or 0
    total_out = db.query(func.coalesce(func.sum(CashMovement.amount), 0)).filter(
        CashMovement.register_session_id == session.id,
        CashMovement.direction == 'out',
    ).scalar() or 0
    expected = float(total_in) - float(total_out)
    session.closing_expected_cash = expected
    db.add(session)
    if commit:
        db.commit()
        db.refresh(session)
    else:
        db.flush()
    return expected



def _serialize_session(row: RegisterSession) -> dict:
    orders_count = len(row.orders or [])
    denomination_lines = []
    if row.denomination_json:
        try:
            denomination_lines = json.loads(row.denomination_json)
        except Exception:
            denomination_lines = []
    try:
        session_age_days = max((business_now().date() - datetime.fromisoformat(str(row.business_date)).date()).days, 0)
    except (TypeError, ValueError):
        session_age_days = None
    is_stale = bool(row.status == 'open' and row.business_date != today_iso())
    return {
        'id': row.id,
        'session_code': row.session_code,
        'register_id': row.register_id,
        'register_name': row.register.name if row.register else None,
        'register_accounting_financial_account_id': row.register.accounting_financial_account_id if row.register else None,
        'business_date': row.business_date,
        'shift_name': row.shift_name,
        'status': row.status,
        'opened_by_user_id': row.opened_by_user_id,
        'opened_by_name': row.opened_by.full_name if row.opened_by and row.opened_by.full_name else (row.opened_by.username if row.opened_by else None),
        'closed_by_user_id': row.closed_by_user_id,
        'closed_by_name': row.closed_by.full_name if row.closed_by and row.closed_by.full_name else (row.closed_by.username if row.closed_by else None),
        'opening_float': row.opening_float,
        'closing_actual_cash': row.closing_actual_cash,
        'closing_expected_cash': row.closing_expected_cash,
        'variance_amount': row.variance_amount,
        'opening_note': row.opening_note,
        'closing_note': row.closing_note,
        'close_mode': row.close_mode,
        'blind_close': bool(row.blind_close),
        'denomination_lines': denomination_lines,
        'variance_note': row.variance_note,
        'sign_off_name': row.close_sign_off_name,
        'sign_off_role': row.close_sign_off_role,
        'reopen_reason': row.reopen_reason,
        'reopen_note': row.reopen_note,
        'opened_at_text': row.opened_at_text,
        'closed_at_text': row.closed_at_text,
        'created_at': utc_iso(row.created_at),
        'updated_at': utc_iso(row.updated_at),
        'session_age_days': session_age_days,
        'is_stale': is_stale,
        'stale_reason': f'Business date is {row.business_date}; today is {today_iso()}.' if is_stale else None,
        'orders_count': orders_count,
    }



def _serialize_refund(row: Refund, include_details: bool = True) -> dict:
    data = {
        'id': row.id,
        'refund_uuid': row.refund_uuid,
        'refund_no': row.refund_no,
        'order_id': row.order_id,
        'order_no': row.order.order_no if row.order else None,
        'register_session_id': row.register_session_id,
        'register_id': row.register_id,
        'register_name': row.register.name if row.register else None,
        'cashier_user_id': row.cashier_user_id,
        'cashier_name': row.cashier.full_name if row.cashier and row.cashier.full_name else (row.cashier.username if row.cashier else None),
        'approved_by_user_id': row.approved_by_user_id,
        'approved_by_name': row.approved_by.full_name if row.approved_by and row.approved_by.full_name else (row.approved_by.username if row.approved_by else None),
        'refund_mode': row.refund_mode,
        'reason_code': row.reason_code,
        'reason_text': row.reason_text,
        'note': row.note,
        'subtotal_amount': row.subtotal_amount,
        'refunded_amount': row.refunded_amount,
        'synced_to_accounting': bool(row.synced_to_accounting),
        'last_sync_at': row.last_sync_at,
        'created_at': utc_iso(row.created_at),
        'updated_at': utc_iso(row.updated_at),
    }
    if include_details:
        data['lines'] = [
            {
                'id': line.id,
                'order_line_id': line.order_line_id,
                'item_name_snapshot': line.item_name_snapshot,
                'quantity': line.quantity,
                'unit_price': line.unit_price,
                'discount_amount': line.discount_amount,
                'refunded_line_total': line.refunded_line_total,
                'note': line.note,
            }
            for line in (row.lines or [])
        ]
        data['payments'] = [
            {
                'id': payment.id,
                'tender_type': payment.tender_type,
                'amount': payment.amount,
                'reference_no': payment.reference_no,
                'note': payment.note,
                'is_cash': bool(payment.is_cash),
                'accounting_financial_account_id': payment.accounting_financial_account_id,
            }
            for payment in (row.payments or [])
        ]
    return data


def _serialize_order(row: PosOrder, include_lines: bool = True, db: Session | None = None) -> dict:
    refunds = list(row.refunds or [])
    refunded_total = round(sum(float(refund.refunded_amount or 0) for refund in refunds), 2)
    refundable_balance = round(max(float(row.total_amount or 0) - refunded_total, 0), 2)
    refund_status = 'none'
    if refunded_total > 0.009 and refundable_balance <= 0.009:
        refund_status = 'fully_refunded'
    elif refunded_total > 0.009:
        refund_status = 'partially_refunded'
    settled_amount, folio_pending_amount = _order_settlement_totals(row)
    settlement_state = _order_settlement_state(row)
    room_charge_postings = _get_room_charge_postings_for_order(db, row.id) if db else []
    room_charge_by_payment_id = {posting.order_payment_id: posting for posting in room_charge_postings if posting.order_payment_id}
    payment_breakdown = []
    for p in (row.payments or []):
        posting = room_charge_by_payment_id.get(p.id)
        payment_row = {
            'id': p.id,
            'tender_type': p.tender_type,
            'amount_applied': p.amount_applied,
            'amount_received': p.amount_received,
            'change_given': p.change_given,
            'reference_no': p.reference_no,
            'note': p.note,
            'is_cash': bool(p.is_cash),
            'accounting_financial_account_id': p.accounting_financial_account_id,
            **_payment_settlement_snapshot(p),
        }
        if posting:
            payment_row['room_charge_posting_status'] = posting.posting_status
            payment_row['room_charge_posting_status_label'] = _room_charge_status_label(posting.posting_status)
            payment_row['room_charge_posting'] = _serialize_room_charge_posting(posting)
        payment_breakdown.append(payment_row)
    data = {
        'id': row.id,
        'order_uuid': row.order_uuid,
        'order_no': row.order_no,
        'register_session_id': row.register_session_id,
        'register_id': row.register_id,
        'register_name': row.register.name if row.register else None,
        'register_accounting_financial_account_id': row.register.accounting_financial_account_id if row.register else None,
        'cashier_user_id': row.cashier_user_id,
        'cashier_name': row.cashier.full_name if row.cashier and row.cashier.full_name else (row.cashier.username if row.cashier else None),
        'business_date': row.business_date,
        'order_type': row.order_type,
        'source_channel': row.source_channel,
        'guest_name': row.guest_name,
        'service_area': row.service_area,
        'table_label': row.table_label,
        'seat_count': row.seat_count,
        'status': row.status,
        'kitchen_status': row.kitchen_status,
        'subtotal_amount': row.subtotal_amount,
        'discount_amount': row.discount_amount,
        'tax_amount': row.tax_amount,
        'service_charge_amount': row.service_charge_amount,
        'total_amount': row.total_amount,
        'paid_amount': row.paid_amount,
        'balance_due': row.balance_due,
        'settled_amount': settled_amount,
        'folio_pending_amount': folio_pending_amount,
        'settlement_state': settlement_state,
        'primary_tender': row.primary_tender,
        'note': row.note,
        'void_reason': row.void_reason,
        'synced_to_accounting': bool(row.synced_to_accounting),
        'last_sync_at': row.last_sync_at,
        'created_at': utc_iso(row.created_at),
        'updated_at': utc_iso(row.updated_at),
        'refunded_total': refunded_total,
        'refundable_balance': refundable_balance,
        'refund_status': refund_status,
        'payment_breakdown': payment_breakdown,
        'room_charge_postings': [_serialize_room_charge_posting(posting) for posting in room_charge_postings],
        'refunds': [_serialize_refund(refund, include_details=include_lines) for refund in refunds],
    }
    if include_lines:
        data['lines'] = [
            {
                'id': line.id,
                'catalog_item_id': line.catalog_item_id,
                'external_menu_item_id': line.external_menu_item_id,
                'external_sku_id': line.external_sku_id,
                'item_name_snapshot': line.item_name_snapshot,
                'prep_station': normalize_kds_station(line.prep_station),
                'quantity': line.quantity,
                'unit_price': line.unit_price,
                'discount_amount': line.discount_amount,
                'line_total': line.line_total,
                'kitchen_status': line.kitchen_status,
                'note': line.note,
                'sku_code': line.catalog_item.sku_code if getattr(line, 'catalog_item', None) else None,
            }
            for line in (row.lines or [])
        ]
    return data


def _serialize_cash_movement(row: CashMovement) -> dict:
    return {
        'id': row.id,
        'cash_event_uuid': row.cash_event_uuid,
        'register_session_id': row.register_session_id,
        'register_id': row.register_id,
        'register_name': row.register.name if row.register else None,
        'register_accounting_financial_account_id': row.register.accounting_financial_account_id if row.register else None,
        'source_order_id': row.source_order_id,
        'source_order_no': row.source_order.order_no if row.source_order else None,
        'event_date': row.event_date,
        'direction': row.direction,
        'movement_type': row.movement_type,
        'category': row.category,
        'amount': row.amount,
        'note': row.note,
        'reference_no': row.reference_no,
        'approved_by_user_id': row.approved_by_user_id,
        'approved_by_name': row.approved_by.full_name if row.approved_by and row.approved_by.full_name else (row.approved_by.username if row.approved_by else None),
        'accounting_financial_account_id': row.accounting_financial_account_id,
        'to_accounting_financial_account_id': row.to_accounting_financial_account_id,
        'destination_register_id': row.destination_register_id,
        'destination_register_name': row.destination_register.name if getattr(row, 'destination_register', None) else None,
        'transfer_group_uuid': row.transfer_group_uuid,
        'requires_approval': bool(row.requires_approval),
        'is_transfer': row.movement_type in {'safe_drop', 'bank_deposit', 'drawer_transfer'},
        'synced_to_accounting': bool(row.synced_to_accounting),
        'last_sync_at': row.last_sync_at,
    }



def _serialize_outbox(row: SyncOutboxEvent) -> dict:
    is_suppressed = (
        not settings.inventory_integration_enabled
        and str(row.event_type or '').startswith('inventory.')
        and row.status in {'pending', 'failed', 'error', 'blocked', 'inventory_pending', 'inventory_retry', 'suppressed'}
    )
    return {
        'id': row.id,
        'event_uuid': row.event_uuid,
        'aggregate_type': row.aggregate_type,
        'aggregate_id': row.aggregate_id,
        'event_type': row.event_type,
        'idempotency_key': row.idempotency_key,
        'payload_json': row.payload_json,
        'status': 'suppressed' if is_suppressed else row.status,
        'stored_status': row.status,
        'suppressed_reason': 'Inventory integration is not enabled.' if is_suppressed else None,
        'retry_count': row.retry_count,
        'next_retry_at': row.next_retry_at,
        'last_attempt_at': row.last_attempt_at,
        'last_error': row.last_error,
        'synced_at': row.synced_at,
        'created_at': utc_iso(row.created_at),
    }



def list_outlets(db: Session):
    return [_serialize_outlet(row) for row in db.query(Outlet).order_by(Outlet.name.asc()).all()]


def create_outlet(db: Session, payload: OutletCreate):
    if db.query(Outlet).filter(Outlet.code == payload.code.strip()).first():
        raise ValueError('Outlet code already exists.')
    row = Outlet(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_outlet(row)


def update_outlet(db: Session, outlet_id: int, payload: OutletUpdate):
    row = db.get(Outlet, int(outlet_id))
    if not row:
        raise ValueError('Outlet not found.')
    data = payload.model_dump(exclude_unset=True)
    if 'code' in data and data['code']:
        dup = db.query(Outlet).filter(Outlet.code == data['code'], Outlet.id != row.id).first()
        if dup:
            raise ValueError('Outlet code already exists.')
    for key, value in data.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_outlet(row)


def list_registers(db: Session, only_active: bool = False):
    query = db.query(Register).options(selectinload(Register.outlet)).order_by(Register.name.asc())
    if only_active:
        query = query.filter(Register.is_active == True)
    return [_serialize_register(row) for row in query.all()]


def create_register(db: Session, payload: RegisterCreate):
    if not db.get(Outlet, int(payload.outlet_id)):
        raise ValueError('Outlet not found.')
    if db.query(Register).filter(Register.code == payload.code.strip()).first():
        raise ValueError('Register code already exists.')
    if payload.accounting_financial_account_id is not None and int(payload.accounting_financial_account_id) <= 0:
        raise ValueError('Accounting financial account ID must be a positive integer.')
    row = Register(**payload.model_dump())
    db.add(row)
    db.commit()
    row = db.query(Register).options(selectinload(Register.outlet)).filter(Register.id == row.id).first()
    return _serialize_register(row)


def update_register(db: Session, register_id: int, payload: RegisterUpdate):
    row = db.query(Register).options(selectinload(Register.outlet)).filter(Register.id == int(register_id)).first()
    if not row:
        raise ValueError('Register not found.')
    data = payload.model_dump(exclude_unset=True)
    if 'outlet_id' in data and data['outlet_id'] and not db.get(Outlet, int(data['outlet_id'])):
        raise ValueError('Outlet not found.')
    if 'code' in data and data['code']:
        dup = db.query(Register).filter(Register.code == data['code'], Register.id != row.id).first()
        if dup:
            raise ValueError('Register code already exists.')
    if 'accounting_financial_account_id' in data and data['accounting_financial_account_id'] is not None and int(data['accounting_financial_account_id']) <= 0:
        raise ValueError('Accounting financial account ID must be a positive integer.')
    for key, value in data.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    row = db.query(Register).options(selectinload(Register.outlet)).filter(Register.id == row.id).first()
    return _serialize_register(row)


def list_catalog_items(db: Session, active_only: bool = False, available_only: bool = False, q: str | None = None):
    query = db.query(CatalogItem).order_by(CatalogItem.sort_order.asc(), CatalogItem.display_name.asc())
    if active_only:
        query = query.filter(CatalogItem.is_active == True)
    if available_only:
        query = query.filter(CatalogItem.is_available == True)
    if q:
        like = f'%{q.strip()}%'
        query = query.filter(
            CatalogItem.display_name.ilike(like)
            | CatalogItem.menu_item_name.ilike(like)
            | CatalogItem.category_name.ilike(like)
        )
    return [_serialize_catalog_item(row) for row in query.all()]


def create_catalog_item(db: Session, payload: CatalogItemCreate):
    if payload.external_sku_id and db.query(CatalogItem).filter(CatalogItem.external_sku_id == payload.external_sku_id).first():
        raise ValueError('Catalog item external_sku_id already exists.')
    row = CatalogItem(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_catalog_item(row)


def update_catalog_item(db: Session, item_id: int, payload: CatalogItemUpdate):
    row = db.get(CatalogItem, int(item_id))
    if not row:
        raise ValueError('Catalog item not found.')
    data = payload.model_dump(exclude_unset=True)
    is_synced = bool(row.external_menu_item_id or row.external_sku_id)
    if is_synced:
        forbidden = set(data) - {'is_available'}
        if forbidden:
            raise ValueError('Accounting owns synced catalog details. POS can only set a local sold-out override.')
        if 'is_available' in data:
            requested = bool(data['is_available'])
            row.availability_override = False if not requested else None
            row.is_available = requested
        db.add(row)
        db.commit()
        db.refresh(row)
        return _serialize_catalog_item(row)
    for key, value in data.items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_catalog_item(row)


def delete_catalog_item(db: Session, item_id: int):
    row = db.get(CatalogItem, int(item_id))
    if not row:
        raise ValueError('Catalog item not found.')
    if row.external_menu_item_id or row.external_sku_id:
        raise ValueError('Accounting-owned catalog items cannot be deleted from POS.')
    db.delete(row)
    db.commit()
    return {'ok': True}


def _next_order_no(db: Session, business_date: str):
    ymd = (business_date or today_iso()).replace('-', '')
    count = db.query(PosOrder).filter(PosOrder.business_date == business_date).count() + 1
    return f'POS-{ymd}-{count:04d}'


def _next_session_code(db: Session, register: Register, business_date: str):
    ymd = (business_date or today_iso()).replace('-', '')
    count = db.query(RegisterSession).filter(RegisterSession.register_id == register.id, RegisterSession.business_date == business_date).count() + 1
    return f'SES-{register.code}-{ymd}-{count:02d}'


def create_outbox_event(db: Session, *, aggregate_type: str, aggregate_id: int, event_type: str, payload: dict, idempotency_key: str | None = None):
    key = idempotency_key or f'{event_type}:{aggregate_id}'
    existing = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.idempotency_key == key).first()
    if existing:
        existing.payload_json = json.dumps(payload, ensure_ascii=False)
        if existing.status in {'failed', 'blocked'}:
            existing.status = 'pending'
            existing.last_error = None
        db.add(existing)
        db.flush()
        return existing
    event = SyncOutboxEvent(
        event_uuid=str(uuid.uuid4()),
        aggregate_type=aggregate_type,
        aggregate_id=int(aggregate_id),
        event_type=event_type,
        idempotency_key=key,
        payload_json=json.dumps(payload, ensure_ascii=False),
        status='pending',
    )
    db.add(event)
    db.flush()
    return event


def open_register_session(db: Session, payload: RegisterSessionOpen, user_id: int | None = None):
    register = db.query(Register).options(selectinload(Register.outlet)).filter(Register.id == int(payload.register_id)).first()
    if not register:
        raise ValueError('Register not found.')
    if not register.accounting_financial_account_id:
        raise ValueError('This register is missing its Accounting drawer mapping. Ask a manager to map the register before opening a shift.')
    existing = db.query(RegisterSession).filter(RegisterSession.register_id == register.id, RegisterSession.status == 'open').first()
    if existing:
        raise ValueError('This register already has an open session.')
    row = RegisterSession(
        session_code=_next_session_code(db, register, payload.business_date),
        register_id=register.id,
        business_date=payload.business_date,
        shift_name=payload.shift_name,
        status='open',
        opened_by_user_id=user_id,
        opening_float=float(payload.opening_float or 0),
        opening_note=payload.opening_note,
        opened_at_text=now_iso(),
        closing_expected_cash=float(payload.opening_float or 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _audit_event(db, action='session.opened', entity_type='register_session', entity_id=row.id, user_id=user_id, details={'session_id': row.id, 'session_code': row.session_code, 'register_id': row.register_id, 'opening_float': row.opening_float})
    if row.opening_float > 0:
        create_cash_movement(
            db,
            CashMovementCreate(
                register_session_id=row.id,
                direction='in',
                movement_type='opening_float',
                category='Opening Float',
                amount=row.opening_float,
                note=payload.opening_note,
                accounting_financial_account_id=register.accounting_financial_account_id,
            ),
            approved_by_user_id=user_id,
            source_order_id=None,
            create_outbox=True,
        )
    row = db.query(RegisterSession).options(selectinload(RegisterSession.register), selectinload(RegisterSession.opened_by), selectinload(RegisterSession.orders)).filter(RegisterSession.id == row.id).first()
    return _serialize_session(row)


def list_register_sessions(db: Session, status: str | None = None, register_id: int | None = None, limit: int = 200):
    query = db.query(RegisterSession).options(
        selectinload(RegisterSession.register),
        selectinload(RegisterSession.opened_by),
        selectinload(RegisterSession.closed_by),
        selectinload(RegisterSession.orders),
    ).order_by(RegisterSession.id.desc())
    if status:
        query = query.filter(RegisterSession.status == status)
    if register_id:
        query = query.filter(RegisterSession.register_id == int(register_id))
    return [_serialize_session(row) for row in query.limit(limit).all()]


def get_register_session(db: Session, session_id: int):
    row = db.query(RegisterSession).options(
        selectinload(RegisterSession.register),
        selectinload(RegisterSession.opened_by),
        selectinload(RegisterSession.closed_by),
        selectinload(RegisterSession.orders).selectinload(PosOrder.lines),
    ).filter(RegisterSession.id == int(session_id)).first()
    if not row:
        raise ValueError('Register session not found.')
    data = _serialize_session(row)
    data['orders'] = [_serialize_order(order, include_lines=True, db=db) for order in (row.orders or [])]
    return data


def close_register_session(db: Session, session_id: int, payload: RegisterSessionClose, user_id: int | None = None):
    row = db.query(RegisterSession).options(selectinload(RegisterSession.register)).filter(RegisterSession.id == int(session_id)).first()
    if not row:
        raise ValueError('Register session not found.')
    if row.status != 'open':
        raise ValueError('Only open sessions can be closed.')
    if not row.register or not row.register.accounting_financial_account_id:
        raise ValueError('This register is missing its Accounting drawer mapping. Ask a manager to map the register before closing the shift.')
    expected = compute_session_expected_cash(db, row.id)
    close_mode = (payload.close_mode or ('blind' if payload.blind_close else 'verified')).strip().lower()
    row.closing_actual_cash = float(payload.closing_actual_cash or 0)
    row.variance_amount = row.closing_actual_cash - expected
    row.close_mode = close_mode
    row.blind_close = bool(payload.blind_close or close_mode == 'blind')
    row.denomination_json = json.dumps([line.model_dump() for line in (payload.denomination_lines or [])]) if payload.denomination_lines else '[]'
    row.variance_note = (payload.variance_note or '').strip() or None
    row.close_sign_off_name = (payload.sign_off_name or '').strip() or None
    row.close_sign_off_role = (payload.sign_off_role or '').strip() or None
    note_parts = [payload.closing_note or '']
    if close_mode == 'blind':
        note_parts.append('Blind close submitted.')
    if abs(row.variance_amount) > 0.009:
        note_parts.append(f'Variance investigation required: {row.variance_amount:.2f}')
    if row.variance_note:
        note_parts.append(f'Variance note: {row.variance_note}')
    if row.close_sign_off_name:
        note_parts.append(f'Signed off by: {row.close_sign_off_name}{f" ({row.close_sign_off_role})" if row.close_sign_off_role else ""}')
    row.closing_note = ' '.join([p for p in note_parts if p]).strip() or None
    row.closed_by_user_id = user_id
    row.closed_at_text = now_iso()
    row.status = 'closed'
    db.add(row)
    db.commit()
    db.refresh(row)
    create_outbox_event(
        db,
        aggregate_type='register_session',
        aggregate_id=row.id,
        event_type='session.closed',
        payload={
            'session_id': row.id,
            'session_code': row.session_code,
            'register_id': row.register_id,
            'business_date': row.business_date,
            'closing_actual_cash': row.closing_actual_cash,
            'closing_expected_cash': row.closing_expected_cash,
            'variance_amount': row.variance_amount,
            'close_mode': close_mode,
            'blind_close': bool(payload.blind_close or close_mode == 'blind'),
            'denomination_lines': [line.model_dump() for line in (payload.denomination_lines or [])],
            'variance_note': row.variance_note,
            'sign_off_name': row.close_sign_off_name,
            'sign_off_role': row.close_sign_off_role,
            'register_accounting_financial_account_id': row.register.accounting_financial_account_id,
        },
    )
    db.commit()
    _audit_event(db, action='session.closed', entity_type='register_session', entity_id=row.id, user_id=user_id, details={'session_id': row.id, 'session_code': row.session_code, 'variance_amount': row.variance_amount, 'close_mode': close_mode, 'variance_note': row.variance_note, 'sign_off_name': row.close_sign_off_name})
    row = db.query(RegisterSession).options(selectinload(RegisterSession.register), selectinload(RegisterSession.opened_by), selectinload(RegisterSession.closed_by), selectinload(RegisterSession.orders)).filter(RegisterSession.id == row.id).first()
    return _serialize_session(row)


def reopen_register_session(db: Session, session_id: int, payload: RegisterSessionReopen, user_id: int | None = None, approved_by_user_id: int | None = None):
    row = db.query(RegisterSession).options(selectinload(RegisterSession.register)).filter(RegisterSession.id == int(session_id)).first()
    if not row:
        raise ValueError('Register session not found.')
    if row.status != 'closed':
        raise ValueError('Only closed sessions can be reopened.')
    existing_open = db.query(RegisterSession).filter(RegisterSession.register_id == row.register_id, RegisterSession.status == 'open', RegisterSession.id != row.id).first()
    if existing_open:
        raise ValueError('Another session is already open for this register.')
    approval = _record_approval(db, approval_type='reopen_session', entity_type='register_session', entity_id=row.id, requested_by_user_id=user_id, approved_by_user_id=approved_by_user_id, requested_reason=payload.reason, decision_note=payload.note, request_details={'session_id': row.id, 'session_code': row.session_code, 'reason': payload.reason}, required=True, commit=False)
    row.status = 'open'
    reopen_note = f"Reopened at {now_iso()}"
    if payload.reason:
        reopen_note += f". Reason: {payload.reason}"
    row.closing_note = ' '.join([p for p in [row.closing_note, reopen_note] if p]).strip()
    row.reopen_reason = payload.reason
    row.reopen_note = payload.note
    row.closed_by_user_id = user_id
    row.closed_at_text = None
    row.closing_actual_cash = None
    row.variance_amount = 0
    db.add(row)
    _audit_event(db, action='session.reopened', entity_type='register_session', entity_id=row.id, user_id=user_id, details={'session_id': row.id, 'session_code': row.session_code, 'reason': payload.reason, 'approval_id': approval.get('id') if approval else None}, commit=False)
    db.commit()
    row = db.query(RegisterSession).options(selectinload(RegisterSession.register), selectinload(RegisterSession.opened_by), selectinload(RegisterSession.closed_by), selectinload(RegisterSession.orders)).filter(RegisterSession.id == row.id).first()
    return _serialize_session(row)


def create_order(db: Session, payload: OrderCreate, user_id: int | None = None):
    session = db.query(RegisterSession).options(selectinload(RegisterSession.register)).filter(RegisterSession.id == int(payload.register_session_id)).first()
    if not session:
        raise ValueError('Register session not found.')
    if session.status != 'open':
        raise ValueError('Order can only be created on an open session.')
    if settings.is_strict_environment and session.business_date != today_iso():
        raise ValueError(
            f'This register session is stale ({session.business_date}). Close or roll forward the session before creating an order for {today_iso()}.'
        )
    if not payload.lines:
        raise ValueError('Order must contain at least one line.')
    row = PosOrder(
        order_uuid=str(uuid.uuid4()),
        order_no=_next_order_no(db, session.business_date),
        register_session_id=session.id,
        register_id=session.register_id,
        cashier_user_id=user_id,
        business_date=session.business_date,
        order_type=payload.order_type or session.register.default_order_type,
        source_channel=payload.source_channel,
        guest_name=payload.guest_name,
        service_area=_clean_text(payload.service_area),
        table_label=payload.table_label,
        seat_count=payload.seat_count,
        status='draft',
        kitchen_status='queued',
        note=payload.note,
    )
    db.add(row)
    db.flush()
    _rebuild_order_lines(db, row, payload.lines)
    db.add(row)
    if float(row.discount_amount or 0) > 0:
        _record_approval(db, approval_type='discount', entity_type='order', entity_id=row.id, requested_by_user_id=user_id, approved_by_user_id=getattr(payload, 'approved_by_user_id', None), requested_reason='Order discount applied', request_details={'order_id': row.id, 'order_no': row.order_no, 'discount_amount': row.discount_amount}, required=True, commit=False)
    _audit_event(db, action='order.created', entity_type='order', entity_id=row.id, user_id=user_id, details={'order_id': row.id, 'order_no': row.order_no, 'status': row.status, 'total_amount': row.total_amount, 'discount_amount': row.discount_amount}, commit=False)
    db.commit()
    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(PosOrder.id == row.id).first()
    _publish_kds_refresh(_order_stations(row), reason='ticket_created', payload={'order_id': row.id, 'order_no': row.order_no})
    return _serialize_order(row, include_lines=True, db=db)


def _rebuild_order_lines(db: Session, row: PosOrder, line_payloads):
    row.lines.clear()
    db.flush()
    subtotal = 0.0
    discount = 0.0
    tax_amount = 0.0
    service_charge = 0.0
    stations = []
    for item in line_payloads or []:
        catalog_item_id = getattr(item, 'catalog_item_id', None)
        if catalog_item_id is None and isinstance(item, dict):
            catalog_item_id = item.get('catalog_item_id')
        catalog = db.get(CatalogItem, int(catalog_item_id or 0))
        if not catalog:
            raise ValueError(f'Catalog item {catalog_item_id} not found.')
        qty_value = getattr(item, 'quantity', None)
        if qty_value is None and isinstance(item, dict):
            qty_value = item.get('quantity')
        qty = float(qty_value or 0)
        if qty <= 0:
            raise ValueError('Line quantity must be greater than zero.')
        unit_price_value = getattr(item, 'unit_price', None)
        if unit_price_value is None and isinstance(item, dict):
            unit_price_value = item.get('unit_price')
        catalog_price = float(catalog.price or 0)
        unit_price = float(unit_price_value if unit_price_value is not None else catalog_price)
        if abs(unit_price - catalog_price) >= 0.01:
            raise ValueError(
                f'{catalog.display_name or catalog.menu_item_name} price does not match the current catalog price. '
                'Refresh the catalog and use the discount workflow for an authorized reduction.'
            )
        discount_value = getattr(item, 'discount_amount', None)
        if discount_value is None and isinstance(item, dict):
            discount_value = item.get('discount_amount')
        line_discount = float(discount_value or 0)
        gross = qty * unit_price
        line_total = max(gross - line_discount, 0)
        tax_amount += line_total * float(catalog.tax_rate or 0)
        service_charge += line_total * float(catalog.service_charge_rate or 0)
        subtotal += gross
        discount += line_discount
        prep_station = normalize_kds_station(catalog.prep_station or catalog.module_slug)
        stations.append(prep_station)
        requested_status = getattr(item, 'kitchen_status', None)
        if requested_status is None and isinstance(item, dict):
            requested_status = item.get('kitchen_status')
        requested_status = str(requested_status or 'queued').strip().lower()
        if requested_status not in {'held', 'queued'}:
            requested_status = 'queued'
        row.lines.append(PosOrderLine(
            catalog_item_id=catalog.id,
            external_menu_item_id=catalog.external_menu_item_id,
            external_sku_id=catalog.external_sku_id,
            item_name_snapshot=catalog.display_name,
            prep_station=prep_station,
            quantity=qty,
            unit_price=unit_price,
            discount_amount=line_discount,
            line_total=line_total,
            kitchen_status=requested_status,
            acknowledgement_state='unacknowledged',
            item_readiness='not_ready',
            ready_quantity=0,
            note=(item.get('note') if isinstance(item, dict) else getattr(item, 'note', None)),
        ))
    row.subtotal_amount = round(subtotal, 2)
    row.discount_amount = round(discount, 2)
    row.tax_amount = round(tax_amount, 2)
    row.service_charge_amount = round(service_charge, 2)
    row.total_amount = round(subtotal - discount + tax_amount + service_charge, 2)
    row.balance_due = row.total_amount - row.paid_amount
    if stations:
        statuses = {line.kitchen_status for line in row.lines}
        row.kitchen_status = 'held' if statuses == {'held'} else 'queued'
    return row


def update_order(db: Session, order_id: int, payload: OrderUpdate, user_id: int | None = None):
    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(PosOrder.id == int(order_id)).first()
    if not row:
        raise ValueError('Order not found.')
    if row.status in {'paid', 'voided'}:
        raise ValueError('Paid or voided orders can no longer be edited.')
    data = payload.model_dump(exclude_unset=True)
    line_payloads = data.pop('lines', None)
    approved_by_user_id = data.pop('approved_by_user_id', None)
    for key, value in data.items():
        setattr(row, key, value)
    if line_payloads is not None:
        _rebuild_order_lines(db, row, line_payloads)
    db.add(row)
    if float(row.discount_amount or 0) > 0:
        _record_approval(db, approval_type='discount', entity_type='order', entity_id=row.id, requested_by_user_id=user_id, approved_by_user_id=approved_by_user_id, requested_reason='Order discount updated', request_details={'order_id': row.id, 'order_no': row.order_no, 'discount_amount': row.discount_amount}, required=True, commit=False)
    _audit_event(db, action='order.updated', entity_type='order', entity_id=row.id, user_id=user_id, details={'order_id': row.id, 'order_no': row.order_no, 'status': row.status, 'discount_amount': row.discount_amount}, commit=False)
    db.commit()
    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(PosOrder.id == row.id).first()
    _publish_kds_refresh(_order_stations(row), reason='ticket_updated', payload={'order_id': row.id, 'order_no': row.order_no})
    return _serialize_order(row, include_lines=True, db=db)


def list_orders(db: Session, status: str | None = None, session_id: int | None = None, q: str | None = None, business_date: str | None = None, limit: int = 200):
    query = db.query(PosOrder).options(
        selectinload(PosOrder.lines).selectinload(PosOrderLine.catalog_item),
        selectinload(PosOrder.payments),
        selectinload(PosOrder.register),
        selectinload(PosOrder.cashier),
    ).order_by(PosOrder.id.desc())
    if status:
        query = query.filter(PosOrder.status == status)
    if session_id:
        query = query.filter(PosOrder.register_session_id == int(session_id))
    if business_date:
        query = query.filter(PosOrder.business_date == business_date)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            PosOrder.order_no.ilike(like)
            | PosOrder.guest_name.ilike(like)
            | PosOrder.service_area.ilike(like)
            | PosOrder.table_label.ilike(like)
            | PosOrder.note.ilike(like)
        )
    return [_serialize_order(row, include_lines=True, db=db) for row in query.limit(limit).all()]


def get_order(db: Session, order_id: int):
    row = db.query(PosOrder).options(
        selectinload(PosOrder.lines),
        selectinload(PosOrder.payments),
        selectinload(PosOrder.register),
        selectinload(PosOrder.cashier),
    ).filter(PosOrder.id == int(order_id)).first()
    if not row:
        raise ValueError('Order not found.')
    return _serialize_order(row, include_lines=True, db=db)



def list_in_house_bookings(db: Session, stay_date: str | None = None, room_number: str | None = None, q: str | None = None, active_only: bool = True, limit: int = 200):
    query = db.query(InHouseBookingSnapshot).order_by(InHouseBookingSnapshot.stay_date.desc(), InHouseBookingSnapshot.room_number.asc(), InHouseBookingSnapshot.id.desc())
    if active_only:
        query = query.filter(InHouseBookingSnapshot.is_active == True)
    if stay_date:
        query = query.filter(InHouseBookingSnapshot.stay_date == stay_date)
    if room_number:
        query = query.filter(InHouseBookingSnapshot.room_number.ilike(f"%{room_number.strip()}%"))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            InHouseBookingSnapshot.room_number.ilike(like)
            | InHouseBookingSnapshot.guest_name.ilike(like)
            | InHouseBookingSnapshot.guest_label.ilike(like)
            | InHouseBookingSnapshot.beds24_booking_id.ilike(like)
        )
    return [_serialize_in_house_booking_snapshot(row) for row in query.limit(limit).all()]



def create_in_house_booking_snapshot(db: Session, payload: InHouseBookingSnapshotCreate):
    data = payload.model_dump()
    stay_date = str(data.get('stay_date') or '').strip()
    room_number = str(data.get('room_number') or '').strip()
    if not stay_date:
        raise ValueError('stay_date is required.')
    if not room_number:
        raise ValueError('room_number is required.')
    existing = db.query(InHouseBookingSnapshot).filter(
        InHouseBookingSnapshot.stay_date == stay_date,
        InHouseBookingSnapshot.room_number == room_number,
        InHouseBookingSnapshot.is_active == True,
    ).order_by(InHouseBookingSnapshot.id.desc()).first()
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return _serialize_in_house_booking_snapshot(existing)
    row = InHouseBookingSnapshot(**data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_in_house_booking_snapshot(row)



def update_in_house_booking_snapshot(db: Session, snapshot_id: int, payload: InHouseBookingSnapshotUpdate):
    row = db.get(InHouseBookingSnapshot, int(snapshot_id))
    if not row:
        raise ValueError('In-house booking snapshot not found.')
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _serialize_in_house_booking_snapshot(row)



def list_room_charge_postings(db: Session, posting_status: str | None = None, stay_date: str | None = None, room_number: str | None = None, q: str | None = None, limit: int = 200):
    query = db.query(RoomChargePosting).options(
        selectinload(RoomChargePosting.order),
        selectinload(RoomChargePosting.booking_snapshot),
        selectinload(RoomChargePosting.posted_by),
        selectinload(RoomChargePosting.created_by),
        selectinload(RoomChargePosting.selected_by),
    ).order_by(RoomChargePosting.id.desc())
    if posting_status:
        query = query.filter(RoomChargePosting.posting_status == posting_status)
    if stay_date:
        query = query.filter(RoomChargePosting.booking_date == stay_date)
    if room_number:
        query = query.filter(RoomChargePosting.room_number.ilike(f"%{room_number.strip()}%"))
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            RoomChargePosting.room_number.ilike(like)
            | RoomChargePosting.guest_label.ilike(like)
            | RoomChargePosting.beds24_booking_id.ilike(like)
            | RoomChargePosting.beds24_posting_reference.ilike(like)
        )
    return [_serialize_room_charge_posting(row) for row in query.limit(limit).all()]



def get_room_charge_posting(db: Session, posting_id: int):
    row = db.query(RoomChargePosting).options(
        selectinload(RoomChargePosting.order),
        selectinload(RoomChargePosting.booking_snapshot),
        selectinload(RoomChargePosting.posted_by),
        selectinload(RoomChargePosting.created_by),
        selectinload(RoomChargePosting.selected_by),
    ).filter(RoomChargePosting.id == int(posting_id)).first()
    if not row:
        raise ValueError('Room charge posting not found.')
    return _serialize_room_charge_posting(row)



def update_room_charge_posting_status(db: Session, posting_id: int, payload: RoomChargePostingStatusUpdate, user_id: int | None = None, approved_by_user_id: int | None = None):
    row = db.query(RoomChargePosting).options(
        selectinload(RoomChargePosting.order),
        selectinload(RoomChargePosting.booking_snapshot),
        selectinload(RoomChargePosting.posted_by),
        selectinload(RoomChargePosting.created_by),
        selectinload(RoomChargePosting.selected_by),
    ).filter(RoomChargePosting.id == int(posting_id)).first()
    if not row:
        raise ValueError('Room charge posting not found.')
    status = str(payload.posting_status or '').strip().lower().replace(' ', '_')
    if status not in ROOM_CHARGE_STATUSES:
        raise ValueError('Unsupported room charge status.')
    previous_status = row.posting_status
    if status != previous_status:
        allowed_next = ALLOWED_ROOM_CHARGE_TRANSITIONS.get(previous_status, set())
        if status not in allowed_next:
            raise ValueError(f'Cannot change room charge from {_room_charge_status_label(previous_status)} to {_room_charge_status_label(status)}.')
    row.posting_status = status
    if payload.beds24_posting_reference is not None:
        row.beds24_posting_reference = _clean_text(payload.beds24_posting_reference)
    if payload.note is not None:
        row.note = _clean_text(payload.note)
    if payload.dispute_note is not None:
        row.dispute_note = _clean_text(payload.dispute_note)
    if payload.bill_to is not None:
        row.bill_to = _clean_text(payload.bill_to)
    if payload.rejected_reason is not None:
        row.rejected_reason = _clean_text(payload.rejected_reason)
    if status == 'posted_to_beds24':
        row.posted_to_beds24_at_text = _clean_text(payload.posted_to_beds24_at) or now_iso()
        row.posted_by_user_id = user_id
    elif payload.posted_to_beds24_at is not None:
        row.posted_to_beds24_at_text = _clean_text(payload.posted_to_beds24_at)
    if status == 'settled_at_frontdesk':
        row.settled_at_frontdesk_at_text = now_iso()
        row.payment_date = _clean_text(payload.payment_date) or today_iso()
        row.later_payment_status = _clean_text(payload.later_payment_status) or 'settled'
    elif status in {'posted_to_beds24', 'pending_frontdesk_post', 'rejected', 'disputed', 'written_off', 'cancelled'}:
        # Settlement fields are intentionally ignored outside settlement actions.
        pass
    db.add(row)
    approval = None
    if status == 'disputed':
        approval = _record_approval(db, approval_type='room_charge_dispute', entity_type='room_charge_posting', entity_id=row.id, requested_by_user_id=user_id, approved_by_user_id=approved_by_user_id, requested_reason=row.dispute_note or 'Room charge disputed', request_details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'previous_status': previous_status, 'posting_status': status}, required=True, commit=False)
    elif status == 'written_off':
        approval = _record_approval(db, approval_type='room_charge_write_off', entity_type='room_charge_posting', entity_id=row.id, requested_by_user_id=user_id, approved_by_user_id=approved_by_user_id, requested_reason=row.note or 'Room charge write-off', request_details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'previous_status': previous_status, 'posting_status': status}, required=True, commit=False)
    if status == 'posted_to_beds24':
        _audit_event(db, action='room_charge.marked_posted_manually', entity_type='room_charge_posting', entity_id=row.id, user_id=user_id, details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'beds24_posting_reference': row.beds24_posting_reference}, commit=False)
    elif status == 'rejected':
        _audit_event(db, action='room_charge.rejected', entity_type='room_charge_posting', entity_id=row.id, user_id=user_id, details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'rejected_reason': row.rejected_reason}, commit=False)
    elif status == 'disputed':
        _audit_event(db, action='room_charge.disputed', entity_type='room_charge_posting', entity_id=row.id, user_id=user_id, details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'dispute_note': row.dispute_note, 'approval_id': approval.get('id') if approval else None}, commit=False)
    elif status == 'written_off':
        _audit_event(db, action='room_charge.written_off', entity_type='room_charge_posting', entity_id=row.id, user_id=user_id, details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'note': row.note, 'approval_id': approval.get('id') if approval else None}, commit=False)
    if status == 'settled_at_frontdesk':
        _audit_event(db, action='room_charge.settlement_updated', entity_type='room_charge_posting', entity_id=row.id, user_id=user_id, details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'posting_status': status, 'later_payment_status': row.later_payment_status, 'payment_date': row.payment_date}, commit=False)
    if previous_status == 'disputed' and status != 'disputed':
        _audit_event(db, action='room_charge.dispute_resolved', entity_type='room_charge_posting', entity_id=row.id, user_id=user_id, details={'room_charge_posting_id': row.id, 'order_id': row.order_id, 'from_status': previous_status, 'to_status': status}, commit=False)
    db.commit()
    row = db.query(RoomChargePosting).options(
        selectinload(RoomChargePosting.order),
        selectinload(RoomChargePosting.booking_snapshot),
        selectinload(RoomChargePosting.posted_by),
        selectinload(RoomChargePosting.created_by),
        selectinload(RoomChargePosting.selected_by),
    ).filter(RoomChargePosting.id == row.id).first()
    return _serialize_room_charge_posting(row)


def set_order_status(db: Session, order_id: int, status: str, user_id: int | None = None):
    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(PosOrder.id == int(order_id)).first()
    if not row:
        raise ValueError('Order not found.')
    if row.status in {'paid', 'folio_pending', 'voided'}:
        raise ValueError('Finalized orders can no longer change draft / hold status.')
    row.status = status
    db.add(row)
    db.commit()
    _audit_event(db, action='order.status_updated', entity_type='order', entity_id=row.id, user_id=user_id, details={'order_id': row.id, 'order_no': row.order_no, 'status': status})
    _publish_kds_refresh(_order_stations(row), reason='ticket_status_updated', payload={'order_id': row.id, 'order_no': row.order_no, 'status': status})
    return _serialize_order(row, include_lines=True, db=db)


def transfer_order_table(db: Session, order_id: int, target_table_label: str, target_service_area: str | None = None, user_id: int | None = None):
    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(PosOrder.id == int(order_id)).first()
    if not row:
        raise ValueError('Order not found.')
    if row.status not in ACTIVE_TABLE_ORDER_STATUSES:
        raise ValueError('Only active unpaid table orders can be transferred.')
    target = (target_table_label or '').strip()
    target_area = _clean_text(target_service_area) or row.service_area
    if not target:
        raise ValueError('target_table_label is required.')
    occupied_query = db.query(PosOrder).filter(
        PosOrder.id != row.id,
        PosOrder.table_label == target,
        PosOrder.status.in_(sorted(ACTIVE_TABLE_ORDER_STATUSES)),
    )
    if target_area:
        occupied_query = occupied_query.filter(PosOrder.service_area == target_area)
    occupied = occupied_query.first()
    if occupied:
        area_label = f'{target_area} · ' if target_area else ''
        raise ValueError(f'Table {area_label}{target} already has an active order. Use merge instead.')
    previous = row.table_label
    previous_area = row.service_area
    row.service_area = target_area
    row.table_label = target
    from_label = f'{previous_area} · {previous}' if previous_area and previous else (previous or 'unassigned')
    to_label = f'{target_area} · {target}' if target_area else target
    row.note = f'{row.note or ""}\nTransferred from {from_label} to {to_label}.'.strip()
    db.add(row)
    db.commit()
    _audit_event(db, action='order.table_transferred', entity_type='order', entity_id=row.id, user_id=user_id, details={'order_id': row.id, 'order_no': row.order_no, 'from_service_area': previous_area, 'from_table': previous, 'to_service_area': target_area, 'to_table': target})
    return get_order(db, row.id)


def merge_order_table(db: Session, order_id: int, target_table_label: str, target_service_area: str | None = None, user_id: int | None = None):
    source = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.refunds)).filter(PosOrder.id == int(order_id)).first()
    if not source:
        raise ValueError('Order not found.')
    if source.status not in ACTIVE_TABLE_ORDER_STATUSES:
        raise ValueError('Only active unpaid table orders can be merged.')
    if source.status == 'folio_pending' or float(source.paid_amount or 0) > 0 or source.payments:
        raise ValueError('Partially paid orders cannot be merged. Refund or settle first.')
    if source.refunds:
        raise ValueError('Orders with refund records cannot be merged.')
    if _get_room_charge_postings_for_order(db, source.id):
        raise ValueError('Orders with room-charge postings cannot be merged.')
    target_label = (target_table_label or '').strip()
    target_area = _clean_text(target_service_area) or source.service_area
    target_query = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(
        PosOrder.id != source.id,
        PosOrder.table_label == target_label,
        PosOrder.status.in_(sorted(ACTIVE_TABLE_ORDER_STATUSES)),
    )
    if target_area:
        target_query = target_query.filter(PosOrder.service_area == target_area)
    target = target_query.first()
    if not target:
        area_label = f'{target_area} · ' if target_area else ''
        raise ValueError(f'Table {area_label}{target_label or "(blank)"} does not have an active order to merge into.')
    if target.register_session_id != source.register_session_id:
        raise ValueError('Orders must be in the same register session before merging.')

    source_label = source.table_label
    for line in list(source.lines or []):
        line.order = target
        db.add(line)
    db.flush()
    subtotal = 0.0
    discount = 0.0
    tax_amount = 0.0
    service_charge = 0.0
    for line in target.lines or []:
        catalog = db.get(CatalogItem, int(line.catalog_item_id))
        gross = float(line.quantity or 0) * float(line.unit_price or 0)
        subtotal += gross
        discount += float(line.discount_amount or 0)
        tax_amount += float(line.line_total or 0) * float(catalog.tax_rate or 0)
        service_charge += float(line.line_total or 0) * float(catalog.service_charge_rate or 0)
    target.subtotal_amount = round(subtotal, 2)
    target.discount_amount = round(discount, 2)
    target.tax_amount = round(tax_amount, 2)
    target.service_charge_amount = round(service_charge, 2)
    target.total_amount = round(subtotal - discount + tax_amount + service_charge, 2)
    target.balance_due = round(float(target.total_amount or 0) - float(target.paid_amount or 0), 2)
    if source.seat_count:
        target.seat_count = int(target.seat_count or 0) + int(source.seat_count or 0)
    merge_from_label = f'{source.service_area} · {source_label}' if source.service_area and source_label else (source_label or 'unassigned')
    merge_note = f'Merged order {source.order_no} from {merge_from_label}'
    if source.guest_name:
        merge_note += f' · Guest/group: {source.guest_name}'
    if source.seat_count:
        merge_note += f' · Pax: {source.seat_count}'
    target.note = f'{target.note or ""}\n{merge_note}.'.strip()
    source.status = 'merged'
    source.kitchen_status = 'merged'
    source.void_reason = None
    target_to_label = f'{target.service_area} · {target_label}' if target.service_area and target_label else target_label
    source.note = f'{source.note or ""}\nMerged into {target.order_no} at {target_to_label}.'.strip()
    db.add(target)
    db.add(source)
    db.commit()
    _audit_event(db, action='order.table_merged', entity_type='order', entity_id=target.id, user_id=user_id, details={'source_order_id': source.id, 'source_order_no': source.order_no, 'source_service_area': source.service_area, 'source_table': source_label, 'source_guest_name': source.guest_name, 'source_seat_count': source.seat_count, 'target_order_id': target.id, 'target_order_no': target.order_no, 'target_service_area': target.service_area, 'target_table': target_label})
    return get_order(db, target.id)


def pay_order(db: Session, order_id: int, payload: OrderPayPayload, user_id: int | None = None):
    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.session)).filter(PosOrder.id == int(order_id)).first()
    if not row:
        raise ValueError('Order not found.')
    if row.status in {'voided', 'paid', 'folio_pending'}:
        raise ValueError('This order cannot be paid.')
    if not row.lines:
        raise ValueError('Order must have at least one line before payment.')
    payments = payload.payments or []
    if not payments:
        raise ValueError('At least one payment line is required.')

    db.query(RoomChargePosting).filter(RoomChargePosting.order_id == row.id).delete(synchronize_session=False)
    row.payments.clear()
    db.flush()

    total_covered = 0.0
    immediate_settlement_total = 0.0
    folio_pending_total = 0.0
    tender_labels = []

    for payment in payments:
        tender = _normalize_tender_type(payment.tender_type)
        if not tender:
            raise ValueError('Payment tender_type is required.')
        if tender not in TENDER_SETTLEMENT_META:
            raise ValueError(f'Unsupported tender type: {tender}.')

        amount_applied = round(float(payment.amount_applied or 0), 2)
        if amount_applied <= 0:
            raise ValueError('Payment amount_applied must be greater than zero.')

        meta = _tender_meta(tender)
        payment_account_id = payment.accounting_financial_account_id
        if tender == 'cash':
            payment_account_id = payment_account_id or row.register.accounting_financial_account_id
        if meta['requires_account'] and not payment_account_id:
            raise ValueError(meta['validation_error'])

        if tender == 'room_charge':
            amount_received = round(float(payment.amount_received or 0), 2)
            change_given = 0.0
            payment_account_id = None
            folio_pending_total += amount_applied
        else:
            amount_received = round(float(payment.amount_received if payment.amount_received is not None else amount_applied), 2)
            change_given = round(max(amount_received - amount_applied, 0), 2) if tender == 'cash' else 0.0
            immediate_settlement_total += amount_applied

        payment_row = PosOrderPayment(
            tender_type=tender,
            amount_applied=amount_applied,
            amount_received=amount_received,
            change_given=change_given,
            reference_no=payment.reference_no,
            note=payment.note,
            is_cash=(tender == 'cash'),
            accounting_financial_account_id=payment_account_id,
        )
        row.payments.append(payment_row)
        db.flush()
        if tender == 'room_charge':
            _build_room_charge_posting(db, row, payment_row, payment, user_id=user_id)
        total_covered += amount_applied
        tender_labels.append(tender)

    row.paid_amount = round(immediate_settlement_total, 2)
    row.balance_due = round(max(float(row.total_amount or 0) - total_covered, 0), 2)
    if row.balance_due > 0.009:
        raise ValueError('Payment total is lower than order total.')
    row.primary_tender = tender_labels[0] if len(set(tender_labels)) == 1 else 'mixed'
    row.status = 'folio_pending' if folio_pending_total > 0.009 else 'paid'
    row.kitchen_status = 'queued'
    if payload.note:
        row.note = payload.note
    db.add(row)
    db.commit()
    db.refresh(row)

    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(PosOrder.id == row.id).first()

    for payment in row.payments:
        payment_payload = _serialize_order(row, include_lines=True, db=db)
        payment_payload['payment'] = {
            'id': payment.id,
            'tender_type': payment.tender_type,
            'amount_applied': payment.amount_applied,
            'amount_received': payment.amount_received,
            'change_given': payment.change_given,
            'reference_no': payment.reference_no,
            'note': payment.note,
            'accounting_financial_account_id': payment.accounting_financial_account_id,
            **_payment_settlement_snapshot(payment),
        }
        if payment.is_cash and payment.amount_applied > 0:
            create_cash_movement(
                db,
                CashMovementCreate(
                    register_session_id=row.register_session_id,
                    direction='in',
                    movement_type='cash_sale',
                    category='Cash Sale',
                    amount=payment.amount_applied,
                    note=f'Cash payment for {row.order_no}',
                    reference_no=payment.reference_no or row.order_no,
                    accounting_financial_account_id=payment.accounting_financial_account_id or row.register.accounting_financial_account_id,
                ),
                approved_by_user_id=user_id,
                source_order_id=row.id,
                create_outbox=True,
            )
        elif _normalize_tender_type(payment.tender_type) in FOLIO_PENDING_TENDERS and payment.amount_applied > 0:
            posting = next((item for item in (payment_payload.get('room_charge_postings') or []) if int(item.get('order_payment_id') or 0) == int(payment.id)), None)
            if posting:
                create_outbox_event(
                    db,
                    aggregate_type='room_charge_posting',
                    aggregate_id=posting['id'],
                    event_type='room_charge.request_created',
                    payload={'order': payment_payload, 'room_charge_posting': posting},
                    idempotency_key=f"room_charge.request_created:{posting['id']}",
                )
        elif payment.amount_applied > 0:
            create_outbox_event(
                db,
                aggregate_type='order_payment',
                aggregate_id=payment.id,
                event_type='payment.collected',
                payload=payment_payload,
                idempotency_key=f'payment.collected:{payment.id}',
            )

    create_outbox_event(
        db,
        aggregate_type='order',
        aggregate_id=row.id,
        event_type='order.finalized',
        payload=_serialize_order(row, include_lines=True, db=db),
    )
    db.commit()
    immediate_paid, folio_pending = _order_settlement_totals(row)
    _audit_event(db, action='order.finalized', entity_type='order', entity_id=row.id, user_id=user_id, details={'order_id': row.id, 'order_no': row.order_no, 'status': row.status, 'settlement_state': _order_settlement_state(row), 'paid_amount': immediate_paid, 'folio_pending_amount': folio_pending})
    _publish_kds_refresh(_order_stations(row), reason='ticket_finalized', payload={'order_id': row.id, 'order_no': row.order_no, 'status': row.status})
    return _serialize_order(row, include_lines=True, db=db)


def _next_refund_no(db: Session, business_date: str):
    ymd = (business_date or today_iso()).replace('-', '')
    count = db.query(Refund).count() + 1
    return f'RFD-{ymd}-{count:04d}'


def _approval_user_for_refund(db: Session, approved_by_user_id: int | None):
    if not approved_by_user_id:
        raise ValueError('A manager approval is required before a refund can be processed.')
    approved_user = db.get(__import__('app.models.entities', fromlist=['User']).User, int(approved_by_user_id))
    if not approved_user or not approved_user.is_active:
        raise ValueError('Approving user not found.')
    role_codes = {link.role.code for link in getattr(approved_user, 'user_roles', []) if getattr(link, 'role', None)}
    permission_keys = set(get_user_permission_keys(db, approved_user))
    if approved_user.role not in {'owner', 'manager'} and not ({'owner', 'manager'} & role_codes) and 'orders.void' not in permission_keys and '*' not in permission_keys:
        raise ValueError('Refund approval requires an owner or manager account.')
    return approved_user


def list_refunds(db: Session, order_id: int):
    rows = db.query(Refund).options(
        selectinload(Refund.lines),
        selectinload(Refund.payments),
        selectinload(Refund.order),
        selectinload(Refund.register),
        selectinload(Refund.cashier),
        selectinload(Refund.approved_by),
    ).filter(Refund.order_id == int(order_id)).order_by(Refund.id.desc()).all()
    return [_serialize_refund(row, include_details=True) for row in rows]


def create_refund(db: Session, order_id: int, payload: RefundCreate, cashier_user_id: int | None = None):
    row = db.query(PosOrder).options(
        selectinload(PosOrder.lines),
        selectinload(PosOrder.payments),
        selectinload(PosOrder.register),
        selectinload(PosOrder.cashier),
        selectinload(PosOrder.refunds).selectinload(Refund.lines),
        selectinload(PosOrder.refunds).selectinload(Refund.payments),
    ).filter(PosOrder.id == int(order_id)).first()
    if not row:
        raise ValueError('Order not found.')
    if row.status not in {'paid', 'folio_pending'}:
        raise ValueError('Only orders that have been paid or are folio pending can be refunded.')

    approved_user = _approval_user_for_refund(db, payload.approved_by_user_id)

    refunded_total_existing = round(sum(float(refund.refunded_amount or 0) for refund in (row.refunds or [])), 2)
    refundable_remaining = round(max(float(row.total_amount or 0) - refunded_total_existing, 0), 2)
    if refundable_remaining <= 0.009:
        raise ValueError('This order has already been fully refunded.')

    refunded_qty_by_line = {}
    refunded_tender_by_type = {}
    for refund in (row.refunds or []):
        for line in (refund.lines or []):
            if line.order_line_id:
                refunded_qty_by_line[line.order_line_id] = refunded_qty_by_line.get(line.order_line_id, 0) + float(line.quantity or 0)
        for payment in (refund.payments or []):
            key = (payment.tender_type or '').strip().lower()
            refunded_tender_by_type[key] = refunded_tender_by_type.get(key, 0) + float(payment.amount or 0)

    refund_mode = (payload.refund_mode or 'full').strip().lower()
    refund_lines_payload = []
    refund_amount = 0.0

    if refund_mode == 'full':
        line_total_accum = 0.0
        for line in (row.lines or []):
            already_qty = float(refunded_qty_by_line.get(line.id, 0) or 0)
            remaining_qty = round(max(float(line.quantity or 0) - already_qty, 0), 4)
            if remaining_qty <= 0:
                continue
            ratio = remaining_qty / float(line.quantity or 1)
            line_total = round(float(line.line_total or 0) * ratio, 2)
            refund_lines_payload.append({
                'order_line_id': line.id,
                'item_name_snapshot': line.item_name_snapshot,
                'quantity': remaining_qty,
                'unit_price': line.unit_price,
                'discount_amount': round(float(line.discount_amount or 0) * ratio, 2),
                'refunded_line_total': line_total,
                'note': payload.note,
            })
            line_total_accum += line_total
        refund_amount = round(refundable_remaining, 2)
        remainder = round(refund_amount - round(line_total_accum, 2), 2)
        if abs(remainder) >= 0.01:
            refund_lines_payload.append({
                'order_line_id': None,
                'item_name_snapshot': 'Order-Level Adjustment',
                'quantity': 1,
                'unit_price': remainder,
                'discount_amount': 0,
                'refunded_line_total': remainder,
                'note': 'Taxes / service charge / rounding',
            })
    elif refund_mode == 'lines':
        if not payload.lines:
            raise ValueError('Refund by line requires at least one refund line.')
        for req in payload.lines:
            if not req.order_line_id:
                raise ValueError('Refund line requires order_line_id.')
            source_line = next((line for line in (row.lines or []) if line.id == int(req.order_line_id)), None)
            if not source_line:
                raise ValueError(f'Order line {req.order_line_id} not found.')
            requested_qty = float(req.quantity or 0)
            if requested_qty <= 0:
                raise ValueError('Refund line quantity must be greater than zero.')
            already_qty = float(refunded_qty_by_line.get(source_line.id, 0) or 0)
            remaining_qty = round(max(float(source_line.quantity or 0) - already_qty, 0), 4)
            if requested_qty - remaining_qty > 0.0001:
                raise ValueError(f'Refund quantity exceeds remaining refundable quantity for {source_line.item_name_snapshot}.')
            ratio = requested_qty / float(source_line.quantity or 1)
            line_total = round(float(source_line.line_total or 0) * ratio, 2)
            refund_lines_payload.append({
                'order_line_id': source_line.id,
                'item_name_snapshot': source_line.item_name_snapshot,
                'quantity': requested_qty,
                'unit_price': source_line.unit_price,
                'discount_amount': round(float(source_line.discount_amount or 0) * ratio, 2),
                'refunded_line_total': line_total,
                'note': req.note or payload.note,
            })
            refund_amount += line_total
        refund_amount = round(refund_amount, 2)
    elif refund_mode == 'amount':
        refund_amount = round(float(payload.amount or 0), 2)
        if refund_amount <= 0:
            raise ValueError('Refund amount must be greater than zero.')
        if refund_amount - refundable_remaining > 0.009:
            raise ValueError('Refund amount exceeds remaining refundable balance.')
        refund_lines_payload.append({
            'order_line_id': None,
            'item_name_snapshot': 'Amount Refund',
            'quantity': 1,
            'unit_price': refund_amount,
            'discount_amount': 0,
            'refunded_line_total': refund_amount,
            'note': payload.note or payload.reason_text,
        })
    else:
        raise ValueError('refund_mode must be one of: full, lines, amount.')

    refund_amount = round(refund_amount, 2)
    if refund_amount <= 0:
        raise ValueError('Refund amount must be greater than zero.')
    if refund_amount - refundable_remaining > 0.009:
        raise ValueError('Refund exceeds remaining refundable balance.')

    allocations = []
    room_charge_reversals = []
    remaining_to_allocate = refund_amount
    for payment in (row.payments or []):
        tender = (payment.tender_type or '').strip().lower()
        remaining_for_tender = round(float(payment.amount_applied or 0) - float(refunded_tender_by_type.get(tender, 0) or 0), 2)
        if remaining_for_tender <= 0:
            continue
        alloc = round(min(remaining_for_tender, remaining_to_allocate), 2)
        if alloc <= 0:
            continue
        
        if tender == 'room_charge':
            # For room charges, create reversal posting instead of refund payment
            original_posting = db.query(RoomChargePosting).filter(RoomChargePosting.order_payment_id == payment.id).first()
            if not original_posting:
                raise ValueError('Room charge posting not found for refund allocation.')
            room_charge_reversals.append({
                'original_posting_id': original_posting.id,
                'amount': alloc,
                'reason': payload.reason_text or payload.reason_code or 'Refund',
                'note': payload.note,
            })
        else:
            allocations.append({
                'tender_type': tender,
                'amount': alloc,
                'reference_no': payment.reference_no,
                'note': f'Refund for {row.order_no}',
                'is_cash': bool(payment.is_cash),
                'accounting_financial_account_id': payment.accounting_financial_account_id or (row.register.accounting_financial_account_id if payment.is_cash else None),
            })
        
        remaining_to_allocate = round(remaining_to_allocate - alloc, 2)
        if remaining_to_allocate <= 0.009:
            break
    if remaining_to_allocate > 0.009:
        raise ValueError('Unable to allocate refund across original payment tenders.')

    refund_row = Refund(
        refund_uuid=str(uuid.uuid4()),
        refund_no=_next_refund_no(db, row.business_date),
        order_id=row.id,
        register_session_id=row.register_session_id,
        register_id=row.register_id,
        cashier_user_id=cashier_user_id,
        approved_by_user_id=approved_user.id,
        refund_mode=refund_mode,
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        note=payload.note,
        subtotal_amount=refund_amount,
        refunded_amount=refund_amount,
    )
    db.add(refund_row)
    db.flush()

    for line in refund_lines_payload:
        refund_row.lines.append(RefundLine(**line))

    kitchen_changed = False
    refunded_qty_after = dict(refunded_qty_by_line)
    for refund_line in refund_lines_payload:
        source_line_id = refund_line.get('order_line_id')
        if not source_line_id:
            continue
        refunded_qty_after[source_line_id] = refunded_qty_after.get(source_line_id, 0) + float(refund_line.get('quantity') or 0)
    for source_line in (row.lines or []):
        remaining_qty = max(float(source_line.quantity or 0) - float(refunded_qty_after.get(source_line.id, 0) or 0), 0)
        if remaining_qty <= 0.0001 and source_line.kitchen_status not in {'voided', 'cancelled', 'served'}:
            source_line.kitchen_status = 'voided'
            source_line.item_readiness = 'not_ready'
            source_line.ready_quantity = 0
            db.add(source_line)
            kitchen_changed = True
    if refundable_remaining - refund_amount <= 0.009 and row.kitchen_status not in {'voided', 'cancelled', 'served'}:
        row.kitchen_status = 'voided'
        db.add(row)
        kitchen_changed = True
    for alloc in allocations:
        refund_payment = RefundPayment(
            tender_type=alloc['tender_type'],
            amount=alloc['amount'],
            reference_no=alloc['reference_no'],
            note=alloc['note'],
            is_cash=alloc['is_cash'],
            accounting_financial_account_id=alloc['accounting_financial_account_id'],
        )
        refund_row.payments.append(refund_payment)
    
    # Handle room charge reversals
    for reversal in room_charge_reversals:
        original_posting = db.query(RoomChargePosting).filter(RoomChargePosting.id == reversal['original_posting_id']).first()
        if original_posting:
            # Create reversal posting
            reversal_posting = RoomChargePosting(
                posting_uuid=str(uuid.uuid4()),
                order_id=row.id,
                order_payment_id=None,
                booking_snapshot_id=original_posting.booking_snapshot_id,
                posting_status='pending_frontdesk_post',  # Reversal needs front desk action
                charge_amount=-abs(reversal['amount']),  # Negative amount for reversal
                service_type=original_posting.service_type,
                service_date=original_posting.service_date,
                booking_date=original_posting.booking_date,
                room_number=original_posting.room_number,
                guest_label=original_posting.guest_label,
                beds24_booking_id=original_posting.beds24_booking_id,
                order_source=original_posting.order_source,
                bill_to=original_posting.bill_to,
                note=f"Refund reversal: {reversal['note'] or reversal['reason']}",
                beds24_posting_reference=None,  # Will be set when posted
                later_payment_status='reversal_pending',
                rejected_reason=None,
                dispute_note=None,
                payment_date=row.business_date,
                created_by_user_id=approved_user.id,
            )
            db.add(reversal_posting)
            db.flush()  # To get the id
            
            # Create outbox event for the reversal posting
            reversal_payload = {
                'order': _serialize_order(row, include_lines=True, db=db),
                'room_charge_posting': _serialize_room_charge_posting(reversal_posting),
                'reverses_source_type': 'pos_room_charge',
                'reverses_source_id': original_posting.id,
            }
            create_outbox_event(
                db,
                aggregate_type='room_charge_posting',
                aggregate_id=reversal_posting.id,
                event_type='room_charge.request_created',
                payload=reversal_payload,
                idempotency_key=f"room_charge.request_created:{reversal_posting.id}",
            )
            
            # Create refund payment record for tracking
            refund_payment = RefundPayment(
                tender_type='room_charge',
                amount=reversal['amount'],
                reference_no=f"Reversal of {original_posting.posting_uuid}",
                note=f"Room charge reversal: {reversal['note'] or reversal['reason']}",
                is_cash=False,
                accounting_financial_account_id=None,
            )
            refund_row.payments.append(refund_payment)

    db.add(refund_row)
    approval = _record_approval(db, approval_type='refund', entity_type='refund', entity_id=refund_row.id, requested_by_user_id=cashier_user_id, approved_by_user_id=approved_user.id, requested_reason=payload.reason_text or payload.reason_code or 'Refund processed', request_details={'refund_id': refund_row.id, 'order_id': row.id, 'refund_mode': refund_mode, 'refunded_amount': refund_amount}, required=True, commit=False)
    _audit_event(db, action='refund.created', entity_type='refund', entity_id=refund_row.id, user_id=cashier_user_id, details={'refund_id': refund_row.id, 'order_id': row.id, 'order_no': row.order_no, 'refunded_amount': refund_amount, 'approval_id': approval.get('id') if approval else None}, commit=False)
    db.commit()
    db.refresh(refund_row)

    refund_row = db.query(Refund).options(
        selectinload(Refund.lines),
        selectinload(Refund.payments),
        selectinload(Refund.order),
        selectinload(Refund.register),
        selectinload(Refund.cashier),
        selectinload(Refund.approved_by),
    ).filter(Refund.id == refund_row.id).first()

    for payment in refund_row.payments:
        if payment.tender_type == 'room_charge':
            # Room charge reversals are handled via room_charge.request_created events, not payment.refunded
            continue
        if payment.is_cash and payment.amount > 0:
            create_cash_movement(
                db,
                CashMovementCreate(
                    register_session_id=refund_row.register_session_id,
                    direction='out',
                    movement_type='refund',
                    category='Refund',
                    amount=payment.amount,
                    note=f'Refund {refund_row.refund_no} for {row.order_no}',
                    reference_no=payment.reference_no or refund_row.refund_no,
                    accounting_financial_account_id=payment.accounting_financial_account_id or row.register.accounting_financial_account_id,
                ),
                approved_by_user_id=approved_user.id,
                source_order_id=row.id,
                create_outbox=True,
            )
        else:
            payment_payload = _serialize_refund(refund_row, include_details=True)
            payment_payload['payment'] = {
                'id': payment.id,
                'tender_type': payment.tender_type,
                'amount': payment.amount,
                'reference_no': payment.reference_no,
                'note': payment.note,
                'accounting_financial_account_id': payment.accounting_financial_account_id,
            }
            create_outbox_event(
                db,
                aggregate_type='refund_payment',
                aggregate_id=payment.id,
                event_type='payment.refunded',
                payload=payment_payload,
                idempotency_key=f'payment.refunded:{payment.id}',
            )

    db.commit()
    if kitchen_changed:
        _publish_kds_refresh(_order_stations(row), reason='ticket_cancelled', payload={'order_id': row.id, 'order_no': row.order_no, 'refund_id': refund_row.id})
    return _serialize_refund(refund_row, include_details=True)


def void_order(db: Session, order_id: int, reason: str, user_id: int | None = None, approved_by_user_id: int | None = None):
    row = db.query(PosOrder).options(selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.lines), selectinload(PosOrder.cashier)).filter(PosOrder.id == int(order_id)).first()
    if not row:
        raise ValueError('Order not found.')
    if row.status == 'voided':
        raise ValueError('Order is already voided.')
    approval = _record_approval(db, approval_type='void', entity_type='order', entity_id=row.id, requested_by_user_id=user_id, approved_by_user_id=approved_by_user_id, requested_reason=reason, request_details={'order_id': row.id, 'order_no': row.order_no}, required=True, commit=False)
    row.status = 'voided'
    row.void_reason = reason
    row.kitchen_status = 'voided'
    db.add(row)
    create_outbox_event(
        db,
        aggregate_type='order',
        aggregate_id=row.id,
        event_type='order.voided',
        payload={
            **_serialize_order(row, include_lines=True, db=db),
            'reason': reason,
        },
    )
    _audit_event(db, action='order.voided', entity_type='order', entity_id=row.id, user_id=user_id, details={'order_id': row.id, 'order_no': row.order_no, 'reason': reason, 'approval_id': approval.get('id') if approval else None}, commit=False)
    db.commit()
    db.refresh(row)
    for payment in row.payments:
        if payment.is_cash and payment.amount_applied > 0:
            create_cash_movement(
                db,
                CashMovementCreate(
                    register_session_id=row.register_session_id,
                    direction='out',
                    movement_type='refund',
                    category='Order Void Refund',
                    amount=payment.amount_applied,
                    note=f'Voided order {row.order_no}: {reason}',
                    reference_no=payment.reference_no or row.order_no,
                    accounting_financial_account_id=payment.accounting_financial_account_id or row.register.accounting_financial_account_id,
                ),
                approved_by_user_id=user_id,
                source_order_id=row.id,
                create_outbox=True,
            )
    row = db.query(PosOrder).options(selectinload(PosOrder.lines), selectinload(PosOrder.payments), selectinload(PosOrder.register), selectinload(PosOrder.cashier)).filter(PosOrder.id == row.id).first()
    return _serialize_order(row, include_lines=True, db=db)


def create_cash_movement(
    db: Session,
    payload: CashMovementCreate,
    approved_by_user_id: int | None = None,
    source_order_id: int | None = None,
    create_outbox: bool = True,
):
    session = db.query(RegisterSession).options(selectinload(RegisterSession.register)).filter(RegisterSession.id == int(payload.register_session_id)).first()
    if not session:
        raise ValueError('Register session not found.')
    if session.status != 'open' and not source_order_id:
        raise ValueError('Manual cash movement requires an open register session.')
    explicit_approver = payload.approved_by_user_id or approved_by_user_id
    amount = float(payload.amount or 0)
    if amount <= 0:
        raise ValueError('Cash movement amount must be greater than zero.')
    direction = str(payload.direction or '').strip().lower()
    if direction not in {'in', 'out'}:
        raise ValueError('direction must be in or out.')

    movement_type = str(payload.movement_type or '').strip().lower()
    transfer_types = {'safe_drop', 'bank_deposit', 'drawer_transfer'}
    transfer_requires_approval = movement_type in transfer_types
    requires_approval = bool(payload.requires_approval or transfer_requires_approval)
    if requires_approval and not explicit_approver:
        raise ValueError('This cash movement requires manager approval.')

    from_account_id = payload.accounting_financial_account_id or session.register.accounting_financial_account_id
    to_account_id = payload.to_accounting_financial_account_id
    destination_register = None
    if payload.destination_register_id:
        destination_register = db.query(Register).filter(Register.id == int(payload.destination_register_id)).first()
        if not destination_register:
            raise ValueError('Destination register not found.')
        if destination_register.accounting_financial_account_id:
            to_account_id = destination_register.accounting_financial_account_id
    if movement_type in transfer_types and not from_account_id:
        raise ValueError('Transfer movements require the source register to be linked to an accounting drawer/account.')
    if movement_type in transfer_types and not to_account_id:
        raise ValueError('Transfer movements require a destination account or destination register.')
    if movement_type == 'drawer_transfer' and not destination_register and not payload.destination_register_id:
        raise ValueError('Drawer transfers require a destination register.')

    row = CashMovement(
        cash_event_uuid=str(uuid.uuid4()),
        register_session_id=session.id,
        register_id=session.register_id,
        source_order_id=source_order_id,
        event_date=session.business_date,
        direction=direction,
        movement_type=movement_type,
        category=payload.category,
        amount=round(amount, 2),
        note=payload.note,
        reference_no=payload.reference_no,
        approved_by_user_id=explicit_approver,
        accounting_financial_account_id=from_account_id,
        to_accounting_financial_account_id=to_account_id,
        destination_register_id=payload.destination_register_id,
        transfer_group_uuid=str(uuid.uuid4()) if movement_type in transfer_types else None,
        requires_approval=requires_approval,
    )
    db.add(row)
    db.flush()
    approval = None
    if movement_type in {'paid_out', 'adjustment_in', 'adjustment_out', 'cash_adjustment'} or requires_approval:
        approval_type = 'cash_paid_out' if movement_type == 'paid_out' else 'cash_adjustment'
        if movement_type in transfer_types:
            approval_type = 'cash_adjustment'
        approval = _record_approval(db, approval_type=approval_type, entity_type='cash_movement', entity_id=row.id, requested_by_user_id=None if source_order_id else explicit_approver, approved_by_user_id=explicit_approver, requested_reason=payload.note or payload.category or movement_type, request_details={'cash_movement_id': row.id, 'movement_type': movement_type, 'amount': row.amount, 'session_id': row.register_session_id, 'to_account_id': to_account_id, 'destination_register_id': payload.destination_register_id}, required=True, commit=False)
    _audit_event(db, action='cash_movement.created', entity_type='cash_movement', entity_id=row.id, user_id=explicit_approver or approved_by_user_id, details={'cash_movement_id': row.id, 'session_id': row.register_session_id, 'movement_type': movement_type, 'direction': direction, 'amount': row.amount, 'approval_id': approval.get('id') if approval else None, 'to_accounting_financial_account_id': to_account_id, 'destination_register_id': payload.destination_register_id}, commit=False)
    compute_session_expected_cash(db, session.id, commit=False)
    if create_outbox:
        if movement_type in transfer_types:
            create_outbox_event(
                db,
                aggregate_type='cash_movement',
                aggregate_id=row.id,
                event_type='transfer.created',
                payload={
                    'id': row.id,
                    'cash_event_uuid': row.cash_event_uuid,
                    'movement_type': movement_type,
                    'transfer_date': row.event_date,
                    'from_account_id': from_account_id,
                    'to_account_id': to_account_id,
                    'amount': row.amount,
                    'reference_no': row.reference_no or row.cash_event_uuid,
                    'note': payload.note or payload.category,
                    'destination_register_id': payload.destination_register_id,
                    'transfer_group_uuid': row.transfer_group_uuid,
                    'requires_approval': requires_approval,
                },
                idempotency_key=f'transfer.created:{row.id}',
            )
        else:
            create_outbox_event(
                db,
                aggregate_type='cash_movement',
                aggregate_id=row.id,
                event_type='cash_movement.created',
                payload=_serialize_cash_movement(db.query(CashMovement).options(selectinload(CashMovement.register), selectinload(CashMovement.destination_register), selectinload(CashMovement.source_order), selectinload(CashMovement.approved_by)).filter(CashMovement.id == row.id).first()),
                idempotency_key=f'cash_movement.created:{row.id}',
            )
    db.commit()
    db.refresh(row)
    row = db.query(CashMovement).options(selectinload(CashMovement.register), selectinload(CashMovement.destination_register), selectinload(CashMovement.source_order), selectinload(CashMovement.approved_by)).filter(CashMovement.id == row.id).first()
    return _serialize_cash_movement(row)


def list_cash_movements(db: Session, session_id: int | None = None, limit: int = 300):
    query = db.query(CashMovement).options(
        selectinload(CashMovement.register),
        selectinload(CashMovement.destination_register),
        selectinload(CashMovement.source_order),
        selectinload(CashMovement.approved_by),
    ).order_by(CashMovement.id.desc())
    if session_id:
        query = query.filter(CashMovement.register_session_id == int(session_id))
    return [_serialize_cash_movement(row) for row in query.limit(limit).all()]


def list_kitchen_lines(db: Session, station: str | None = None, statuses: list[str] | None = None):
    statuses = statuses or ['queued', 'acknowledged', 'in_progress', 'ready']
    station = normalize_kds_station(station) if station else None
    query = db.query(PosOrderLine).options(
        selectinload(PosOrderLine.order).selectinload(PosOrder.refunds).selectinload(Refund.lines),
        selectinload(PosOrderLine.acknowledged_by),
    ).join(PosOrder, PosOrder.id == PosOrderLine.order_id).filter(
        PosOrderLine.kitchen_status.in_(statuses),
        PosOrder.status.notin_(['voided', 'cancelled']),
        PosOrder.kitchen_status.notin_(['voided', 'cancelled']),
    )
    if station and station not in {'expo', 'pass'}:
        if station in KDS_STATION_FILTER_ALIASES:
            aliases = KDS_STATION_FILTER_ALIASES[station]
            query = query.filter(or_(PosOrderLine.prep_station.in_([alias for alias in aliases if alias is not None]), PosOrderLine.prep_station.is_(None)))
        else:
            query = query.filter(PosOrderLine.prep_station == station)
    if station in {'expo', 'pass'}:
        query = query.filter(PosOrderLine.kitchen_status.in_(['ready', 'in_progress', 'acknowledged']))
    query = query.order_by(PosOrderLine.id.asc())
    rows = []
    for line in query.all():
        refunded_quantity = sum(
            float(refund_line.quantity or 0)
            for refund in (line.order.refunds or [])
            for refund_line in (refund.lines or [])
            if refund_line.order_line_id == line.id
        ) if line.order else 0
        active_quantity = max(float(line.quantity or 0) - refunded_quantity, 0)
        if active_quantity <= 0.0001:
            continue
        created = utc_iso(getattr(line, 'created_at', None))
        updated = utc_iso(getattr(line, 'updated_at', None))
        priority = 'normal'
        escalation = 'normal'
        age_mins = None
        prep_mins = None
        cycle_to_ready_mins = None
        try:
            created_dt = parse_utc_iso(created)
            started_dt = parse_utc_iso(getattr(line, 'prep_started_at_text', None))
            ready_dt = parse_utc_iso(getattr(line, 'ready_at_text', None))
            current_utc = datetime.now(UTC)
            if created_dt:
                age_mins = max(0, round((current_utc - created_dt).total_seconds() / 60))
                if age_mins >= 25:
                    priority = 'critical'
                    escalation = 'critical'
                elif age_mins >= 15:
                    priority = 'rush'
                    escalation = 'rush'
                elif age_mins >= 8:
                    priority = 'watch'
                    escalation = 'watch'
            if started_dt:
                end_dt = ready_dt or current_utc
                prep_mins = max(0, round((end_dt - started_dt).total_seconds() / 60))
            if created_dt and ready_dt:
                cycle_to_ready_mins = max(0, round((ready_dt - created_dt).total_seconds() / 60))
        except Exception:
            pass
        rows.append({
            'line_id': line.id,
            'order_id': line.order_id,
            'order_no': line.order.order_no if line.order else None,
            'table_label': line.order.table_label if line.order else None,
            'guest_name': line.order.guest_name if line.order else None,
            'prep_station': normalize_kds_station(line.prep_station),
            'item_name_snapshot': line.item_name_snapshot,
            'quantity': active_quantity,
            'original_quantity': line.quantity,
            'refunded_quantity': refunded_quantity,
            'note': line.note,
            'kitchen_status': line.kitchen_status,
            'acknowledgement_state': line.acknowledgement_state,
            'acknowledged_at': line.acknowledged_at_text,
            'acknowledged_by_name': line.acknowledged_by.full_name if getattr(line, 'acknowledged_by', None) and line.acknowledged_by.full_name else (line.acknowledged_by.username if getattr(line, 'acknowledged_by', None) else None),
            'prep_started_at': line.prep_started_at_text,
            'ready_at': line.ready_at_text,
            'served_at': line.served_at_text,
            'item_readiness': line.item_readiness,
            'ready_quantity': min(float(line.ready_quantity or 0), active_quantity),
            'order_status': line.order.status if line.order else None,
            'created_at': created,
            'updated_at': updated,
            'age_minutes': age_mins,
            'prep_minutes': prep_mins,
            'cycle_to_ready_minutes': cycle_to_ready_mins,
            'priority': priority,
            'escalation_state': escalation,
        })
    group_sizes = {}
    for row in rows:
        group_sizes[row['order_id']] = group_sizes.get(row['order_id'], 0) + 1
    for row in rows:
        row['group_size'] = group_sizes.get(row['order_id'], 1)
    rows.sort(key=lambda r: (0 if r['priority'] == 'critical' else 1 if r['priority'] == 'rush' else 2 if r['priority'] == 'watch' else 3, r['order_no'] or '', r['line_id']))
    return rows


def update_kitchen_line_status(db: Session, line_id: int, payload, user_id: int | None = None):
    line = db.query(PosOrderLine).options(selectinload(PosOrderLine.order), selectinload(PosOrderLine.order).selectinload(PosOrder.lines)).filter(PosOrderLine.id == int(line_id)).first()
    if not line:
        raise ValueError('Kitchen line not found.')
    status = str(getattr(payload, 'kitchen_status', payload) or '').strip().lower()
    if status not in {'held', 'queued', 'acknowledged', 'in_progress', 'ready', 'served'}:
        raise ValueError('Unsupported kitchen status.')
    now = now_iso()
    line.kitchen_status = status
    if getattr(payload, 'note', None):
        line.note = payload.note
    if getattr(payload, 'acknowledgement_state', None):
        line.acknowledgement_state = payload.acknowledgement_state
    if status in {'acknowledged', 'in_progress', 'ready', 'served'} and line.acknowledgement_state == 'unacknowledged':
        line.acknowledgement_state = 'acknowledged'
    if line.acknowledgement_state == 'acknowledged' and not line.acknowledged_at_text:
        line.acknowledged_at_text = now
        line.acknowledged_by_user_id = user_id
    if status == 'in_progress' and not line.prep_started_at_text:
        line.prep_started_at_text = now
    ready_quantity = getattr(payload, 'ready_quantity', None)
    if ready_quantity is not None:
        line.ready_quantity = max(0, min(float(ready_quantity or 0), float(line.quantity or 0)))
        line.item_readiness = getattr(payload, 'item_readiness', None) or ('partial' if line.ready_quantity < float(line.quantity or 0) else 'ready')
    if getattr(payload, 'item_readiness', None) and ready_quantity is None:
        line.item_readiness = payload.item_readiness
    if status == 'ready':
        line.ready_at_text = now
        line.ready_quantity = float(line.quantity or 0)
        line.item_readiness = 'ready'
        if not line.prep_started_at_text:
            line.prep_started_at_text = now
    elif status == 'served':
        line.served_at_text = now
        line.item_readiness = 'ready'
        line.ready_quantity = float(line.quantity or 0)
    elif status in {'queued', 'held'}:
        line.item_readiness = 'not_ready'
        line.ready_quantity = 0
    db.add(line)
    db.commit()
    order = line.order
    if order:
        statuses = {row.kitchen_status for row in order.lines}
        if statuses == {'ready'}:
            order.kitchen_status = 'ready'
        elif statuses == {'served'}:
            order.kitchen_status = 'served'
        elif statuses == {'held'}:
            order.kitchen_status = 'held'
        elif 'in_progress' in statuses:
            order.kitchen_status = 'in_progress'
        elif 'acknowledged' in statuses:
            order.kitchen_status = 'acknowledged'
        elif 'queued' in statuses:
            order.kitchen_status = 'queued'
        db.add(order)
        db.commit()
        _publish_kds_refresh(_order_stations(order), reason='ticket_line_updated', payload={'order_id': order.id, 'order_no': order.order_no, 'line_id': line.id, 'kitchen_status': line.kitchen_status})
    return {'ok': True, 'line_id': line.id, 'kitchen_status': line.kitchen_status, 'acknowledgement_state': line.acknowledgement_state, 'item_readiness': line.item_readiness, 'ready_quantity': line.ready_quantity}


def list_outbox_events(db: Session, status: str | None = None, limit: int = 200):
    query = db.query(SyncOutboxEvent).order_by(SyncOutboxEvent.id.desc())
    if status and status != 'suppressed':
        query = query.filter(SyncOutboxEvent.status == status)
    rows = [_serialize_outbox(row) for row in query.limit(limit).all()]
    return [row for row in rows if not status or row['status'] == status]


def dashboard_summary(db: Session):
    open_sessions = db.query(RegisterSession).filter(RegisterSession.status == 'open').count()
    pending_query = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.status.in_(['pending', 'failed', 'blocked']))
    if not settings.inventory_integration_enabled:
        pending_query = pending_query.filter(~SyncOutboxEvent.event_type.like('inventory.%'))
    pending_sync = pending_query.count()
    today = today_iso()
    sales_today = db.query(func.coalesce(func.sum(PosOrder.total_amount), 0)).filter(PosOrder.business_date == today, PosOrder.status.in_(['paid', 'folio_pending'])).scalar() or 0
    cash_today = db.query(func.coalesce(func.sum(CashMovement.amount), 0)).filter(CashMovement.event_date == today, CashMovement.direction == 'in').scalar() or 0
    orders_open = db.query(PosOrder).filter(PosOrder.status.in_(['draft', 'held'])).count()
    latest_session = db.query(RegisterSession).options(selectinload(RegisterSession.register)).order_by(RegisterSession.id.desc()).first()
    settled_statuses = ['paid', 'folio_pending']
    order_count = db.query(PosOrder).filter(PosOrder.business_date == today, PosOrder.status.in_(settled_statuses)).count()
    voided_count = db.query(PosOrder).filter(PosOrder.business_date == today, PosOrder.status == 'voided').count()
    refund_total = db.query(func.coalesce(func.sum(Refund.refunded_amount), 0)).join(PosOrder, Refund.order_id == PosOrder.id).filter(PosOrder.business_date == today).scalar() or 0
    tender_rows = db.query(
        PosOrderPayment.tender_type,
        func.coalesce(func.sum(PosOrderPayment.amount_applied), 0),
        func.count(PosOrderPayment.id),
    ).join(PosOrder, PosOrderPayment.order_id == PosOrder.id).filter(
        PosOrder.business_date == today,
        PosOrder.status.in_(settled_statuses),
    ).group_by(PosOrderPayment.tender_type).all()
    movement_rows = db.query(
        CashMovement.movement_type,
        CashMovement.direction,
        func.coalesce(func.sum(CashMovement.amount), 0),
        func.count(CashMovement.id),
    ).filter(CashMovement.event_date == today).group_by(CashMovement.movement_type, CashMovement.direction).all()
    order_type_rows = db.query(
        PosOrder.order_type,
        func.coalesce(func.sum(PosOrder.total_amount), 0),
        func.count(PosOrder.id),
    ).filter(PosOrder.business_date == today, PosOrder.status.in_(settled_statuses)).group_by(PosOrder.order_type).all()
    open_session_rows = db.query(RegisterSession).options(selectinload(RegisterSession.register)).filter(RegisterSession.status == 'open').order_by(RegisterSession.id.desc()).all()
    z_report = {
        'business_date': today,
        'gross_sales': round(float(sales_today), 2),
        'refund_total': round(float(refund_total), 2),
        'net_sales': round(float(sales_today or 0) - float(refund_total or 0), 2),
        'order_count': order_count,
        'voided_count': voided_count,
        'open_orders': orders_open,
        'sold_out_count': db.query(CatalogItem).filter(CatalogItem.is_active == True, CatalogItem.is_available == False).count(),
        'active_menu_count': db.query(CatalogItem).filter(CatalogItem.is_active == True, CatalogItem.is_available == True).count(),
        'tenders': [
            {'tender_type': tender or 'unknown', 'amount': round(float(amount or 0), 2), 'count': int(count or 0)}
            for tender, amount, count in tender_rows
        ],
        'cash_movements': [
            {'movement_type': movement_type or 'unknown', 'direction': direction or '', 'amount': round(float(amount or 0), 2), 'count': int(count or 0)}
            for movement_type, direction, amount, count in movement_rows
        ],
        'order_types': [
            {'order_type': order_type or 'unknown', 'amount': round(float(amount or 0), 2), 'count': int(count or 0)}
            for order_type, amount, count in order_type_rows
        ],
        'open_sessions': [
            {
                'session_code': row.session_code,
                'register_name': row.register.name if row.register else None,
                'opening_float': round(float(row.opening_float or 0), 2),
                'expected_cash': round(float(row.closing_expected_cash or 0), 2),
            }
            for row in open_session_rows
        ],
    }
    return {
        'open_sessions': open_sessions,
        'pending_sync': pending_sync,
        'sales_today': round(float(sales_today), 2),
        'cash_today': round(float(cash_today), 2),
        'orders_open': orders_open,
        'catalog_count': z_report['active_menu_count'],
        'sold_out_count': z_report['sold_out_count'],
        'latest_session': _serialize_session(latest_session) if latest_session else None,
        'z_report': z_report,
    }
