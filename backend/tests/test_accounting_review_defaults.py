import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.accounting_review_defaults import (
    REVIEW_ROUTE_DEFAULTS,
    ensure_accounting_review_routes,
    review_aware_order_void_push,
)


def test_missing_routes_are_filled_with_review_defaults():
    db = MagicMock()
    with patch('app.services.accounting_review_defaults.setting_json', return_value={'api_base': 'https://accounting.example/api'}), \
         patch('app.services.accounting_review_defaults.save_setting_json') as save:
        result = ensure_accounting_review_routes(db)

    for key, value in REVIEW_ROUTE_DEFAULTS.items():
        assert result[key] == value
    save.assert_called_once()


def test_legacy_routes_are_upgraded_but_custom_routes_are_preserved():
    db = MagicMock()
    existing = {
        'current_erp_cashflow_path': '/cashflow/transactions',
        'current_erp_sales_path': '/custom/accounting/sales',
    }
    with patch('app.services.accounting_review_defaults.setting_json', return_value=existing), \
         patch('app.services.accounting_review_defaults.save_setting_json') as save:
        result = ensure_accounting_review_routes(db)

    assert result['current_erp_cashflow_path'] == '/integrations/pos-review/cashflow'
    assert result['current_erp_sales_path'] == '/custom/accounting/sales'
    assert result['current_erp_sales_void_path'] == '/integrations/pos-review/order-void'
    save.assert_called_once()


def test_review_routes_are_idempotent():
    db = MagicMock()
    existing = dict(REVIEW_ROUTE_DEFAULTS)
    with patch('app.services.accounting_review_defaults.setting_json', return_value=existing), \
         patch('app.services.accounting_review_defaults.save_setting_json') as save:
        result = ensure_accounting_review_routes(db)

    assert result == existing
    save.assert_not_called()


def test_review_order_void_posts_directly_without_legacy_lookup():
    legacy = AsyncMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    push = review_aware_order_void_push(legacy)

    result = asyncio.run(push(
        client,
        'https://accounting.example/api',
        {'current_erp_sales_void_path': '/integrations/pos-review/order-void'},
        {
            'order_no': 'POS-1001',
            'order_uuid': 'order-uuid-1001',
            'reason': 'Guest cancellation',
            'business_date': '2026-07-17',
        },
    ))

    assert result.status_code == 200
    legacy.assert_not_awaited()
    client.post.assert_awaited_once_with(
        'https://accounting.example/api/integrations/pos-review/order-void',
        json={
            'order_no': 'POS-1001',
            'reason': 'Guest cancellation',
            'business_date': '2026-07-17',
            'order_uuid': 'order-uuid-1001',
            'external_id': 'order-uuid-1001',
        },
    )


def test_custom_or_legacy_order_void_uses_existing_sender():
    expected = MagicMock(status_code=200)
    legacy = AsyncMock(return_value=expected)
    client = MagicMock()
    push = review_aware_order_void_push(legacy)

    result = asyncio.run(push(client, 'https://accounting.example/api', {}, {'order_no': 'POS-1002'}))

    assert result is expected
    legacy.assert_awaited_once_with(client, 'https://accounting.example/api', {}, {'order_no': 'POS-1002'})


def test_order_void_adapter_is_idempotent():
    legacy = AsyncMock()
    first = review_aware_order_void_push(legacy)
    second = review_aware_order_void_push(first)
    assert second is first
