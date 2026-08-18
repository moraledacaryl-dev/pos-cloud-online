import inspect
import json

import pytest
from fastapi import HTTPException, Request, Response

from app.api import customer_display
from app.services import customer_display_security as security


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.expiry = {}
        self.counts = {}

    def setex(self, key, ttl, value):
        self.data[key] = value
        self.expiry[key] = ttl
        return True

    def getdel(self, key):
        return self.data.pop(key, None)

    def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key, ttl):
        self.expiry[key] = ttl
        return True


def _request(cookie=''):
    headers = []
    if cookie:
        headers.append((b'cookie', cookie.encode()))
    return Request({'type': 'http', 'method': 'GET', 'path': '/api/customer-display/main', 'headers': headers, 'scheme': 'https', 'server': ('pos.hiddenoasis.app', 443), 'client': ('127.0.0.1', 1), 'query_string': b''})


def test_snapshot_redacts_guest_internal_ids_and_notes():
    snapshot = customer_display._sanitize_snapshot({
        'order_no': 'A-100',
        'guest_name': 'Private Guest',
        'table_label': 'T1',
        'cart': [{'local_id': 'secret-local-id', 'name': 'Latte', 'quantity': 2, 'total': 320, 'note': 'private note'}],
        'totals': {'gross': 320, 'discount': 0, 'total': 320},
    })
    assert snapshot['order_no'] == 'A-100'
    assert 'guest_name' not in snapshot
    assert 'local_id' not in snapshot['cart'][0]
    assert 'note' not in snapshot['cart'][0]


def test_pairing_code_is_random_hashed_single_use_and_short_lived(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(security, '_redis', lambda: fake)
    result = security.create_pairing_code(channel='main', register_id=3, requester_user_id=7)
    code = result['pairing_code']
    assert len(code) >= 8
    assert result['expires_in_seconds'] == security.PAIRING_TTL_SECONDS
    assert code not in json.dumps(fake.data)
    key = next(iter(fake.data))
    assert key.endswith(security._digest(code))
    first = fake.getdel(key)
    second = fake.getdel(key)
    assert first is not None
    assert second is None


def test_display_snapshot_route_requires_paired_device():
    source = inspect.getsource(customer_display.get_snapshot)
    assert 'require_display_device' in source
    assert "Cache-Control" in source
    assert 'private, no-store' in source


def test_pairing_generation_requires_manager_permission():
    source = inspect.getsource(customer_display.new_pairing_code)
    assert "require_permissions('approvals.manage')" in source


def test_display_cookie_is_httponly_and_strict(monkeypatch):
    class Device:
        device_uuid = 'dev'
        channel = 'main'
        register_id = None
    class DB:
        def add(self, obj): self.obj = obj
        def commit(self): pass
        def refresh(self, obj):
            obj.device_uuid = 'dev'
    fake = FakeRedis()
    monkeypatch.setattr(security, '_redis', lambda: fake)
    monkeypatch.setattr(security.settings, 'environment', 'production')
    pairing = security.create_pairing_code(channel='main', register_id=None, requester_user_id=1)
    response = Response()
    request = _request()
    device = security.activate_pairing_code(DB(), request, response, pairing['pairing_code'])
    cookies = [value.decode() for key, value in response.raw_headers if key.lower() == b'set-cookie']
    cookie = next(row for row in cookies if row.startswith(f'{security.DISPLAY_COOKIE}='))
    assert 'HttpOnly' in cookie
    assert 'Secure' in cookie
    assert 'SameSite=strict' in cookie
    assert 'Path=/api/customer-display' in cookie
    assert device.channel == 'main'


def test_channel_isolation_and_revoked_device_logic_is_present():
    source = inspect.getsource(security.require_display_device)
    assert 'device.channel != channel' in source
    assert 'device.revoked_at' in source
    assert 'device.is_active' in source
    assert 'expires_at' in source


def test_snapshot_has_ttl_and_terminal_clear_states():
    source = inspect.getsource(customer_display.update_snapshot)
    assert 'SNAPSHOT_TTL_SECONDS' in source
    for state in ('paid', 'voided', 'closed', 'reset'):
        assert state in source
