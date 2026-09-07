import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
from app.services import sync_service


def make_session():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def event(*, event_uuid: str, event_type: str, status: str) -> SyncOutboxEvent:
    return SyncOutboxEvent(
        event_uuid=event_uuid,
        aggregate_type='order',
        aggregate_id=1,
        event_type=event_type,
        idempotency_key=f'test:{event_uuid}',
        payload_json='{}',
        status=status,
    )


def test_manual_inventory_retry_routes_to_inventory_worker(monkeypatch):
    db = make_session()
    row = event(event_uuid='inventory-retry', event_type='inventory.sale_completed', status='inventory_retry')
    db.add(row)
    db.commit()
    captured = {}

    async def fake_inventory_runner(_db, limit, *, event_id=None):
        captured.update({'limit': limit, 'event_id': event_id})
        return {'ok': True, 'processed': 1, 'synced': 1, 'failed': 0, 'blocked': 0}

    monkeypatch.setattr(sync_service, 'run_inventory_outbox_sync', fake_inventory_runner)
    result = asyncio.run(sync_service.retry_outbox_event(db, row.id))
    db.refresh(row)

    assert result['synced'] == 1
    assert captured == {'limit': 1, 'event_id': row.id}
    assert row.status == 'inventory_pending'


def test_unblock_preserves_operations_queue_routing():
    db = make_session()
    row = event(event_uuid='operations-blocked', event_type='operations.v2.order.finalized', status='operations_blocked')
    db.add(row)
    db.commit()

    result = asyncio.run(sync_service.unblock_outbox_event(db, row.id))

    assert result['status'] == 'operations_pending'
