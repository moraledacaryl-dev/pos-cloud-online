"""Read-only POS dashboard and shift Z-report aggregation.

This service has no payment, settlement, outbox-write or transaction mutation
paths. Inject legacy policies and serializer explicitly to avoid service cycles.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.entities import (
    CashMovement,
    CatalogItem,
    PosOrder,
    PosOrderPayment,
    Refund,
    RegisterSession,
    SyncOutboxEvent,
)


def build_dashboard_summary(
    db: Session, *, today: str, inventory_integration_enabled: bool,
    suppression_reason, serialize_session,
):
    open_sessions = db.query(RegisterSession).filter(RegisterSession.status == 'open').count()
    pending_query = db.query(SyncOutboxEvent).filter(
        SyncOutboxEvent.status.in_([
            'pending', 'failed', 'blocked', 'operations_pending', 'operations_retry', 'operations_blocked'
        ])
    )
    if not inventory_integration_enabled:
        pending_query = pending_query.filter(~SyncOutboxEvent.event_type.like('inventory.%'))
    # Dashboard must use the same effective suppression policy as the recovery
    # queue.  Historical local-only events can remain physically "blocked" in
    # the database while being intentionally suppressed at serialization time;
    # counting their raw status creates a false operator warning.
    pending_sync = sum(
        1
        for event in pending_query.all()
        if not suppression_reason(event.event_type, event.payload_json)
    )
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
        'latest_session': serialize_session(latest_session) if latest_session else None,
        'z_report': z_report,
    }
