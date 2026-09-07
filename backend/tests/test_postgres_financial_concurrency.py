import os
import threading
import uuid

import pytest

if os.getenv('RUN_POSTGRES_INTEGRATION') != '1':
    pytest.skip('PostgreSQL integration test is enabled only in the production-equivalent CI job.', allow_module_level=True)

from app.db.database import SessionLocal, engine
from app.models.entities import CatalogItem, Outlet, Register, RegisterSession
from app.schemas.common import OrderCreate, OrderPayPayload
from app.services.pos_service import create_order, pay_order


def _run_concurrently(function):
    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def run():
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            outcome = function(db)
        except Exception as exc:
            db.rollback()
            outcome = f'error:{type(exc).__name__}:{exc}'
        finally:
            db.close()
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=run), threading.Thread(target=run)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert len(outcomes) == 2
    return outcomes


def test_postgres_allows_only_one_open_session_per_register():
    assert engine.dialect.name == 'postgresql'
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        outlet = Outlet(code=f'out-{suffix}', name=f'Outlet {suffix}', is_active=True)
        db.add(outlet)
        db.flush()
        register = Register(outlet_id=outlet.id, code=f'reg-{suffix}', name=f'Register {suffix}', is_active=True)
        db.add(register)
        db.commit()
        register_id = register.id

    def insert_open(db):
        db.add(RegisterSession(
            session_uuid=str(uuid.uuid4()),
            session_code=f'SES-{uuid.uuid4().hex[:12]}',
            register_id=register_id,
            business_date='2026-09-07',
            status='open',
        ))
        db.commit()
        return 'ok'

    outcomes = _run_concurrently(insert_open)
    assert outcomes.count('ok') == 1, outcomes
    assert sum('IntegrityError' in outcome for outcome in outcomes) == 1, outcomes


def test_postgres_row_lock_prevents_double_payment():
    assert engine.dialect.name == 'postgresql'
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        outlet = Outlet(code=f'pay-out-{suffix}', name=f'Pay Outlet {suffix}', is_active=True)
        db.add(outlet)
        db.flush()
        register = Register(
            outlet_id=outlet.id,
            code=f'pay-reg-{suffix}',
            name=f'Pay Register {suffix}',
            is_active=True,
            accounting_financial_account_id=1,
        )
        db.add(register)
        db.flush()
        session = RegisterSession(
            session_uuid=str(uuid.uuid4()),
            session_code=f'PAY-{suffix}',
            register_id=register.id,
            business_date='2026-09-07',
            status='open',
        )
        item = CatalogItem(
            menu_item_name=f'Concurrency Item {suffix}',
            display_name=f'Concurrency Item {suffix}',
            price='1.00',
            tax_rate='0',
            service_charge_rate='0',
            is_active=True,
            is_available=True,
        )
        db.add_all([session, item])
        db.commit()
        order = create_order(db, OrderCreate(
            register_session_id=session.id,
            lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 1, 'discount_amount': 0}],
        ))
        order_id = order['id']

    payload = OrderPayPayload(payments=[{
        'tender_type': 'cash',
        'amount_applied': 1,
        'amount_received': 1,
        'accounting_financial_account_id': 1,
    }])

    outcomes = _run_concurrently(lambda db: f"ok:{pay_order(db, order_id, payload)['status']}")
    assert outcomes.count('ok:paid') == 1, outcomes
    assert sum('cannot be paid' in outcome for outcome in outcomes) == 1, outcomes
