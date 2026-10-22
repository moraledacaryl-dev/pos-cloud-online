"""Out-of-order Staff sync must not reactivate an employee identity.

Disposable SQLite fixture; no HR records or external systems are contacted.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.staff_identity import StaffIdentity
from app.schemas.staff_identity import StaffEmployeeSyncEnvelope
from app.services.staff_identity_service import sync_staff_employees


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine, future=True)()


def _envelope(event_id, timestamp, *, active, name="Cashier"):
    return StaffEmployeeSyncEnvelope.model_validate({
        "external_source": "hidden_oasis_staff_payroll",
        "external_id": event_id,
        "event_type": "employee.sync",
        "generated_at": timestamp,
        "payload": {"employees": [{
            "source_staff_id": 15,
            "employee_code": "EMP-015",
            "display_name": name,
            "active": active,
        }]},
    })


def test_delayed_staff_replay_cannot_reactivate_disabled_cashier():
    engine, db = _session()
    try:
        old = _envelope("staff-15-v1", "2026-10-21T10:00:00Z", active=True)
        new = _envelope("staff-15-v2", "2026-10-22T10:00:00Z", active=False)
        sync_staff_employees(db, old)
        applied = sync_staff_employees(db, new)
        replay = sync_staff_employees(db, old)

        assert applied["synced_count"] == 1
        assert replay["synced_count"] == 0
        assert replay["ignored_stale_count"] == 1
        row = db.query(StaffIdentity).one()
        assert row.is_active is False
        assert row.last_external_id == "staff-15-v2"
        assert row.last_synced_at_text == "2026-10-22T10:00:00Z"
    finally:
        db.close()
        engine.dispose()


def test_same_external_event_id_is_idempotent_even_with_conflicting_data():
    engine, db = _session()
    try:
        initial = _envelope("staff-15-deactivated", "2026-10-22T10:00:00", active=False)
        duplicate = _envelope(
            "staff-15-deactivated", "2026-10-22T10:00:00",
            active=True, name="Altered name",
        )
        sync_staff_employees(db, initial)
        result = sync_staff_employees(db, duplicate)

        assert result["ignored_stale_count"] == 1
        assert result["synced_count"] == 0
        row = db.query(StaffIdentity).one()
        assert row.is_active is False
        assert row.display_name == "Cashier"
        assert row.last_external_id == "staff-15-deactivated"
    finally:
        db.close()
        engine.dispose()


def test_staff_timestamp_comparison_normalizes_offsets():
    engine, db = _session()
    try:
        newest = _envelope("staff-new", "2026-10-22T02:00:00+00:00", active=False)
        stale = _envelope("staff-old", "2026-10-22T09:00:00+08:00", active=True)
        sync_staff_employees(db, newest)
        result = sync_staff_employees(db, stale)

        assert result["ignored_stale_count"] == 1
        row = db.query(StaffIdentity).one()
        assert row.is_active is False
        assert row.last_external_id == "staff-new"
    finally:
        db.close()
        engine.dispose()
