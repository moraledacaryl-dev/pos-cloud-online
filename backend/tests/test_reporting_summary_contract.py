"""Regression coverage for read-only dashboard/Z-report service extraction."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import (
    CashMovement,
    CatalogItem,
    Outlet,
    PosOrder,
    PosOrderPayment,
    Refund,
    Register,
    RegisterSession,
    SyncOutboxEvent,
)
from app.services import pos_service
from app.services.reporting_service import build_dashboard_summary

TODAY = '2026-10-22'


@pytest.fixture
def reporting_db():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, future=True)
    with factory() as db:
        outlet = Outlet(code='CAFE-TEST', name='Cafe', business_unit='F&B')
        db.add(outlet)
        db.flush()
        register = Register(outlet_id=outlet.id, code='DRAWER-TEST', name='Main cash')
        db.add(register)
        db.flush()
        session = RegisterSession(
            session_code='SHIFT-TEST', register_id=register.id,
            business_date=TODAY, status='open',
            opening_float=Decimal('100.00'), closing_expected_cash=Decimal('250.00'),
        )
        db.add(session)
        db.add_all([
            CatalogItem(menu_item_name='Coffee', display_name='Coffee',
                        price=Decimal('100'), is_active=True, is_available=True),
            CatalogItem(menu_item_name='Cookie', display_name='Cookie',
                        price=Decimal('25'), is_active=True, is_available=False),
            CatalogItem(menu_item_name='Retired', display_name='Retired',
                        price=Decimal('30'), is_active=False, is_available=False),
        ])
        db.flush()
        for number, status, price in [
            (1, 'paid', '200.00'),
            (2, 'folio_pending', '100.00'),
            (3, 'voided', '50.00'),
            (4, 'draft', '30.00'),
        ]:
            db.add(PosOrder(
                order_uuid=f'ord-report-{number}', order_no=f'ORD-REPORT-{number}',
                register_session_id=session.id, register_id=register.id,
                business_date=TODAY, order_type='takeout' if number == 2 else 'dine_in',
                status=status, total_amount=Decimal(price),
            ))
        db.flush()
        paid = db.query(PosOrder).filter(PosOrder.order_no == 'ORD-REPORT-1').one()
        folio = db.query(PosOrder).filter(PosOrder.order_no == 'ORD-REPORT-2').one()
        db.add_all([
            PosOrderPayment(order_id=paid.id, tender_type='cash', amount_applied=Decimal('150.00')),
            PosOrderPayment(order_id=paid.id, tender_type='gcash', amount_applied=Decimal('50.00')),
            PosOrderPayment(order_id=folio.id, tender_type='room_charge', amount_applied=Decimal('100.00')),
            Refund(refund_uuid='refund-report', refund_no='R-REPORT', order_id=paid.id,
                   register_session_id=session.id, register_id=register.id,
                   refunded_amount=Decimal('50.00')),
            CashMovement(cash_event_uuid='cash-report-1', register_session_id=session.id,
                         register_id=register.id, event_date=TODAY, direction='in',
                         movement_type='cash_sale', amount=Decimal('150.00')),
            CashMovement(cash_event_uuid='cash-report-2', register_session_id=session.id,
                         register_id=register.id, event_date=TODAY, direction='out',
                         movement_type='refund', amount=Decimal('50.00')),
            SyncOutboxEvent(
                event_uuid='outbox-local', aggregate_type='order', aggregate_id=paid.id,
                event_type='order.finalized', idempotency_key='report-local',
                payload_json='{"lines":[{"external_menu_item_id":null}]}', status='blocked',
            ),
            SyncOutboxEvent(
                event_uuid='outbox-real', aggregate_type='order', aggregate_id=paid.id,
                event_type='order.finalized', idempotency_key='report-real',
                payload_json='{"lines":[{"external_menu_item_id":123}]}', status='failed',
            ),
            SyncOutboxEvent(
                event_uuid='outbox-inventory', aggregate_type='order', aggregate_id=paid.id,
                event_type='inventory.sale', idempotency_key='report-inventory',
                payload_json='{}', status='blocked',
            ),
        ])
        db.commit()
        yield db
    engine.dispose()


def report(db, *, enabled: bool):
    return build_dashboard_summary(
        db, today=TODAY, inventory_integration_enabled=enabled,
        suppression_reason=pos_service.outbox_suppression_reason,
        serialize_session=lambda row: {'session_code': row.session_code},
    )


@pytest.mark.parametrize(('inventory_enabled', 'expected_pending'), [(False, 1), (True, 2)])
def test_dashboard_aggregates_tenders_cash_refunds_and_suppressed_outbox(
    reporting_db, inventory_enabled, expected_pending
):
    db = reporting_db
    result = report(db, enabled=inventory_enabled)
    z = result['z_report']
    assert result['open_sessions'] == 1
    assert result['pending_sync'] == expected_pending
    assert result['sales_today'] == 300
    assert result['cash_today'] == 150
    assert result['orders_open'] == 1
    assert result['catalog_count'] == 1
    assert result['sold_out_count'] == 1
    assert result['latest_session'] == {'session_code': 'SHIFT-TEST'}
    assert z['business_date'] == TODAY
    assert z['gross_sales'] == 300
    assert z['refund_total'] == 50
    assert z['net_sales'] == 250
    assert z['order_count'] == 2
    assert z['voided_count'] == 1
    assert z['open_orders'] == 1
    assert z['active_menu_count'] == 1
    assert z['sold_out_count'] == 1
    assert {row['tender_type']: row['amount'] for row in z['tenders']} == {
        'cash': 150, 'gcash': 50, 'room_charge': 100,
    }
    assert {row['order_type']: row['amount'] for row in z['order_types']} == {
        'dine_in': 200, 'takeout': 100,
    }
    assert z['open_sessions'][0]['expected_cash'] == 250
    assert {row['movement_type']: row['amount'] for row in z['cash_movements']} == {
        'cash_sale': 150, 'refund': 50,
    }
    assert not db.dirty and not db.new and not db.deleted


def test_public_pos_service_wrapper_preserves_existing_contract(reporting_db, monkeypatch):
    monkeypatch.setattr(pos_service, 'today_iso', lambda: TODAY)
    monkeypatch.setattr(pos_service.settings, 'inventory_integration_enabled', False)
    monkeypatch.setattr(
        pos_service, '_serialize_session',
        lambda row: {'session_code': row.session_code},
    )
    assert pos_service.dashboard_summary(reporting_db) == report(reporting_db, enabled=False)


def test_past_business_dates_and_discarded_orders_do_not_pollute_today(reporting_db):
    result = build_dashboard_summary(
        reporting_db,
        today='2026-10-23',
        inventory_integration_enabled=False,
        suppression_reason=pos_service.outbox_suppression_reason,
        serialize_session=lambda row: {'session_code': row.session_code},
    )
    assert result['sales_today'] == 0
    assert result['cash_today'] == 0
    assert result['z_report']['order_count'] == 0
    assert result['z_report']['refund_total'] == 0
    assert result['open_sessions'] == 1
