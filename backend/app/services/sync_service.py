from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.entities import CashMovement, CatalogItem, PosOrder, Register, RegisterSession, SyncOutboxEvent
from app.services.pos_service import normalize_kds_station, now_iso, save_setting_json, setting_json


def _client_headers(config: dict) -> dict:
    headers = {'Accept': 'application/json'}
    token = (config or {}).get('api_token') or ''
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return headers


def _join(base: str, path: str) -> str:
    return base.rstrip('/') + '/' + path.lstrip('/')


def _load_payload(row: SyncOutboxEvent) -> dict:
    try:
        return json.loads(row.payload_json or '{}')
    except Exception:
        return {}


def _catalog_prep_station(menu: dict, sku: dict | None = None) -> str:
    sku = sku or {}
    return normalize_kds_station(
        sku.get('prep_station')
        or sku.get('kds_station')
        or menu.get('prep_station')
        or menu.get('kds_station')
        or menu.get('module_slug')
        or 'restaurant'
    )


def get_sync_config(db: Session) -> dict:
    cfg = setting_json(db, 'accounting_sync', default={})
    return cfg if isinstance(cfg, dict) else {}


async def _ensure_accounting_token(db: Session, config: dict) -> dict:
    base = (config.get('api_base') or '').strip()
    secret = (config.get('integration_secret') or '').strip()
    if not base or not secret:
        return config
    token_path = config.get('integration_token_path') or '/auth/integration/token'
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers={'Accept': 'application/json'}) as client:
        res = await client.post(_join(base, token_path), json={'secret': secret})
        if res.status_code >= 400:
            detail = res.text[:300]
            raise ValueError(f'Failed to refresh accounting integration token: {detail}')
        data = res.json() or {}
    token = data.get('access_token')
    if not token:
        raise ValueError('Accounting integration token response did not include access_token.')
    next_config = {**config, 'api_token': token}
    save_setting_json(db, 'accounting_sync', next_config, username='sync_service')
    return next_config


async def fetch_accounting_financial_accounts(db: Session) -> list[dict]:
    config = get_sync_config(db)
    base = (config.get('api_base') or '').strip()
    if not base:
        return []
    config = await _ensure_accounting_token(db, config)
    path = config.get('current_erp_financial_accounts_path') or '/financial-accounts'
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_client_headers(config)) as client:
        res = await client.get(_join(base, path), params={'only_active': 'true'})
        if res.status_code >= 400:
            detail = res.text[:300]
            raise ValueError(f'Failed to fetch financial accounts: {detail}')
        rows = res.json() or []
    return rows if isinstance(rows, list) else []


async def validate_account_mapping(db: Session, account_id: int | None = None, account_code: str | None = None) -> dict:
    rows = await fetch_accounting_financial_accounts(db)
    match = None
    for row in rows:
        if account_id and int(row.get('id') or 0) == int(account_id):
            match = row
            break
        if account_code and str(row.get('code') or '').strip().lower() == str(account_code).strip().lower():
            match = row
            break
    return {'ok': bool(match), 'account': match, 'count': len(rows)}


async def sync_catalog_from_accounting(db: Session) -> dict:
    config = get_sync_config(db)
    base = (config.get('api_base') or '').strip()
    if not base:
        raise ValueError('Accounting API base URL is not configured.')
    config = await _ensure_accounting_token(db, config)
    items_path = config.get('catalog_items_path') or '/menu/items'
    skus_path = config.get('catalog_skus_path') or '/menu/skus'
    headers = _client_headers(config)
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=headers) as client:
        items_res = await client.get(_join(base, items_path))
        if items_res.status_code >= 400:
            detail = items_res.text[:400]
            raise ValueError(f'Failed to fetch accounting menu items: {detail}')
        skus_res = await client.get(_join(base, skus_path))
        if skus_res.status_code >= 400:
            detail = skus_res.text[:400]
            raise ValueError(f'Failed to fetch accounting menu SKUs: {detail}')
        items = items_res.json() or []
        skus = skus_res.json() or []

    menu_by_id = {int(row.get('id')): row for row in items if row.get('id') is not None}
    skus_by_menu = {}
    touched = 0
    seen_external_skus = set()
    for sku in skus:
        external_sku_id = sku.get('id')
        if external_sku_id is None:
            continue
        external_sku_id = int(external_sku_id)
        menu_item_id = sku.get('menu_item_id')
        if menu_item_id is not None:
            skus_by_menu.setdefault(int(menu_item_id), []).append(sku)

    for sku in skus:
        external_sku_id = sku.get('id')
        if external_sku_id is None:
            continue
        external_sku_id = int(external_sku_id)
        seen_external_skus.add(external_sku_id)
        menu_item_id = sku.get('menu_item_id')
        menu = menu_by_id.get(int(menu_item_id or 0), {})
        display_name = ' - '.join([part for part in [menu.get('name'), sku.get('variant_name') or sku.get('size_label')] if part]) or str(menu.get('name') or sku.get('sku_code') or external_sku_id)
        accounting_hash = f"{menu.get('updated_at') or ''}|{sku.get('updated_at') or ''}|{sku.get('price') or ''}"
        row = db.query(CatalogItem).filter(CatalogItem.external_sku_id == external_sku_id).first()
        payload = {
            'external_menu_item_id': int(menu.get('id')) if menu.get('id') is not None else None,
            'external_sku_id': external_sku_id,
            'menu_item_name': menu.get('name') or display_name,
            'sku_code': sku.get('sku_code'),
            'variant_name': sku.get('variant_name') or sku.get('size_label'),
            'display_name': display_name,
            'category_name': menu.get('category'),
            'module_slug': menu.get('module_slug') or 'restaurant',
            'prep_station': _catalog_prep_station(menu, sku),
            'price': float(sku.get('price') or menu.get('price') or 0),
            'tax_rate': 0,
            'service_charge_rate': 0,
            'is_active': bool(sku.get('is_active', True)) and bool(menu.get('is_active', True)),
            'is_available': bool(sku.get('is_active', True)) and bool(menu.get('is_active', True)),
            'sort_order': 0,
            'accounting_hash': accounting_hash,
            'last_sync_at': now_iso(),
            'notes': menu.get('notes') or sku.get('notes'),
        }
        if not row:
            row = CatalogItem(**payload)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        db.add(row)
        touched += 1

    menu_items_with_variants = {menu_id for menu_id, variants in skus_by_menu.items() if variants}
    for menu_item_id, menu in menu_by_id.items():
        if menu_item_id in menu_items_with_variants:
            continue
        display_name = str(menu.get('name') or menu_item_id)
        accounting_hash = f"{menu.get('updated_at') or ''}|{menu.get('price') or ''}"
        row = db.query(CatalogItem).filter(CatalogItem.external_menu_item_id == menu_item_id, CatalogItem.external_sku_id == None).first()
        payload = {
            'external_menu_item_id': menu_item_id,
            'external_sku_id': None,
            'menu_item_name': menu.get('name') or display_name,
            'sku_code': menu.get('sku_code'),
            'variant_name': None,
            'display_name': display_name,
            'category_name': menu.get('category'),
            'module_slug': menu.get('module_slug') or 'restaurant',
            'prep_station': _catalog_prep_station(menu),
            'price': float(menu.get('price') or 0),
            'tax_rate': 0,
            'service_charge_rate': 0,
            'is_active': bool(menu.get('is_active', True)),
            'is_available': bool(menu.get('is_active', True)),
            'sort_order': 0,
            'accounting_hash': accounting_hash,
            'last_sync_at': now_iso(),
            'notes': menu.get('notes'),
        }
        if not row:
            row = CatalogItem(**payload)
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        db.add(row)
        touched += 1

    if seen_external_skus:
        stale_sku_rows = db.query(CatalogItem).filter(CatalogItem.external_sku_id != None, ~CatalogItem.external_sku_id.in_(list(seen_external_skus))).all()
        for row in stale_sku_rows:
            row.is_active = False
            row.is_available = False
            db.add(row)

    if menu_items_with_variants:
        stale_menu_rows = db.query(CatalogItem).filter(CatalogItem.external_menu_item_id.in_(list(menu_items_with_variants)), CatalogItem.external_sku_id == None).all()
        for row in stale_menu_rows:
            row.is_active = False
            row.is_available = False
            db.add(row)

    db.commit()
    return {'ok': True, 'imported_rows': touched, 'menu_items_seen': len(menu_by_id), 'skus_seen': len(seen_external_skus)}


async def _current_erp_transaction_exists(client: httpx.AsyncClient, base: str, path: str, reference_no: str) -> bool:
    if not reference_no:
        return False
    res = await client.get(_join(base, path), params={'q': reference_no, 'limit': 50})
    if res.status_code >= 400:
        return False
    rows = res.json() or []
    return any(str(row.get('reference_no') or '') == str(reference_no) for row in rows)


async def _current_erp_transfer_exists(client: httpx.AsyncClient, base: str, path: str, reference_no: str) -> bool:
    if not reference_no:
        return False
    res = await client.get(_join(base, path), params={'limit': 200})
    if res.status_code >= 400:
        return False
    rows = res.json() or []
    return any(str(row.get('reference_no') or '') == str(reference_no) for row in rows)


async def _find_current_erp_sale(client: httpx.AsyncClient, base: str, path: str, order_no: str) -> dict | None:
    res = await client.get(_join(base, path), params={'limit': 300})
    if res.status_code >= 400:
        return None
    rows = res.json() or []
    for row in rows:
        if str(row.get('order_no') or '') == str(order_no):
            return row
    return None


async def _current_erp_reconciliation_exists(client: httpx.AsyncClient, base: str, path: str, account_id: int | None, shift_name: str, business_date: str) -> bool:
    params = {'account_id': account_id, 'start_date': business_date, 'end_date': business_date, 'limit': 200}
    res = await client.get(_join(base, path), params=params)
    if res.status_code >= 400:
        return False
    rows = res.json() or []
    return any(str(row.get('shift_name') or '') == str(shift_name) for row in rows)


async def _push_cash_movement(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    mode = (config.get('mode') or 'current_erp').strip().lower()
    if mode == 'future_facade':
        path = config.get('future_facade_cash_path') or '/integrations/pos/cash-events'
        return await client.post(_join(base, path), json=payload)
    path = config.get('current_erp_cashflow_path') or '/cashflow/transactions'
    exists_path = config.get('current_erp_transactions_lookup_path') or path
    reference_no = payload.get('reference_no') or payload.get('cash_event_uuid')
    if await _current_erp_transaction_exists(client, base, exists_path, reference_no):
        return None
    mapped = {
        'transaction_date': payload.get('event_date'),
        'direction': payload.get('direction'),
        'financial_account_id': payload.get('accounting_financial_account_id'),
        'module': 'restaurant',
        'category': 'POS Drawer',
        'subcategory': payload.get('movement_type') or payload.get('category'),
        'level3_item': payload.get('category') or payload.get('movement_type'),
        'amount': payload.get('amount'),
        'payment_method': 'cash',
        'reference_no': reference_no,
        'counterparty_name': 'Dedicated POS',
        'notes': payload.get('note'),
        'linked_record_type': 'pos_cash_movement',
        'linked_record_id': payload.get('id'),
        'bir_include': False,
        'status': 'posted',
        'auto_post_accounting': False,
        'allow_overdraw': True,
        'external_source': 'dedicated_pos_cloud',
        'external_id': reference_no,
    }
    return await client.post(_join(base, path), json=mapped)


async def _push_transfer(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    path = config.get('current_erp_transfers_path') or '/transfers'
    reference_no = payload.get('reference_no') or payload.get('cash_event_uuid')
    if await _current_erp_transfer_exists(client, base, path, reference_no):
        return None
    mapped = {
        'transfer_date': payload.get('transfer_date'),
        'from_account_id': payload.get('from_account_id'),
        'to_account_id': payload.get('to_account_id'),
        'amount': payload.get('amount'),
        'reference_no': reference_no,
        'notes': payload.get('note'),
        'status': 'posted',
        'auto_post_accounting': False,
        'allow_overdraw': True,
        'external_source': 'dedicated_pos_cloud',
        'external_id': reference_no,
    }
    return await client.post(_join(base, path), json=mapped)


async def _push_payment_collection(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    payment = (payload or {}).get('payment') or {}
    tender = str(payment.get('tender_type') or '').strip().lower()
    if not tender:
        return None
    if tender == 'room_charge':
        path = config.get('current_erp_receivables_path') or '/receivables'
        receivable_payload = {
            'source_type': 'pos_order',
            'source_id': payload.get('order_id'),
            'counterparty_name': payload.get('guest_name') or f"Room Charge {payload.get('order_no')}",
            'receivable_type': 'guest_balance',
            'transaction_date': payload.get('business_date'),
            'gross_amount': payment.get('amount_applied') or 0,
            'amount_collected': 0,
            'status': 'open',
            'notes': json.dumps({'source': 'dedicated_pos_cloud', 'order_no': payload.get('order_no'), 'table_label': payload.get('table_label')}, ensure_ascii=False),
            'bir_include': False,
        }
        return await client.post(_join(base, path), json=receivable_payload)

    path = config.get('current_erp_cashflow_path') or '/cashflow/transactions'
    exists_path = config.get('current_erp_transactions_lookup_path') or path
    reference_no = payment.get('reference_no') or f"{payload.get('order_no')}:{tender}"
    if await _current_erp_transaction_exists(client, base, exists_path, reference_no):
        return None
    mapped = {
        'transaction_date': payload.get('business_date'),
        'direction': 'in',
        'financial_account_id': payment.get('accounting_financial_account_id'),
        'module': 'restaurant',
        'category': 'POS Settlement',
        'subcategory': tender,
        'level3_item': f"Order {payload.get('order_no')}",
        'amount': payment.get('amount_applied') or 0,
        'payment_method': tender,
        'reference_no': reference_no,
        'counterparty_name': payload.get('guest_name') or 'Walk-in Guest',
        'notes': payment.get('note') or f"POS {tender} settlement for {payload.get('order_no')}",
        'linked_record_type': 'pos_order_payment',
        'linked_record_id': payload.get('order_id'),
        'bir_include': False,
        'status': 'posted',
        'auto_post_accounting': False,
        'allow_overdraw': True,
        'external_source': 'dedicated_pos_cloud',
        'external_id': reference_no,
    }
    return await client.post(_join(base, path), json=mapped)


async def _push_payment_refund(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    payment = (payload or {}).get('payment') or {}
    tender = str(payment.get('tender_type') or '').strip().lower()
    if not tender:
        return None
    if tender == 'room_charge':
        path = config.get('current_erp_receivables_path') or '/receivables'
        receivable_payload = {
            'source_type': 'pos_refund',
            'source_id': payment.get('id'),
            'counterparty_name': payload.get('guest_name') or f"Room Charge Refund {payload.get('order_no')}",
            'receivable_type': 'guest_balance',
            'transaction_date': payload.get('created_at') or payload.get('business_date'),
            'gross_amount': -(payment.get('amount') or 0),  # Negative for refund
            'amount_collected': 0,
            'status': 'open',
            'notes': json.dumps({'source': 'dedicated_pos_cloud', 'refund_no': payload.get('refund_no'), 'order_no': payload.get('order_no')}, ensure_ascii=False),
            'bir_include': False,
        }
        return await client.post(_join(base, path), json=receivable_payload)
    path = config.get('current_erp_cashflow_path') or '/cashflow/transactions'
    exists_path = config.get('current_erp_transactions_lookup_path') or path
    reference_no = payment.get('reference_no') or f"{payload.get('refund_no') or payload.get('order_no')}:refund:{tender}"
    if await _current_erp_transaction_exists(client, base, exists_path, reference_no):
        return None
    mapped = {
        'transaction_date': payload.get('created_at') or payload.get('business_date'),
        'direction': 'out',
        'financial_account_id': payment.get('accounting_financial_account_id'),
        'module': 'restaurant',
        'category': 'POS Refund',
        'subcategory': tender,
        'level3_item': f"Refund {payload.get('refund_no') or payload.get('order_no')}",
        'amount': payment.get('amount') or 0,
        'payment_method': tender,
        'reference_no': reference_no,
        'counterparty_name': payload.get('guest_name') or 'Walk-in Guest',
        'notes': payment.get('note') or f"POS refund via {tender} for {payload.get('order_no')}",
        'linked_record_type': 'pos_refund_payment',
        'linked_record_id': payment.get('id'),
        'bir_include': False,
        'status': 'posted',
        'auto_post_accounting': False,
        'allow_overdraw': True,
        'external_source': 'dedicated_pos_cloud',
        'external_id': f"refund-payment:{payment.get('id')}",
    }
    return await client.post(_join(base, path), json=mapped)


async def _push_room_charge_request(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    posting = (payload or {}).get('room_charge_posting') or {}
    if not posting:
        return None
    path = config.get('current_erp_receivables_path') or '/receivables'
    receivable_payload = {
        'source_type': 'pos_room_charge',
        'source_id': posting.get('id'),
        'counterparty_name': posting.get('guest_label') or f"Room {posting.get('room_number')}",
        'receivable_type': 'guest_balance',
        'transaction_date': posting.get('service_date') or posting.get('business_date'),
        'gross_amount': posting.get('charge_amount') or 0,
        'amount_collected': 0,
        'status': 'open' if (posting.get('charge_amount') or 0) > 0 else 'closed',  # For reversals, maybe closed or negative
        'notes': json.dumps({
            'source': 'dedicated_pos_cloud',
            'order_no': payload.get('order', {}).get('order_no'),
            'room_number': posting.get('room_number'),
            'service_type': posting.get('service_type'),
            'posting_uuid': posting.get('posting_uuid'),
        }, ensure_ascii=False),
        'bir_include': False,
    }
    return await client.post(_join(base, path), json=receivable_payload)


async def _push_order(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    mode = (config.get('mode') or 'current_erp').strip().lower()
    if mode == 'future_facade':
        path = config.get('future_facade_sales_path') or '/integrations/pos/sales/finalize'
        return await client.post(_join(base, path), json=payload)
    path = config.get('current_erp_sales_path') or '/menu/sales'
    existing = await _find_current_erp_sale(client, base, path, payload.get('order_no'))
    if existing:
        return None
    lines = []
    for line in payload.get('lines') or []:
        external_menu_item_id = line.get('external_menu_item_id')
        if not external_menu_item_id:
            raise ValueError(f"Order {payload.get('order_no')} has a line without external_menu_item_id. Sync catalog from accounting first.")
        lines.append({
            'menu_item_id': external_menu_item_id,
            'sku_id': line.get('external_sku_id'),
            'quantity': line.get('quantity'),
            'unit_price': line.get('unit_price'),
            'discount_amount': line.get('discount_amount') or 0,
            'notes': line.get('note'),
        })
    payment_breakdown = payload.get('payment_breakdown') or []
    payment_method = payload.get('primary_tender') or 'cash'
    if len(payment_breakdown) > 1:
        payment_method = 'mixed'
    mapped = {
        'order_no': payload.get('order_no'),
        'order_date': payload.get('business_date'),
        'payment_method': payment_method,
        'channel': payload.get('order_type') or payload.get('source_channel'),
        'counterparty': payload.get('guest_name') or 'Walk-in Guest',
        'notes': json.dumps({
            'source': 'dedicated_pos_cloud',
            'order_uuid': payload.get('order_uuid'),
            'table_label': payload.get('table_label'),
            'payments': payment_breakdown,
        }, ensure_ascii=False),
        'strict_inventory': True,
        'auto_post_accounting': False,
        'external_source': 'dedicated_pos_cloud',
        'external_id': payload.get('order_uuid') or payload.get('order_no'),
        'lines': lines,
    }
    return await client.post(_join(base, path), json=mapped)


async def _push_order_void(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    path = config.get('current_erp_sales_path') or '/menu/sales'
    sale = await _find_current_erp_sale(client, base, path, payload.get('order_no'))
    if not sale:
        return None
    if sale.get('status') == 'voided':
        return None
    sale_id = sale.get('id')
    if not sale_id:
        return None
    body = {
        'reason': payload.get('reason') or 'Voided in POS',
        'void_date': payload.get('business_date'),
        'reverse_inventory': True,
        'auto_post_accounting': False,
    }
    return await client.post(_join(base, f"{path}/{sale_id}/void"), json=body)


async def _push_reconciliation(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    mode = (config.get('mode') or 'current_erp').strip().lower()
    if mode == 'future_facade':
        path = config.get('future_facade_reconciliation_path') or '/integrations/pos/reconciliations'
        return await client.post(_join(base, path), json=payload)
    path = config.get('current_erp_reconciliation_path') or '/reconciliations'
    exists_path = config.get('current_erp_reconciliations_lookup_path') or path
    if await _current_erp_reconciliation_exists(client, base, exists_path, payload.get('register_accounting_financial_account_id'), payload.get('session_code'), payload.get('business_date')):
        return None
    mapped = {
        'financial_account_id': payload.get('register_accounting_financial_account_id'),
        'reconciliation_date': payload.get('business_date'),
        'shift_name': payload.get('session_code'),
        'actual_counted': payload.get('closing_actual_cash'),
        'status': 'counted',
        'counted_by': 'Dedicated POS',
        'notes': f"Expected {payload.get('closing_expected_cash')} / variance {payload.get('variance_amount')} / mode {payload.get('close_mode')}",
        'lines': payload.get('denomination_lines') or [
            {'line_label': 'Counted Cash', 'amount': payload.get('closing_actual_cash') or 0, 'notes': 'Submitted by Dedicated POS', 'sort_order': 0},
        ],
    }
    return await client.post(_join(base, path), json=mapped)


async def run_outbox_sync(db: Session, limit: int = 25) -> dict:
    config = get_sync_config(db)
    base = (config.get('api_base') or '').strip()
    if not base:
        raise ValueError('Accounting API base URL is not configured.')
    config = await _ensure_accounting_token(db, config)
    query = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.status.in_(['pending', 'failed'])).order_by(SyncOutboxEvent.id.asc())
    rows = query.limit(max(int(limit or 25), 1)).all()
    synced = 0
    failed = 0
    blocked = 0
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_client_headers(config)) as client:
        for row in rows:
            payload = _load_payload(row)
            row.last_attempt_at = now_iso()
            try:
                if row.event_type == 'cash_movement.created' and config.get('sync_cash_movements', True):
                    res = await _push_cash_movement(client, base, config, payload)
                elif row.event_type == 'transfer.created' and config.get('sync_cash_movements', True):
                    res = await _push_transfer(client, base, config, payload)
                elif row.event_type == 'payment.collected' and config.get('sync_cash_movements', True):
                    res = await _push_payment_collection(client, base, config, payload)
                elif row.event_type == 'payment.folio_pending' and config.get('sync_cash_movements', True):
                    res = await _push_payment_collection(client, base, config, payload)
                elif row.event_type == 'payment.refunded' and config.get('sync_cash_movements', True):
                    res = await _push_payment_refund(client, base, config, payload)
                elif row.event_type == 'room_charge.request_created' and config.get('sync_room_charges', True):
                    res = await _push_room_charge_request(client, base, config, payload)
                elif row.event_type == 'order.finalized' and config.get('sync_orders', True):
                    res = await _push_order(client, base, config, payload)
                elif row.event_type == 'order.voided' and config.get('sync_orders', True):
                    res = await _push_order_void(client, base, config, payload)
                elif row.event_type == 'session.closed' and config.get('sync_reconciliations', True):
                    res = await _push_reconciliation(client, base, config, payload)
                else:
                    row.status = 'blocked'
                    row.last_error = f'Unsupported or disabled event type: {row.event_type}'
                    blocked += 1
                    db.add(row)
                    continue

                if res is None or res.status_code < 400:
                    row.status = 'synced'
                    row.synced_at = now_iso()
                    row.last_error = None
                    synced += 1
                else:
                    try:
                        body = res.json()
                    except Exception:
                        body = res.text[:500]
                    row.status = 'failed'
                    row.retry_count = int(row.retry_count or 0) + 1
                    row.next_retry_at = (datetime.utcnow() + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
                    row.last_error = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
                    failed += 1
                if row.event_type in {'cash_movement.created', 'transfer.created'} and row.status == 'synced':
                    movement = db.get(CashMovement, int(row.aggregate_id))
                    if movement:
                        movement.synced_to_accounting = True
                        movement.last_sync_at = now_iso()
                        db.add(movement)
                elif row.event_type in {'order.finalized', 'order.voided'} and row.status == 'synced':
                    order = db.get(PosOrder, int(row.aggregate_id))
                    if order:
                        order.synced_to_accounting = True
                        order.last_sync_at = now_iso()
                        db.add(order)
                elif row.event_type == 'room_charge.request_created' and row.status == 'synced':
                    posting = db.get(RoomChargePosting, int(row.aggregate_id))
                    if posting:
                        posting.synced_to_accounting = True
                        posting.last_sync_at = now_iso()
                        db.add(posting)
                elif row.event_type == 'room_charge.request_created' and row.status == 'synced':
                    posting = db.get(RoomChargePosting, int(row.aggregate_id))
                    if posting:
                        posting.synced_to_accounting = True
                        posting.last_sync_at = now_iso()
                        db.add(posting)
                db.add(row)
                db.commit()
            except ValueError as e:
                row.status = 'blocked'
                row.last_error = str(e)
                blocked += 1
                db.add(row)
                db.commit()
            except Exception as e:
                row.status = 'failed'
                row.retry_count = int(row.retry_count or 0) + 1
                row.next_retry_at = (datetime.utcnow() + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
                row.last_error = str(e)
                failed += 1
                db.add(row)
                db.commit()
    return {'ok': True, 'processed': len(rows), 'synced': synced, 'failed': failed, 'blocked': blocked}


async def retry_outbox_event(db: Session, event_id: int) -> dict:
    config = get_sync_config(db)
    base = (config.get('api_base') or '').strip()
    if not base:
        raise ValueError('Accounting API base URL is not configured.')
    config = await _ensure_accounting_token(db, config)
    row = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.id == event_id).first()
    if not row:
        raise ValueError('Outbox event not found.')
    if row.status == 'synced':
        raise ValueError('Event is already synced.')
    synced = 0
    failed = 0
    blocked = 0
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_client_headers(config)) as client:
        payload = _load_payload(row)
        row.last_attempt_at = now_iso()
        try:
            if row.event_type == 'cash_movement.created' and config.get('sync_cash_movements', True):
                res = await _push_cash_movement(client, base, config, payload)
            elif row.event_type == 'transfer.created' and config.get('sync_cash_movements', True):
                res = await _push_transfer(client, base, config, payload)
            elif row.event_type == 'payment.collected' and config.get('sync_cash_movements', True):
                res = await _push_payment_collection(client, base, config, payload)
            elif row.event_type == 'payment.folio_pending' and config.get('sync_cash_movements', True):
                res = await _push_payment_collection(client, base, config, payload)
            elif row.event_type == 'payment.refunded' and config.get('sync_cash_movements', True):
                res = await _push_payment_refund(client, base, config, payload)
            elif row.event_type == 'order.finalized' and config.get('sync_orders', True):
                res = await _push_order(client, base, config, payload)
            elif row.event_type == 'order.voided' and config.get('sync_orders', True):
                res = await _push_order_void(client, base, config, payload)
            elif row.event_type == 'session.closed' and config.get('sync_reconciliations', True):
                res = await _push_reconciliation(client, base, config, payload)
            else:
                row.status = 'blocked'
                row.last_error = f'Unsupported or disabled event type: {row.event_type}'
                blocked += 1
                db.add(row)
                db.commit()
                return {'ok': False, 'blocked': True, 'error': row.last_error}

            if res is None or res.status_code < 400:
                row.status = 'synced'
                row.synced_at = now_iso()
                row.last_error = None
                synced += 1
            else:
                try:
                    body = res.json()
                except Exception:
                    body = res.text[:500]
                row.status = 'failed'
                row.retry_count = int(row.retry_count or 0) + 1
                row.next_retry_at = (datetime.utcnow() + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
                row.last_error = json.dumps(body, ensure_ascii=False) if not isinstance(body, str) else body
                failed += 1
            if row.event_type in {'cash_movement.created', 'transfer.created'} and row.status == 'synced':
                movement = db.get(CashMovement, int(row.aggregate_id))
                if movement:
                    movement.synced_to_accounting = True
                    movement.last_sync_at = now_iso()
                    db.add(movement)
            elif row.event_type in {'order.finalized', 'order.voided'} and row.status == 'synced':
                order = db.get(PosOrder, int(row.aggregate_id))
                if order:
                    order.synced_to_accounting = True
                    order.last_sync_at = now_iso()
                    db.add(order)
            db.add(row)
            db.commit()
            return {'ok': True, 'synced': synced, 'failed': failed, 'blocked': blocked}
        except ValueError as e:
            row.status = 'blocked'
            row.last_error = str(e)
            blocked += 1
            db.add(row)
            db.commit()
            return {'ok': False, 'blocked': True, 'error': str(e)}
        except Exception as e:
            row.status = 'failed'
            row.retry_count = int(row.retry_count or 0) + 1
            row.next_retry_at = (datetime.utcnow() + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
            row.last_error = str(e)
            failed += 1
            db.add(row)
            db.commit()
            return {'ok': False, 'failed': True, 'error': str(e)}



async def unblock_outbox_event(db: Session, event_id: int) -> dict:
    row = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.id == event_id).first()
    if not row:
        raise ValueError('Sync event not found')
    if row.status not in {'blocked', 'failed'}:
        raise ValueError('Event is not blocked or failed')
    
    row.status = 'pending'
    row.next_retry_at = _now_text()
    row.last_attempt_at = None
    row.last_error = None
    db.commit()
    
    return _serialize_outbox_event(row)


async def archive_outbox_event(db: Session, event_id: int, reason: str) -> dict:
    row = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.id == event_id).first()
    if not row:
        raise ValueError('Sync event not found')
    if row.status == 'synced':
        raise ValueError('Cannot archive synced event')
    
    row.status = 'archived'
    row.last_error = f'Archived: {reason}'
    db.commit()
    
    return _serialize_outbox_event(row)


async def resolve_outbox_event(db: Session, event_id: int, resolution: str) -> dict:
    row = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.id == event_id).first()
    if not row:
        raise ValueError('Sync event not found')
    if row.status not in {'failed', 'blocked'}:
        raise ValueError('Event is not in a resolvable state')
    
    row.status = 'resolved'
    row.last_error = f'Resolved: {resolution}'
    db.commit()
    
    return _serialize_outbox_event(row)


async def mapping_health_summary(db: Session) -> dict:
    accounts = await fetch_accounting_financial_accounts(db)
    by_id = {int(row.get('id')): row for row in accounts if row.get('id') is not None}
    results = []
    for register in db.query(Register).order_by(Register.name.asc()).all():
        account = by_id.get(int(register.accounting_financial_account_id or 0)) if register.accounting_financial_account_id else None
        healthy = bool(account)
        results.append({
            'register_id': register.id,
            'register_code': register.code,
            'register_name': register.name,
            'accounting_financial_account_id': register.accounting_financial_account_id,
            'accounting_financial_account_code': register.accounting_financial_account_code,
            'healthy': healthy,
            'account_name': account.get('name') if account else None,
            'account_type': account.get('account_type') if account else None,
        })
    return {'ok': True, 'rows': results, 'healthy_count': sum(1 for row in results if row['healthy']), 'total_count': len(results)}



def record_sync_worker_heartbeat(db: Session, status: str = "ok", result: dict | None = None, error: str | None = None):
    payload = {
        "last_seen_at": now_iso(),
        "last_cycle": {"status": status, "result": result or {}},
        "last_error": error,
        "worker": {"component": "sync_worker"},
    }
    save_setting_json(db, "sync_worker_heartbeat", payload, username="sync_worker")
    return payload
