import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.customer_display import get_snapshot, update_snapshot
from app.db.database import Base
from app.models.entities import Outlet, Register, SyncOutboxEvent, User
from app.schemas.common import RegisterSessionClose, RegisterSessionOpen
from app.services.ops_service import _accounting_health_url, get_outbox_metrics
from app.services.pos_service import close_register_session, open_register_session, save_setting_json
from app.services.sync_service import run_outbox_sync


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_register(db, *, mapped=True):
    outlet = Outlet(code='RESTO', name='Restaurant', is_active=True)
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    register = Register(
        outlet_id=outlet.id,
        code='MAIN',
        name='Main Drawer',
        accounting_financial_account_id=1 if mapped else None,
        accounting_financial_account_code='CASH-RESTO' if mapped else 'DRW-CAFE',
        is_active=True,
    )
    db.add(register)
    db.commit()
    db.refresh(register)
    return register


def test_unmapped_register_cannot_open_or_close_a_shift():
    db = make_session()
    register = seed_register(db, mapped=False)
    with pytest.raises(ValueError, match='missing its Accounting drawer mapping'):
        open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-06-02'))

    register.accounting_financial_account_id = 1
    db.add(register)
    db.commit()
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-06-02'))
    register.accounting_financial_account_id = None
    db.add(register)
    db.commit()
    with pytest.raises(ValueError, match='missing its Accounting drawer mapping'):
        close_register_session(db, session['id'], RegisterSessionClose(closing_actual_cash=0))


def test_worker_skips_failed_event_until_retry_time_is_due():
    db = make_session()
    save_setting_json(db, 'accounting_sync', {'api_base': 'https://accounting.test/api'}, username='test')
    future_time = (datetime.utcnow() + timedelta(minutes=20)).replace(microsecond=0).isoformat()
    row = SyncOutboxEvent(
        event_uuid='event-1',
        aggregate_type='register_session',
        aggregate_id='1',
        event_type='session.closed',
        idempotency_key='session.closed:1',
        payload_json='{}',
        status='failed',
        retry_count=99,
        next_retry_at=future_time,
    )
    db.add(row)
    db.commit()

    result = asyncio.run(run_outbox_sync(db, limit=25))
    metrics = get_outbox_metrics(db)

    assert result['processed'] == 0
    assert metrics['failed'] == 1
    assert metrics['due_now'] == 0


def test_accounting_health_path_uses_origin_not_api_prefix():
    assert _accounting_health_url('https://hiddenoasis.app/api', '/healthz') == 'https://hiddenoasis.app/healthz'
    assert _accounting_health_url('https://hiddenoasis.app/api', 'healthz') == 'https://hiddenoasis.app/api/healthz'


def test_customer_display_snapshot_is_server_backed_and_sanitized():
    db = make_session()
    user = User(username='cashier', hashed_password='x', role='cashier', is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    result = update_snapshot('main', {
        'updated_at': '2026-06-02T10:00:00',
        'guest_name': 'Walk-in Guest',
        'table_label': 'L1',
        'cart': [{'local_id': 'line-1', 'name': 'Iced Coffee', 'quantity': '2', 'total': '240', 'note': 'Less ice'}],
        'totals': {'gross': '240', 'discount': 'bad', 'total': '240'},
    }, db=db, user=user)
    snapshot = get_snapshot('main', db=db)

    assert result['ok'] is True
    assert snapshot['cart'][0]['name'] == 'Iced Coffee'
    assert snapshot['cart'][0]['quantity'] == 2
    assert snapshot['totals']['discount'] == 0
    assert snapshot['totals']['total'] == 240
