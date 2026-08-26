import os
import threading
import uuid

import pytest

if os.getenv('RUN_POSTGRES_INTEGRATION') != '1':
    pytest.skip('PostgreSQL integration test is enabled only in the production-equivalent CI job.', allow_module_level=True)

from app.db.database import SessionLocal, engine
from app.models.entities import User
from app.services.approval_service import approve_grant, consume_approval_grant, request_approval
from app.services.auth_service import hash_password
from app.services.permission_service import assign_user_roles, ensure_permissions_seed, list_roles


def test_postgres_row_lock_allows_exactly_one_approval_grant_consumer():
    assert engine.dialect.name == 'postgresql'
    suffix = uuid.uuid4().hex[:10]
    payload = {'refund_mode': 'amount', 'amount': 125.50, 'reason_code': 'guest_request'}

    with SessionLocal() as db:
        ensure_permissions_seed(db)
        manager = User(
            username=f'ci-manager-{suffix}',
            full_name='CI Manager',
            hashed_password=hash_password('ManagerPassword-2026!'),
            role='manager',
            is_active=True,
            session_version=1,
        )
        cashier = User(
            username=f'ci-cashier-{suffix}',
            full_name='CI Cashier',
            hashed_password=hash_password('CashierPassword-2026!'),
            role='cashier',
            is_active=True,
            session_version=1,
        )
        db.add_all([manager, cashier])
        db.commit()
        db.refresh(manager)
        db.refresh(cashier)
        roles = list_roles(db)
        manager_role = next(row for row in roles if row.get('code') == 'manager')
        assign_user_roles(db, manager.id, [int(manager_role['id'])])
        db.refresh(manager)

        grant = request_approval(
            db,
            approval_type='refund',
            entity_type='refund',
            entity_id=7788,
            requested_by_user_id=cashier.id,
            requested_reason='PostgreSQL race regression',
            protected_payload=payload,
            commit=False,
        )
        approved = approve_grant(db, grant['id'], manager, commit=False)
        db.commit()
        approval_uuid = approved['approval_uuid']
        cashier_id = cashier.id

    barrier = threading.Barrier(2)
    outcomes = []
    outcome_lock = threading.Lock()

    def consume_once():
        session = SessionLocal()
        try:
            barrier.wait(timeout=10)
            result = consume_approval_grant(
                session,
                approval_uuid=approval_uuid,
                requester_user_id=cashier_id,
                approval_type='refund',
                entity_type='refund',
                entity_id=7788,
                protected_payload=payload,
            )
            session.commit()
            outcome = f"ok:{result['status']}"
        except Exception as exc:
            session.rollback()
            outcome = f'error:{exc}'
        finally:
            session.close()
        with outcome_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=consume_once), threading.Thread(target=consume_once)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert len(outcomes) == 2
    assert sum(outcome.startswith('ok:consumed') for outcome in outcomes) == 1, outcomes
    assert sum('consum' in outcome.lower() for outcome in outcomes if outcome.startswith('error:')) == 1, outcomes
