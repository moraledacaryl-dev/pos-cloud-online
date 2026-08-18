import inspect

from app import main
from app.api import audit
from app.db.database import engine
from app.services import audit_service


def test_request_middleware_does_not_write_generic_database_audits():
    source = inspect.getsource(main.request_context_middleware)
    assert 'write_audit_log' not in source
    assert "action='http.request'" not in source
    assert 'request.completed' in source


def test_audit_api_is_bounded_and_cursor_paginated():
    source = inspect.getsource(audit.audit_logs)
    assert 'default=50' in source
    assert 'le=100' in source
    assert 'before_id' in source
    assert audit_service.AUDIT_PAGE_SIZE_DEFAULT == 50
    assert audit_service.AUDIT_PAGE_SIZE_MAX == 100


def test_audit_service_returns_page_envelope():
    source = inspect.getsource(audit_service.list_audit_logs)
    assert "'items'" in source
    assert "'next_cursor'" in source
    assert 'page_size + 1' in source


def test_sqlite_foreign_keys_are_enabled_for_test_engine():
    if engine.dialect.name != 'sqlite':
        return
    with engine.connect() as connection:
        enabled = connection.exec_driver_sql('PRAGMA foreign_keys').scalar()
    assert enabled == 1
