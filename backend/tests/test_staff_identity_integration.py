from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from pydantic import ValidationError
from fastapi import HTTPException
import pytest

from app.api.staff_integrations import require_staff_integration_key, router as staff_integrations_router
from app.core.settings import settings
from app.db.database import Base
from app.models.entities import User
from app.models.staff_identity import PosUserStaffLink, StaffIdentity
from app.schemas.staff_identity import StaffEmployeeSyncEnvelope
from app.services.auth_service import hash_password
from app.services.staff_identity_service import set_user_staff_link, sync_staff_employees


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def envelope(*, external_id='employee-sync:1:v1', source_staff_id=1, employee_code='EMP-001', display_name='Cashier One', active=True, department='F&B'):
    return StaffEmployeeSyncEnvelope.model_validate({
        'external_source': 'hidden_oasis_staff_payroll',
        'external_id': external_id,
        'event_type': 'employee.sync',
        'source_record_type': 'Employee',
        'source_record_id': source_staff_id,
        'generated_at': '2026-08-12T08:00:00',
        'schema_version': '2026-06-v1',
        'payload': {
            'employees': [{
                'employee_code': employee_code,
                'display_name': display_name,
                'department': department,
                'position': 'Cashier',
                'role': 'regular',
                'active': active,
                'primary_department': department,
                'source_staff_id': source_staff_id,
            }]
        },
    })


def test_employee_sync_is_idempotent_and_updates_safe_identity_fields():
    db = make_session()
    first = sync_staff_employees(db, envelope())
    second = sync_staff_employees(db, envelope(external_id='employee-sync:1:v2', display_name='Cashier One Updated', active=False))

    assert first['synced_count'] == 1
    assert second['synced_count'] == 1
    rows = db.query(StaffIdentity).all()
    assert len(rows) == 1
    assert rows[0].source_staff_id == 1
    assert rows[0].employee_code == 'EMP-001'
    assert rows[0].display_name == 'Cashier One Updated'
    assert rows[0].is_active is False
    assert rows[0].last_external_id == 'employee-sync:1:v2'


def test_employee_code_collision_is_rejected():
    db = make_session()
    sync_staff_employees(db, envelope(source_staff_id=1, employee_code='EMP-001'))
    with pytest.raises(ValueError, match='conflicts|already assigned'):
        sync_staff_employees(db, envelope(external_id='employee-sync:2:v1', source_staff_id=2, employee_code='EMP-001'))


def test_private_hr_fields_are_rejected_at_integration_boundary():
    payload = envelope().model_dump()
    payload['payload']['employees'][0]['salary'] = 25000
    with pytest.raises(ValidationError):
        StaffEmployeeSyncEnvelope.model_validate(payload)


def test_pos_user_link_is_explicit_one_to_one_and_unlinkable():
    db = make_session()
    sync_staff_employees(db, envelope())
    identity = db.query(StaffIdentity).one()
    first_user = User(username='cashier1', full_name='Cashier One', hashed_password=hash_password('secret123'), role='cashier', is_active=True)
    second_user = User(username='cashier2', full_name='Cashier Two', hashed_password=hash_password('secret123'), role='cashier', is_active=True)
    db.add_all([first_user, second_user])
    db.commit()
    db.refresh(first_user)
    db.refresh(second_user)

    linked = set_user_staff_link(db, first_user.id, identity.id)
    assert linked['staff_identity']['employee_code'] == 'EMP-001'
    assert db.query(PosUserStaffLink).count() == 1

    with pytest.raises(ValueError, match='already linked'):
        set_user_staff_link(db, second_user.id, identity.id)

    unlinked = set_user_staff_link(db, first_user.id, None)
    assert unlinked['staff_identity_id'] is None
    assert db.query(PosUserStaffLink).count() == 0


def test_only_staff_payroll_employee_sync_contract_is_accepted():
    db = make_session()
    wrong_source = envelope().model_copy(update={'external_source': 'other_hr_system'})
    with pytest.raises(ValueError, match='Unsupported Staff identity source'):
        sync_staff_employees(db, wrong_source)
    wrong_event = envelope().model_copy(update={'event_type': 'employee.salary_changed'})
    with pytest.raises(ValueError, match='Unsupported Staff integration event type'):
        sync_staff_employees(db, wrong_event)


def test_staff_receiver_route_matches_staff_payroll_contract():
    assert any(route.path == '/employees' and 'POST' in route.methods for route in staff_integrations_router.routes)


def test_staff_receiver_auth_is_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, 'staff_integration_enabled', False)
    with pytest.raises(HTTPException) as disabled:
        require_staff_integration_key('strong-shared-staff-pos-secret')
    assert disabled.value.status_code == 503

    monkeypatch.setattr(settings, 'staff_integration_enabled', True)
    monkeypatch.setattr(settings, 'staff_integration_key', 'strong-shared-staff-pos-secret')
    with pytest.raises(HTTPException) as invalid:
        require_staff_integration_key('wrong-secret-value')
    assert invalid.value.status_code == 401
    assert require_staff_integration_key('strong-shared-staff-pos-secret') is None
