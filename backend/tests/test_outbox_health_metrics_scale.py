"""Large disabled-Inventory queues stay bounded in health/readiness queries.

These tests use only disposable in-memory SQLite data. They do not run
sync workers, send financial events, or access production integrations.
"""

import json

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
from app.services import ops_service


@pytest.fixture
def queue_db():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, future=True)
    with factory() as db:
        yield db, engine
    engine.dispose()


def make_event(index, *, event_type='inventory.sale', status='blocked', retry=3, payload=None):
    return SyncOutboxEvent(
        event_uuid=f'ops-metrics-{index}',
        aggregate_type='order', aggregate_id=index,
        event_type=event_type,
        idempotency_key=f'ops-metrics:{index}',
        payload_json=payload if isinstance(payload, str) else json.dumps(
            payload if payload is not None else {},
        ),
        status=status, retry_count=retry,
    )


def test_high_volume_disabled_inventory_is_filtered_in_sql(queue_db, monkeypatch):
    db, engine = queue_db
    monkeypatch.setattr(ops_service.settings, 'inventory_integration_enabled', False)
    inventory = [
        make_event(i, status='blocked') for i in range(1, 1206)
    ] + [
        make_event(i, status='inventory_pending', retry=0) for i in range(1206, 1456)
    ]
    db.bulk_save_objects(inventory)
    db.add_all([
        make_event(
            1456, event_type='order.finalized', status='failed', retry=2,
            payload={'lines': [{'external_menu_item_id': 42}]},
        ),
        make_event(
            1457, event_type='order.finalized', status='failed', retry=2,
            payload={'lines': [{'external_menu_item_id': None}]},
        ),
        make_event(
            1458, event_type='order.voided', status='failed', retry=2,
            payload={'lines': 'malformed'},
        ),
        make_event(
            1459, event_type='order.finalized', status='pending', retry=0,
            payload={'lines': [{'external_menu_item_id': 42}]},
        ),
        make_event(1460, event_type='order.finalized', status='synced', retry=0),
    ])
    db.commit()

    bound_parameters = []

    def inspect_bindings(_conn, _cursor, statement, parameters, _context, _executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            bound_parameters.append(len(parameters))

    event.listen(engine, 'before_cursor_execute', inspect_bindings)
    try:
        metrics = ops_service.get_outbox_metrics(db)
    finally:
        event.remove(engine, 'before_cursor_execute', inspect_bindings)

    assert metrics['total'] == 1460
    assert metrics['suppressed'] == 1456
    assert metrics['status_counts']['blocked'] == 1205
    assert metrics['status_counts']['inventory_pending'] == 250
    assert metrics['inventory_blocked'] == 0
    assert metrics['inventory_pending'] == 0
    assert metrics['failed'] == 2
    assert metrics['pending'] == 1
    assert metrics['blocked'] == 0
    assert metrics['attention_required'] == 2
    assert metrics['due_now'] == 3
    assert metrics['retrying'] == 2
    assert metrics['max_retry_count'] == 2
    assert metrics['oldest_unresolved_event_id'] == 1456
    assert max(bound_parameters) < 100, (
        'health SQL must never bind a parameter for each suppressed Inventory event'
    )
    assert not db.dirty and not db.new and not db.deleted


def test_inventory_enabled_returns_underlying_inventory_alerts(queue_db, monkeypatch):
    db, _engine = queue_db
    monkeypatch.setattr(ops_service.settings, 'inventory_integration_enabled', True)
    db.add_all([
        make_event(1, status='inventory_pending', retry=0),
        make_event(2, status='inventory_retry', retry=3),
        make_event(3, status='blocked', retry=2),
        make_event(
            4, event_type='order.finalized', status='failed', retry=5,
            payload={'lines': [{'external_menu_item_id': None}]},
        ),
        make_event(
            5, event_type='order.finalized', status='failed', retry=1,
            payload={'lines': [{'external_menu_item_id': 5}]},
        ),
    ])
    db.commit()
    metrics = ops_service.get_outbox_metrics(db)
    assert metrics['total'] == 5
    assert metrics['suppressed'] == 1
    assert metrics['inventory_pending'] == 1
    assert metrics['inventory_retry'] == 1
    assert metrics['inventory_blocked'] == 1
    assert metrics['pending'] == 1
    assert metrics['failed'] == 2
    assert metrics['blocked'] == 1
    assert metrics['attention_required'] == 3
    assert metrics['retrying'] == 3
    assert metrics['max_retry_count'] == 3
    assert metrics['due_now'] == 3


def test_no_inventory_or_pos_local_suppression_does_not_change_health_contract(queue_db, monkeypatch):
    db, _engine = queue_db
    monkeypatch.setattr(ops_service.settings, 'inventory_integration_enabled', False)
    db.add_all([
        make_event(1, event_type='operations.order', status='operations_pending', retry=0),
        make_event(2, event_type='operations.order', status='operations_blocked', retry=2),
        make_event(
            3, event_type='order.finalized', status='failed', retry=1,
            payload={'lines': [{'external_menu_item_id': 7}]},
        ),
    ])
    db.commit()
    metrics = ops_service.get_outbox_metrics(db)
    assert metrics['suppressed'] == 0
    assert metrics['operations_pending'] == 1
    assert metrics['operations_blocked'] == 1
    assert metrics['pending'] == 1
    assert metrics['failed'] == 1
    assert metrics['blocked'] == 1
    assert metrics['due_now'] == 2
    assert metrics['retrying'] == 2
