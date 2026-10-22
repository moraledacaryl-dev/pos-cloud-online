"""Group 19: PostgreSQL register locking across reopen paths.

This runs only in the isolated production-equivalent PostgreSQL CI job.
No staging or production credentials are used.
"""

import os
import threading
import time
import uuid

import pytest

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("PostgreSQL concurrency coverage runs only in isolated integration CI.", allow_module_level=True)

import app.services.pos_service as pos_service
from app.db.database import SessionLocal, engine
from app.models.entities import Outlet, Register, RegisterSession
from app.schemas.common import RegisterSessionReopen
from app.services.pos_service import reopen_register_session


def test_two_concurrent_reopens_choose_one_open_session(monkeypatch):
    """A second cashier gets a domain error rather than a unique-index failure."""
    assert engine.dialect.name == "postgresql"
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        outlet = Outlet(code=f"reo-out-{suffix}", name=f"Reopen Outlet {suffix}", is_active=True)
        db.add(outlet)
        db.flush()
        register = Register(
            outlet_id=outlet.id, code=f"reo-reg-{suffix}",
            name=f"Reopen Register {suffix}", is_active=True,
            accounting_financial_account_id=1,
        )
        db.add(register)
        db.flush()
        closed_sessions = [
            RegisterSession(
                session_code=f"REO-{index}-{suffix}", register_id=register.id,
                business_date="2026-09-07", status="closed",
                closed_at_text="2026-09-07T12:00:00Z",
            )
            for index in (1, 2)
        ]
        db.add_all(closed_sessions)
        db.commit()
        session_ids = [row.id for row in closed_sessions]
        register_id = register.id

    # Approval permissions are exercised in their own tests. This fixture
    # deliberately makes the post-check window long enough to expose the race
    # that existed when only the individual RegisterSession row was locked.
    def approved_grant(*args, **kwargs):
        time.sleep(0.25)
        return {"id": 1}

    monkeypatch.setattr(pos_service, "_record_approval", approved_grant)
    barrier = threading.Barrier(2)
    results = []
    mutex = threading.Lock()

    def reopen_worker(session_id):
        db = SessionLocal()
        try:
            barrier.wait(timeout=10)
            reopen_register_session(
                db, session_id, RegisterSessionReopen(reason="Authorized shift correction"),
            )
            result = "opened"
        except Exception as exc:
            db.rollback()
            result = f"{type(exc).__name__}: {exc}"
        finally:
            db.close()
        with mutex:
            results.append(result)

    threads = [threading.Thread(target=reopen_worker, args=(id_,)) for id_ in session_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert len(results) == 2, results
    assert results.count("opened") == 1, results
    assert sum("ValueError: Another session is already open" in x for x in results) == 1, results
    assert not any("IntegrityError" in x for x in results), results

    with SessionLocal() as db:
        open_sessions = db.query(RegisterSession).filter(
            RegisterSession.register_id == register_id,
            RegisterSession.status == "open",
        ).all()
        assert len(open_sessions) == 1
