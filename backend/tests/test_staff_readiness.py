import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.customer_display import _stored_snapshot, update_snapshot
from app.core.settings import DEFAULT_ACCOUNTING_API_BASE, Settings, looks_like_placeholder_secret
from app.db.database import Base
from app.models.entities import Outlet, Register, SyncOutboxEvent, SystemSetting, User
from app.schemas.common import RegisterSessionClose, RegisterSessionOpen
from app.services.ops_service import _accounting_health_url, get_outbox_metrics, get_security_readiness
from app.services.pos_service import (
    close_register_session,
    ensure_default_outlet_registers,
    open_register_session,
    repair_accounting_sync_api_base,
    save_setting_json,
    setting_json,
)
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


class FakeResponse:
    status_code = 200
    text = '[]'

    def __init__(self, payload=None):
        self._payload = payload if payload is not None else []

    def json(self):
        return self._payload


class CaptureAsyncClient:
    posts = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        return FakeResponse([])

    async def post(self, url, json=None):
        self.__class__.posts.append((url, json))
        return FakeResponse({'ok': True})


def test_accounting_api_base_default_is_accounting_subdomain(monkeypatch):
    monkeypatch.delenv('ACCOUNTING_API_BASE', raising=False)
    assert DEFAULT_ACCOUNTING_API_BASE == 'https://accounting.hiddenoasis.app/api'
    assert Settings(_env_file=None).accounting_api_base == 'https://accounting.hiddenoasis.app/api'
    assert Settings(_env_file=None).accounting_api_base != 'https://hiddenoasis.app/api'


def test_accounting_api_base_env_override(monkeypatch):
    monkeypatch.setenv('ACCOUNTING_API_BASE', 'https://accounting.example.test/api')
    assert Settings(_env_file=None).accounting_api_base == 'https://accounting.example.test/api'


def test_accounting_sync_startup_repair_updates_legacy_root_url():
    db = make_session()
    save_setting_json(db, 'accounting_sync', {'api_base': 'https://hiddenoasis.app/api', 'sync_orders': True}, username='test')

    changed = repair_accounting_sync_api_base(db)

    assert changed is True
    cfg = setting_json(db, 'accounting_sync')
    assert cfg['api_base'] == 'https://accounting.hiddenoasis.app/api'
    assert 'https://hiddenoasis.app/api' not in db.query(SystemSetting).filter(SystemSetting.key == 'accounting_sync').one().value_json


def test_accounting_sync_startup_repair_is_idempotent():
    db = make_session()
    save_setting_json(db, 'accounting_sync', {'api_base': 'https://hiddenoasis.app/api'}, username='test')

    assert repair_accounting_sync_api_base(db) is True
    first = db.query(SystemSetting).filter(SystemSetting.key == 'accounting_sync').one().value_json
    assert repair_accounting_sync_api_base(db) is False
    second = db.query(SystemSetting).filter(SystemSetting.key == 'accounting_sync').one().value_json

    assert second == first


def test_accounting_sync_startup_repair_handles_text_value_json():
    db = make_session()
    row = SystemSetting(key='accounting_sync', value_json='api_base=https://hiddenoasis.app/api', updated_by='test')
    db.add(row)
    db.commit()

    assert repair_accounting_sync_api_base(db) is True
    repaired = db.query(SystemSetting).filter(SystemSetting.key == 'accounting_sync').one().value_json
    assert repaired == 'api_base=https://accounting.hiddenoasis.app/api'


def test_default_seed_uses_accounting_subdomain_and_repairs_existing_legacy_sync(monkeypatch):
    monkeypatch.delenv('ACCOUNTING_API_BASE', raising=False)
    db = make_session()
    ensure_default_outlet_registers(db)
    assert setting_json(db, 'accounting_sync')['api_base'] == 'https://accounting.hiddenoasis.app/api'

    save_setting_json(db, 'accounting_sync', {'api_base': 'https://hiddenoasis.app/api'}, username='test')
    ensure_default_outlet_registers(db)
    assert setting_json(db, 'accounting_sync')['api_base'] == 'https://accounting.hiddenoasis.app/api'


def test_sync_worker_uses_configured_accounting_api_base(monkeypatch):
    db = make_session()
    save_setting_json(db, 'accounting_sync', {'api_base': 'https://accounting.configured.test/api', 'sync_cash_movements': True}, username='test')
    event = SyncOutboxEvent(
        event_uuid='event-configured-base',
        aggregate_type='cash_movement',
        aggregate_id='999',
        event_type='cash_movement.created',
        idempotency_key='cash_movement.created:999',
        payload_json='{"event_date":"2026-06-09","direction":"in","amount":125,"reference_no":"CM-999","cash_event_uuid":"cm-999","accounting_financial_account_id":1,"id":999}',
        status='pending',
    )
    db.add(event)
    db.commit()
    CaptureAsyncClient.posts = []
    monkeypatch.setattr('app.services.sync_service.httpx.AsyncClient', CaptureAsyncClient)

    result = asyncio.run(run_outbox_sync(db, limit=10))

    assert result['synced'] == 1
    assert CaptureAsyncClient.posts
    assert CaptureAsyncClient.posts[0][0] == 'https://accounting.configured.test/api/cashflow/transactions'


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
    future_time = (datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=20)).replace(microsecond=0).isoformat()
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
    assert _accounting_health_url('https://accounting.hiddenoasis.app/api', '/healthz') == 'https://accounting.hiddenoasis.app/healthz'
    assert _accounting_health_url('https://accounting.hiddenoasis.app/api', 'healthz') == 'https://accounting.hiddenoasis.app/api/healthz'


def test_placeholder_secrets_are_reported_for_deployment_readiness():
    assert looks_like_placeholder_secret('change-me-super-secret')
    assert looks_like_placeholder_secret('')
    assert not looks_like_placeholder_secret('hidden-oasis-pos-2026-strong-token')

    readiness = get_security_readiness()
    assert readiness['ok'] is False
    assert any('SECRET_KEY' in warning for warning in readiness['warnings'])


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
    snapshot = _stored_snapshot(db, 'main')

    assert result['ok'] is True
    assert snapshot['cart'][0]['name'] == 'Iced Coffee'
    assert snapshot['cart'][0]['quantity'] == 2
    assert snapshot['totals']['discount'] == 0
    assert snapshot['totals']['total'] == 240
    assert 'guest_name' not in snapshot
    assert 'local_id' not in snapshot['cart'][0]
    assert 'note' not in snapshot['cart'][0]
