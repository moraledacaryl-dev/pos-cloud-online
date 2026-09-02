from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
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

OrderVoidPush = Callable[[httpx.AsyncClient, str, dict, dict], Awaitable[Any]]


def _join(base: str, path: str) -> str:
    return base.rstrip('/') + '/' + path.lstrip('/')


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


def review_aware_order_void_push(legacy_push: OrderVoidPush) -> OrderVoidPush:
    """Return an order-void sender that supports both review and legacy Accounting routes."""
    if getattr(legacy_push, '_accounting_review_aware', False) is True:
        return legacy_push

    async def push(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
        review_path = str(config.get('current_erp_sales_void_path') or '').strip()
        if not review_path:
            return await legacy_push(client, base, config, payload)

        mapped = {
            'order_no': payload.get('order_no'),
            'reason': payload.get('reason') or 'Voided in POS',
            'business_date': payload.get('business_date'),
            'order_uuid': payload.get('order_uuid'),
            'external_id': payload.get('order_uuid') or payload.get('order_no'),
        }
        return await client.post(_join(base, review_path), json=mapped)

    setattr(push, '_accounting_review_aware', True)
    return push


def install_accounting_review_transport(sync_service_module) -> None:
    """Install process-local Accounting transport adapters exactly once.

    Both the API process and the background sync worker call this installer. That
    prevents a worker-only code path from falling back to the legacy sale lookup
    when an order.voided event should instead go directly to Accounting's review
    intake route.
    """
    current = sync_service_module._push_order_void
    wrapped = review_aware_order_void_push(current)
    sync_service_module._push_order_void = wrapped
