from __future__ import annotations

from sqlalchemy.orm import Session

from app.services.pos_service import save_setting_json, setting_json


REVIEW_ROUTE_DEFAULTS = {
    'current_erp_cashflow_path': '/integrations/pos-review/cashflow',
    'current_erp_transfers_path': '/integrations/pos-review/transfer',
    'current_erp_receivables_path': '/integrations/pos-review/room-charge',
    'current_erp_sales_path': '/integrations/pos-review/order',
    'current_erp_sales_void_path': '/integrations/pos-review/order-void',
    'current_erp_reconciliation_path': '/integrations/pos-review/reconciliation',
}

LEGACY_ROUTE_DEFAULTS = {
    'current_erp_cashflow_path': '/cashflow/transactions',
    'current_erp_transfers_path': '/transfers',
    'current_erp_receivables_path': '/receivables',
    'current_erp_sales_path': '/menu/sales',
    'current_erp_reconciliation_path': '/reconciliations',
}


def ensure_accounting_review_routes(db: Session) -> dict:
    """Move untouched POS defaults to Accounting's Review Inbox compatibility routes.

    Explicit custom paths are preserved. This makes existing deployments upgrade safely
    while new installations use review-first financial delivery without manual settings.
    """
    config = setting_json(db, 'accounting_sync', default={}) or {}
    config = dict(config) if isinstance(config, dict) else {}
    changed = False

    for key, review_path in REVIEW_ROUTE_DEFAULTS.items():
        current = config.get(key)
        legacy = LEGACY_ROUTE_DEFAULTS.get(key)
        if current in (None, '', legacy):
            config[key] = review_path
            changed = True

    if changed:
        save_setting_json(db, 'accounting_sync', config, username='system')
    return config
