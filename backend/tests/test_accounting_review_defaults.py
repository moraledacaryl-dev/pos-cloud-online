from unittest.mock import MagicMock, patch

from app.services.accounting_review_defaults import (
    REVIEW_ROUTE_DEFAULTS,
    ensure_accounting_review_routes,
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
