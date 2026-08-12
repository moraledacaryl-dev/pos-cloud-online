from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from hmac import compare_digest

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.settings import looks_like_placeholder_secret, settings
from app.db.database import get_db
from app.models.entities import CashMovement, PosOrder, PosOrderPayment, Refund, RegisterSession, RoomChargePosting

router = APIRouter()


def _money(value) -> float:
    return round(float(value or 0), 2)


def _hour(value) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return f'{value.hour:02d}:00'
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return f'{parsed.hour:02d}:00'
    except ValueError:
        return None


def require_integration_key(x_integration_api_key: str | None = Header(default=None, alias='X-Integration-Api-Key')):
    secret = (settings.integration_api_key or '').strip()
    if looks_like_placeholder_secret(secret):
        if settings.is_production:
            raise HTTPException(status_code=503, detail='Integration API key is not configured')
        return
    if not x_integration_api_key or not compare_digest(str(x_integration_api_key), secret):
        raise HTTPException(status_code=401, detail='Invalid integration API key')


def build_daily_ops_context(db: Session, business_date: str) -> dict:
    orders = db.query(PosOrder).filter(PosOrder.business_date == business_date).all()
    order_ids = [order.id for order in orders]
    sessions = db.query(RegisterSession).filter(RegisterSession.business_date == business_date).all()

    payments = []
    refunds = []
    if order_ids:
        payments = db.query(PosOrderPayment).filter(PosOrderPayment.order_id.in_(order_ids)).all()
        refunds = db.query(Refund).filter(Refund.order_id.in_(order_ids)).all()

    tender_totals = defaultdict(float)
    for payment in payments:
        key = (payment.tender_type or 'unknown').lower().replace(' ', '_')
        tender_totals[key] += _money(payment.amount_applied)

    refund_total = _money(sum(_money(refund.refunded_amount) for refund in refunds))
    voids = [order for order in orders if (order.status or '').lower() in {'void', 'voided', 'cancelled'}]
    open_orders = [order for order in orders if (order.status or '').lower() in {'draft', 'open', 'in_progress'}]
    held_orders = [order for order in orders if (order.status or '').lower() in {'held', 'hold'}]
    unpaid_orders = [order for order in orders if _money(order.balance_due) > 0 and (order.status or '').lower() not in {'void', 'voided', 'cancelled'}]

    room_charges = db.query(RoomChargePosting).filter(RoomChargePosting.service_date == business_date).all()
    pending_room_charges = [row for row in room_charges if row.posting_status == 'pending_frontdesk_post']

    cash_movements = db.query(CashMovement).filter(CashMovement.event_date == business_date).all()
    bank_transfer_total = _money(sum(_money(row.amount) for row in cash_movements if (row.movement_type or '').lower() in {'bank_transfer', 'cash_transfer'}))

    hour_counts = Counter(filter(None, (_hour(order.created_at) for order in orders)))
    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else None
    warnings = []
    drawer_variance = _money(sum(_money(session.variance_amount) for session in sessions))
    if abs(drawer_variance) > 0:
        warnings.append({'type': 'drawer_variance.alert', 'amount': drawer_variance})
    if unpaid_orders:
        warnings.append({'type': 'unpaid_orders.warning', 'count': len(unpaid_orders)})
    if pending_room_charges:
        warnings.append({'type': 'room_charge.pending_frontdesk_post', 'count': len(pending_room_charges)})

    first_order = min((order.created_at for order in orders if order.created_at), default=None)
    last_order = max((order.created_at for order in orders if order.created_at), default=None)
    gross_sales = _money(sum(_money(order.total_amount) for order in orders))
    net_sales = _money(sum(_money(order.total_amount) for order in orders if order not in voids) - refund_total)
    room_charge_total = _money(sum(_money(row.charge_amount) for row in room_charges))
    card_sales = _money(tender_totals.get('card', 0) + tender_totals.get('credit_card', 0) + tender_totals.get('debit_card', 0))
    generated_at = datetime.utcnow().replace(microsecond=0).isoformat()

    context = {
        'event_type': 'daily_sales_context',
        'external_source': 'dedicated_pos_cloud',
        'business_date': business_date,
        'generated_at': generated_at,
        'gross_sales': gross_sales,
        'net_sales': net_sales,
        'order_count': len(orders),
        'refund_count': len(refunds),
        'void_count': len(voids),
        'cash_sales': _money(tender_totals.get('cash')),
        'gcash_sales': _money(tender_totals.get('gcash')),
        'card_sales': card_sales,
        'bank_transfer_sales': bank_transfer_total,
        'room_charge_total': room_charge_total,
        'open_order_count': len(open_orders),
        'held_order_count': len(held_orders),
        'unpaid_order_count': len(unpaid_orders),
        'pending_room_charge_count': len(pending_room_charges),
        'drawer_variance_total': drawer_variance,
        'active_session_count': len([session for session in sessions if session.status == 'open']),
        'first_order_time': first_order.isoformat() if first_order else None,
        'last_order_time': last_order.isoformat() if last_order else None,
        'totals': {
            'sales': net_sales,
            'orders': len(orders),
            'refunds': refund_total,
            'voids': len(voids),
            'cash': _money(tender_totals.get('cash')),
            'gcash': _money(tender_totals.get('gcash')),
            'card': card_sales,
            'bank_transfers': bank_transfer_total,
            'room_charges': room_charge_total,
        },
        'counts': {
            'open_orders': len(open_orders),
            'held_orders': len(held_orders),
            'unpaid_orders': len(unpaid_orders),
            'pending_room_charges': len(pending_room_charges),
            'active_sessions': len([session for session in sessions if session.status == 'open']),
        },
        'drawer_variance': drawer_variance,
        'first_order_at': first_order.isoformat() if first_order else None,
        'last_order_at': last_order.isoformat() if last_order else None,
        'peak_hour': peak_hour,
        'warnings': warnings,
        'privacy_note': 'Operational totals only. No payroll, HR data, guest names, or customer PII are returned.',
    }
    context['integration_event'] = {
        'external_source': 'dedicated_pos_cloud',
        'external_id': f'daily-sales-context:{business_date}',
        'event_type': 'daily_sales_context',
        'source_record_type': 'POS Daily Operations Context',
        'source_record_id': business_date,
        'generated_at': generated_at,
        'schema_version': '2026-06-v1',
        'status': 'For Review',
        'payload': {
            key: value for key, value in context.items()
            if key not in {'integration_event'}
        },
    }
    return context


@router.get('/daily-ops-context')
async def daily_ops_context(
    date: str = Query(..., pattern=r'^\d{4}-\d{2}-\d{2}$'),
    db: Session = Depends(get_db),
    _=Depends(require_integration_key),
):
    return build_daily_ops_context(db, date)
