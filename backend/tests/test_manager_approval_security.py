import json
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.cash import _correct_cash_audit_attribution
from app.db.database import Base
from app.models.entities import AuditLog, ManagerApproval, Permission, User, UserPermissionOverride
from app.schemas.common import RefundCreate
from app.services.approval_guard import consume_protected_approval, reject_legacy_client_approver
from app.services.approval_service import (
    approve_grant,
    authorize_approval_with_credentials,
    consume_approval_grant,
    request_approval,
)
from app.services.auth_service import hash_password


def make_session(url='sqlite:///:memory:'):
    engine = create_engine(url, future=True, connect_args={'check_same_thread': False} if url.startswith('sqlite') else {})
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def seed_users(db):
    manager = User(username='manager', full_name='Manager', hashed_password=hash_password('manager-secret'), role='manager', is_active=True)
    cashier = User(username='cashier', full_name='Cashier', hashed_password=hash_password('cashier-secret'), role='cashier', is_active=True)
    other = User(username='other-cashier', full_name='Other Cashier', hashed_password=hash_password('cashier-secret'), role='cashier', is_active=True)
    db.add_all([manager, cashier, other])
    db.commit()
    return manager, cashier, other


def approved_refund_grant(db, manager, cashier, *, order_id=10, amount=100):
    payload = {'refund_mode': 'amount', 'amount': amount, 'reason_code': 'guest_request'}
    grant = request_approval(
        db,
        approval_type='refund',
        entity_type='refund',
        entity_id=order_id,
        requested_by_user_id=cashier.id,
        requested_reason='Guest request',
        protected_payload=payload,
        commit=False,
    )
    approved = approve_grant(db, grant['id'], manager, commit=False)
    db.commit()
    return approved, payload


def test_client_cannot_submit_approved_by_user_id():
    payload = RefundCreate(refund_mode='amount', amount=100, approved_by_user_id=999)
    with pytest.raises(ValueError, match='Client-supplied approved_by_user_id'):
        reject_legacy_client_approver(payload)


def test_cashier_cannot_use_another_cashiers_grant():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, other = seed_users(db)
    grant, payload = approved_refund_grant(db, manager, cashier)
    with pytest.raises(ValueError, match='different requester'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=other.id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload=payload)


def test_refund_grant_cannot_authorize_another_amount_order_or_action():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, _ = seed_users(db)
    grant, payload = approved_refund_grant(db, manager, cashier, order_id=10, amount=100)
    with pytest.raises(ValueError, match='payload'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload={**payload, 'amount': 101})
    db.rollback()
    with pytest.raises(ValueError, match='different entity'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=11, protected_payload=payload)
    db.rollback()
    with pytest.raises(ValueError, match='different action'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='void', entity_type='refund', entity_id=10, protected_payload=payload)


def test_expired_grant_fails():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, _ = seed_users(db)
    grant, payload = approved_refund_grant(db, manager, cashier)
    row = db.query(ManagerApproval).filter(ManagerApproval.id == grant['id']).first()
    details = json.loads(row.request_details_json)
    details['_approval_grant']['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    row.request_details_json = json.dumps(details)
    db.commit()
    with pytest.raises(ValueError, match='expired'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload=payload)


def test_consumed_grant_cannot_be_replayed():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, _ = seed_users(db)
    grant, payload = approved_refund_grant(db, manager, cashier)
    first = consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload=payload)
    db.commit()
    assert first['status'] == 'consumed'
    with pytest.raises(ValueError, match='already been consumed'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload=payload)


def test_inactive_or_permission_revoked_approver_fails_at_consumption():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, _ = seed_users(db)
    grant, payload = approved_refund_grant(db, manager, cashier)
    manager.is_active = False
    db.commit()
    with pytest.raises(ValueError, match='inactive or no longer'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload=payload)

    manager.is_active = True
    db.commit()
    grant2, payload2 = approved_refund_grant(db, manager, cashier, order_id=12)
    permission = db.query(Permission).filter(Permission.key == 'approvals.manage').first()
    assert permission is not None
    db.add(UserPermissionOverride(user_id=manager.id, permission_id=permission.id, is_allowed=False))
    db.commit()
    with pytest.raises(ValueError, match='inactive or no longer'):
        consume_approval_grant(db, approval_uuid=grant2['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=12, protected_payload=payload2)


def test_authenticated_manager_credentials_create_bound_grant_without_exposing_manager_id_as_proof():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, _ = seed_users(db)
    grant = authorize_approval_with_credentials(
        db,
        requester=cashier,
        manager_username='manager',
        manager_password='manager-secret',
        approval_type='refund',
        entity_type='refund',
        entity_id=10,
        requested_reason='Guest request',
        protected_payload={'refund_mode': 'amount', 'amount': 100},
    )
    assert grant['status'] == 'approved'
    assert grant['requested_by_user_id'] == cashier.id
    assert grant['approved_by_user_id'] == manager.id
    assert grant['approval_uuid']
    assert len(grant['payload_digest']) == 64


def test_manager_self_action_is_separately_attributed():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, _, _ = seed_users(db)
    payload = RefundCreate(refund_mode='amount', amount=25, reason_code='other')
    with consume_protected_approval(db, requester=manager, payload=payload, approval_type='refund', entity_type='refund', entity_id=99, requested_reason='Manager self-action') as grant:
        assert grant['requested_by_user_id'] == manager.id
        assert grant['approved_by_user_id'] == manager.id
        assert grant['status'] == 'consumed'
    db.commit()


def test_cash_business_audit_preserves_requester_and_approver_separately():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, _ = seed_users(db)
    audit = AuditLog(actor_user_id=manager.id, actor_username=manager.username, action='cash_movement.created', entity_type='cash_movement', entity_id='77', details_json='{}')
    db.add(audit)
    db.commit()
    grant = {'approval_uuid': 'grant-1', 'approved_by_user_id': manager.id, 'payload_digest': 'a' * 64}
    _correct_cash_audit_attribution(db, 77, cashier, grant)
    db.refresh(audit)
    details = json.loads(audit.details_json)
    assert audit.actor_user_id == cashier.id
    assert details['requested_by_user_id'] == cashier.id
    assert details['approved_by_user_id'] == manager.id
    assert details['approval_grant_uuid'] == 'grant-1'


def test_grant_payload_cannot_be_mutated_after_approval():
    _, SessionLocal = make_session()
    db = SessionLocal()
    manager, cashier, _ = seed_users(db)
    grant, payload = approved_refund_grant(db, manager, cashier)
    row = db.query(ManagerApproval).filter(ManagerApproval.id == grant['id']).first()
    details = json.loads(row.request_details_json)
    details['protected_payload']['amount'] = 9999
    row.request_details_json = json.dumps(details)
    db.commit()
    with pytest.raises(ValueError, match='payload'):
        consume_approval_grant(db, approval_uuid=grant['approval_uuid'], requester_user_id=cashier.id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload={'refund_mode': 'amount', 'amount': 9999, 'reason_code': 'guest_request'})


def test_simultaneous_consumers_only_one_succeeds(tmp_path):
    db_path = tmp_path / 'approval-race.sqlite3'
    engine, SessionLocal = make_session(f'sqlite:///{db_path}')
    with SessionLocal() as db:
        manager, cashier, _ = seed_users(db)
        grant, payload = approved_refund_grant(db, manager, cashier)
        grant_uuid = grant['approval_uuid']
        cashier_id = cashier.id

    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def consume_once():
        session = SessionLocal()
        try:
            barrier.wait(timeout=5)
            consume_approval_grant(session, approval_uuid=grant_uuid, requester_user_id=cashier_id, approval_type='refund', entity_type='refund', entity_id=10, protected_payload=payload)
            session.commit()
            outcome = 'ok'
        except Exception as exc:
            session.rollback()
            outcome = str(exc)
        finally:
            session.close()
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=consume_once), threading.Thread(target=consume_once)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert outcomes.count('ok') == 1
    assert len(outcomes) == 2
    assert any('consumed' in outcome for outcome in outcomes if outcome != 'ok')
    engine.dispose()
