import asyncio
from types import SimpleNamespace

from app.services.accounting_review_defaults import install_accounting_review_transport, review_aware_order_void_push


class DummyResponse:
    status_code = 200


class DummyClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, json):
        self.calls.append((url, json))
        return DummyResponse()


def test_review_aware_void_posts_directly_to_accounting_review_route():
    legacy_calls = []

    async def legacy(client, base, config, payload):
        legacy_calls.append(payload)
        return DummyResponse()

    push = review_aware_order_void_push(legacy)
    client = DummyClient()
    result = asyncio.run(push(
        client,
        'https://accounting.hiddenoasis.app/api',
        {'current_erp_sales_void_path': '/integrations/pos-review/order-void'},
        {
            'order_no': 'POS-100',
            'order_uuid': 'uuid-100',
            'business_date': '2026-08-12',
            'reason': 'Guest cancellation',
        },
    ))

    assert result.status_code == 200
    assert legacy_calls == []
    assert client.calls == [(
        'https://accounting.hiddenoasis.app/api/integrations/pos-review/order-void',
        {
            'order_no': 'POS-100',
            'reason': 'Guest cancellation',
            'business_date': '2026-08-12',
            'order_uuid': 'uuid-100',
            'external_id': 'uuid-100',
        },
    )]


def test_review_aware_void_preserves_explicit_legacy_fallback():
    legacy_calls = []

    async def legacy(client, base, config, payload):
        legacy_calls.append((base, config, payload))
        return DummyResponse()

    push = review_aware_order_void_push(legacy)
    payload = {'order_no': 'POS-200'}
    result = asyncio.run(push(DummyClient(), 'https://accounting.example/api', {}, payload))

    assert result.status_code == 200
    assert legacy_calls[0][2] == payload


def test_transport_installer_is_idempotent_for_api_and_worker_processes():
    async def legacy(client, base, config, payload):
        return DummyResponse()

    module = SimpleNamespace(_push_order_void=legacy)
    install_accounting_review_transport(module)
    first = module._push_order_void
    install_accounting_review_transport(module)
    second = module._push_order_void

    assert first is second
    assert getattr(second, '_accounting_review_aware', False) is True
