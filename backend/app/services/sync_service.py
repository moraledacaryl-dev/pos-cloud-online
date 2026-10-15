from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.entities import (
    CashMovement,
    CatalogItem,
    InHouseBookingSnapshot,
    PosOrder,
    Register,
    RoomChargePosting,
    SyncOutboxEvent,
)
from app.services.inventory_integration import INVENTORY_EVENT_TYPES, run_inventory_outbox_sync
from app.services.operations_integration import OPERATIONS_EVENT_PREFIX, run_operations_outbox_sync
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


def _serialize_outbox_event(row: SyncOutboxEvent) -> dict:
    return {
        'id': row.id,
        'event_uuid': row.event_uuid,
        'aggregate_type': row.aggregate_type,
        'aggregate_id': row.aggregate_id,
        'event_type': row.event_type,
        'idempotency_key': row.idempotency_key,
        'payload_json': row.payload_json,
        'status': row.status,
        'retry_count': row.retry_count,
        'next_retry_at': row.next_retry_at,
        'last_attempt_at': row.last_attempt_at,
        'last_error': row.last_error,
        'synced_at': row.synced_at,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }


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
    cfg = cfg if isinstance(cfg, dict) else {}
    mode = str(cfg.get('mode') or 'current_erp').strip().lower()
    if mode != 'current_erp':
        raise ValueError('Only current_erp accounting sync is supported. Change the POS sync mode before running sync.')
    return {**cfg, 'mode': 'current_erp'}


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def _default_room_charge_lookup_window(days_back: int = 1, days_forward: int = 21) -> tuple[str, str]:
    today = datetime.now(timezone(timedelta(hours=8))).date()
    return (today - timedelta(days=max(int(days_back or 0), 0))).isoformat(), (today + timedelta(days=max(int(days_forward or 0), 0))).isoformat()


async def _ensure_accounting_token(db: Session, config: dict) -> dict:
    base = (config.get('api_base') or '').strip()
    secret = (config.get('integration_secret') or '').strip()
    if not base or not secret:
        return config
    token_path = config.get('integration_token_path') or '/auth/integration/token'
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers={'Accept': 'application/json'},
        follow_redirects=True,
    ) as client:
        res = await client.post(_join(base, token_path), json={'secret': secret})
        if not 200 <= res.status_code < 300:
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
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers=_client_headers(config),
        follow_redirects=True,
    ) as client:
        res = await client.get(_join(base, path), params={'only_active': 'true'})
        if not 200 <= res.status_code < 300:
            detail = res.text[:300]
            raise ValueError(f'Failed to fetch financial accounts: {detail}')
        rows = res.json() or []
    return rows if isinstance(rows, list) else []


async def sync_in_house_bookings_from_accounting(
    db: Session,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    days_back: int = 1,
    days_forward: int = 21,
    force: bool = False,
) -> dict:
    meta = setting_json(db, 'room_charge_booking_sync', default={}) or {}
    last_sync_at = meta.get('last_sync_at')
    if not force and last_sync_at:
        try:
            last_sync = datetime.fromisoformat(str(last_sync_at).replace('Z', '+00:00'))
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - last_sync).total_seconds() < 900:
                return {'ok': True, 'skipped': True, 'reason': 'recently_synced', **meta}
        except Exception:
            pass

    default_start, default_end = _default_room_charge_lookup_window(days_back=days_back, days_forward=days_forward)
    start = _parse_date(start_date or default_start)
    end = _parse_date(end_date or default_end)
    if not start or not end:
        raise ValueError('Valid start_date and end_date are required.')
    if end < start:
        raise ValueError('end_date cannot be before start_date.')

    config = get_sync_config(db)
    base = (config.get('api_base') or '').strip()
    if not base:
        raise ValueError('Accounting API base URL is not configured.')
    config = await _ensure_accounting_token(db, config)
    path = config.get('accounting_bookings_calendar_path') or '/reservations/bookings/calendar'
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers=_client_headers(config), follow_redirects=True) as client:
        res = await client.get(_join(base, path), params={'start_date': start.isoformat(), 'end_date': end.isoformat()})
        if not 200 <= res.status_code < 300:
            detail = res.text[:400]
            raise ValueError(f'Failed to fetch Accounting booking calendar: {detail}')
        bookings = res.json() or []
    if not isinstance(bookings, list):
        bookings = []

    created = updated = skipped = deactivated = 0
    seen_keys: set[tuple[str, str]] = set()
    inactive_statuses = {'cancelled', 'canceled', 'no_show', 'noshow'}
    for booking in bookings:
        check_in = _parse_date(booking.get('check_in'))
        check_out = _parse_date(booking.get('check_out'))
        if not check_in or not check_out:
            skipped += 1
            continue
        first = max(check_in, start)
        last = min(check_out, end)
        room_display_name = str(booking.get('room_display_name') or booking.get('room_name') or '').strip()
        room_code = str(booking.get('room_no') or '').strip()
        room_number = room_display_name or room_code
        guest_name = str(booking.get('guest_full_name') or booking.get('guest_name') or 'Guest').strip()
        if not room_number:
            skipped += 1
            continue
        external_id = str(booking.get('external_booking_id') or '').strip()
        source_key = external_id or f"accounting:{booking.get('id')}"
        status = str(booking.get('status') or 'confirmed').strip() or 'confirmed'
        is_active = status.lower() not in inactive_statuses
        current = first
        while current <= last:
            stay_date = current.isoformat()
            seen_keys.add((stay_date, source_key))
            row = (
                db.query(InHouseBookingSnapshot)
                .filter(
                    InHouseBookingSnapshot.stay_date == stay_date,
                    InHouseBookingSnapshot.beds24_booking_id == source_key,
                    InHouseBookingSnapshot.source == 'accounting_booking_sync',
                )
                .first()
            )
            if row:
                updated += 1
            else:
                row = InHouseBookingSnapshot(stay_date=stay_date, beds24_booking_id=source_key, source='accounting_booking_sync')
                created += 1
            row.room_number = room_number
            row.guest_name = guest_name
            row.guest_label = guest_name
            row.arrival_date = check_in.isoformat()
            row.departure_date = check_out.isoformat()
            row.booking_status = status
            row.is_active = is_active
            note_parts = [
                f"Accounting booking {booking.get('id') or ''}",
                f"channel {booking.get('channel_display_name') or booking.get('channel') or ''}",
            ]
            if room_code and room_display_name and room_code != room_display_name:
                note_parts.append(f"room code {room_code}")
            row.notes = '; '.join(part.strip() for part in note_parts if part.strip())
            db.add(row)
            current += timedelta(days=1)

    rows = (
        db.query(InHouseBookingSnapshot)
        .filter(InHouseBookingSnapshot.source == 'accounting_booking_sync')
        .filter(InHouseBookingSnapshot.stay_date >= start.isoformat())
        .filter(InHouseBookingSnapshot.stay_date <= end.isoformat())
        .all()
    )
    for row in rows:
        key = (row.stay_date, row.beds24_booking_id or '')
        if key not in seen_keys and row.is_active:
            row.is_active = False
            db.add(row)
            deactivated += 1
    summary = {
        'ok': True,
        'skipped': False,
        'source': 'accounting_booking_sync',
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'fetched': len(bookings),
        'created': created,
        'updated': updated,
        'deactivated': deactivated,
        'ignored': skipped,
        'last_sync_at': datetime.now(timezone.utc).isoformat(),
    }
    save_setting_json(db, 'room_charge_booking_sync', summary, username='sync_service')
    db.commit()
    return summary


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


async def sync_catalog_from_inventory(db: Session, *, force: bool = True) -> dict:
    meta = setting_json(db, 'catalog_sync', default={}) or {}
    last_sync_at = meta.get('last_sync_at')
    if not force and last_sync_at:
        try:
            last_sync = datetime.fromisoformat(str(last_sync_at).replace('Z', '+00:00'))
            if last_sync.tzinfo is None:
                last_sync = last_sync.replace(tzinfo=timezone.utc)
            if (datetime.now(timezone.utc) - last_sync).total_seconds() < 900:
                return {'ok': True, 'skipped': True, 'reason': 'recently_synced', **meta}
        except Exception:
            pass
    if not settings.inventory_integration_enabled:
        raise ValueError('Inventory integration is disabled.')
    base = (settings.inventory_api_base or '').strip()
    token = (settings.inventory_integration_token or '').strip()
    if not base or not token:
        raise ValueError('Inventory catalog integration is not configured.')
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers={'Accept': 'application/json', 'X-Integration-Token': token},
        follow_redirects=True,
    ) as client:
        res = await client.get(_join(base, settings.inventory_catalog_path))
        if not 200 <= res.status_code < 300:
            raise ValueError(f'Failed to fetch Inventory catalog: {res.text[:400]}')
        payload = res.json() or {}
    items = payload.get('items') if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError('Inventory catalog response did not contain an items list.')
    if not items:
        raise ValueError('Inventory catalog returned zero items; refusing to deactivate the last known selling catalog.')

    pricing_rules = payload.get('pricing_rules') or []
    if not isinstance(pricing_rules, list):
        raise ValueError('Inventory catalog response has invalid pricing_rules.')
    normalized_rules = []
    seen_rule_ids = set()
    for rule in pricing_rules:
        if not isinstance(rule, dict) or not str(rule.get('id') or '').strip():
            raise ValueError('Inventory catalog contains an invalid pricing rule.')
        rule_id = str(rule['id']).strip()
        if rule_id in seen_rule_ids:
            raise ValueError(f'Inventory catalog contains duplicate pricing rule {rule_id}.')
        seen_rule_ids.add(rule_id)
        normalized_rules.append({'id': rule_id, 'name': str(rule.get('name') or rule_id), 'qualifier_tag': str(rule.get('qualifier_tag') or '').strip(), 'target_tag': str(rule.get('target_tag') or '').strip(), 'priority': int(rule.get('priority') or 100)})

    # Validate the complete upstream snapshot before mutating the local catalog.
    validated_items = []
    seen_payload_variants = set()
    for index, source in enumerate(items):
        if not isinstance(source, dict):
            raise ValueError(f'Inventory catalog row {index + 1} is not an object.')
        variant_id = str(source.get('variant_id') or '').strip()
        menu_id = str(source.get('menu_item_id') or '').strip()
        if not variant_id or not menu_id:
            raise ValueError(f'Inventory catalog row {index + 1} is missing menu_item_id or variant_id.')
        if variant_id in seen_payload_variants:
            raise ValueError(f'Inventory catalog contains duplicate variant_id {variant_id}.')
        seen_payload_variants.add(variant_id)
        try:
            price = Decimal(str(source.get('price')))
            if not price.is_finite() or price < 0:
                raise InvalidOperation
            sort_order = int(source.get('sort_order') or 0)
            with_drink_price = None if source.get('with_drink_price') is None else Decimal(str(source.get('with_drink_price')))
            if with_drink_price is not None and (not with_drink_price.is_finite() or with_drink_price < 0 or with_drink_price > price):
                raise InvalidOperation
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f'Inventory catalog row {index + 1} has an invalid price or sort_order.')
        pricing_role = str(source.get('pricing_role') or 'standard').strip().lower()
        if pricing_role not in {'standard', 'drink', 'pastry'}:
            raise ValueError(f'Inventory catalog row {index + 1} has an invalid pricing_role.')
        modifier_groups = source.get('modifier_groups') or []
        pricing_tags = source.get('pricing_tags') or []
        conditional_prices = source.get('conditional_prices') or []
        if not isinstance(modifier_groups, list) or not isinstance(pricing_tags, list) or not isinstance(conditional_prices, list):
            raise ValueError(f'Inventory catalog row {index + 1} has invalid selling-rule metadata.')
        normalized_prices=[]
        for cp in conditional_prices:
            if not isinstance(cp,dict) or str(cp.get('rule_id') or '').strip() not in seen_rule_ids:
                raise ValueError(f'Inventory catalog row {index + 1} references an unknown pricing rule.')
            try:
                cp_price=Decimal(str(cp.get('price')))
                if not cp_price.is_finite() or cp_price < 0: raise InvalidOperation
            except (InvalidOperation,TypeError,ValueError):
                raise ValueError(f'Inventory catalog row {index + 1} has an invalid conditional price.')
            normalized_prices.append({'rule_id':str(cp['rule_id']).strip(),'price':str(cp_price)})
        validated_items.append((source, menu_id, variant_id, price, with_drink_price, pricing_role, modifier_groups, [str(x).strip() for x in pricing_tags if str(x).strip()], normalized_prices, sort_order))

    touched = 0
    seen_variants = set()
    for source, menu_id, variant_id, price, with_drink_price, pricing_role, modifier_groups, pricing_tags, conditional_prices, sort_order in validated_items:
        seen_variants.add(variant_id)
        row = db.query(CatalogItem).filter(CatalogItem.inventory_variant_id == variant_id).first()
        sku = str(source.get('sku') or '').strip() or None
        # Migration bridge: claim an existing row only when the SKU match is unique.
        if not row and sku:
            sku_matches = db.query(CatalogItem).filter(CatalogItem.sku_code == sku).limit(2).all()
            if len(sku_matches) > 1:
                raise ValueError(f'Cannot safely bridge Inventory SKU {sku}: multiple POS catalog rows use it.')
            row = sku_matches[0] if sku_matches else None
        active = bool(source.get('is_active', True)) and bool(source.get('pos_visible', True))
        display = str(source.get('display_name') or source.get('menu_item_name') or sku or variant_id)
        variant_name = str(source.get('variant_name') or '').strip() or None
        if variant_name and variant_name.lower() not in {'regular', 'default'}:
            display = f"{display} - {variant_name}"
        values = {
            'inventory_menu_item_id': menu_id,
            'inventory_variant_id': variant_id,
            'menu_item_name': source.get('menu_item_name') or display,
            'sku_code': sku,
            'variant_name': variant_name,
            'display_name': display,
            'category_name': source.get('category'),
            'module_slug': 'restaurant',
            'prep_station': _catalog_prep_station(source),
            'price': price,
            'with_drink_price': with_drink_price,
            'pricing_role': pricing_role,
            'pricing_tags_json': json.dumps(pricing_tags, ensure_ascii=False),
            'conditional_prices_json': json.dumps(conditional_prices, ensure_ascii=False),
            'modifier_groups_json': json.dumps(modifier_groups, ensure_ascii=False),
            'is_active': active,
            'is_available': row.availability_override if row and row.availability_override is not None else active,
            'sort_order': sort_order,
            'last_sync_at': now_iso(),
            'accounting_hash': None,
        }
        if not row:
            row = CatalogItem(**values)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        db.add(row)
        touched += 1

    stale = db.query(CatalogItem).filter(CatalogItem.inventory_variant_id != None).all()
    for row in stale:
        if row.inventory_variant_id not in seen_variants:
            row.is_active = False
            row.is_available = False
            db.add(row)
    summary = {
        'ok': True, 'source': 'inventory-procurement', 'transport': 'direct_inventory_api',
        'imported_rows': touched, 'menu_items_seen': len({str(x.get('menu_item_id')) for x in items if x.get('menu_item_id')}),
        'skus_seen': len(seen_variants), 'pricing_rules': normalized_rules, 'last_sync_at': now_iso(),
    }
    save_setting_json(db, 'catalog_sync', summary, username='sync_service')
    db.commit()
    return summary


async def _current_erp_transaction_exists(client: httpx.AsyncClient, base: str, path: str, reference_no: str) -> bool:
    if not reference_no:
        return False
    res = await client.get(_join(base, path), params={'q': reference_no, 'limit': 50})
    if not 200 <= res.status_code < 300:
        return False
    rows = res.json() or []
    return any(str(row.get('reference_no') or '') == str(reference_no) for row in rows)


async def _current_erp_transfer_exists(client: httpx.AsyncClient, base: str, path: str, reference_no: str) -> bool:
    if not reference_no:
        return False
    res = await client.get(_join(base, path), params={'limit': 200})
    if not 200 <= res.status_code < 300:
        return False
    rows = res.json() or []
    return any(str(row.get('reference_no') or '') == str(reference_no) for row in rows)


async def _find_current_erp_sale(client: httpx.AsyncClient, base: str, path: str, order_no: str) -> dict | None:
    res = await client.get(_join(base, path), params={'limit': 300})
    if not 200 <= res.status_code < 300:
        return None
    rows = res.json() or []
    for row in rows:
        if str(row.get('order_no') or '') == str(order_no):
            return row
    return None


async def _current_erp_reconciliation_exists(client: httpx.AsyncClient, base: str, path: str, account_id: int | None, shift_name: str, business_date: str) -> bool:
    params = {'account_id': account_id, 'start_date': business_date, 'end_date': business_date, 'limit': 200}
    res = await client.get(_join(base, path), params=params)
    if not 200 <= res.status_code < 300:
        return False
    rows = res.json() or []
    return any(str(row.get('shift_name') or '') == str(shift_name) for row in rows)


async def _push_cash_movement(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
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
        # Dedicated room_charge.request_created events own folio receivables.
        return None

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
        # Room-charge reversals are owned by room_charge.request_created events.
        # Sending payment.refunded as a negative pos_refund receivable violates
        # Accounting's receivable reversal contract.
        return None
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
    path = config.get('current_erp_pos_room_charge_path') or '/integrations/pos/room-charge'
    receivable_payload = {
        'source_type': 'pos_room_charge_reversal' if (posting.get('charge_amount') or 0) < 0 else 'pos_room_charge',
        'source_id': posting.get('id'),
        'counterparty_name': posting.get('guest_label') or f"Room {posting.get('room_number')}",
        'receivable_type': 'guest_balance',
        'transaction_date': posting.get('service_date') or posting.get('business_date'),
        'gross_amount': posting.get('charge_amount') or 0,
        'external_source': 'dedicated_pos_cloud',
        'external_id': f"room-charge:{posting.get('posting_uuid') or posting.get('id')}",
        'posting_uuid': posting.get('posting_uuid'),
        'order_no': payload.get('order', {}).get('order_no'),
        'room_number': posting.get('room_number'),
        'service_type': posting.get('service_type'),
        'reverses_source_type': payload.get('reverses_source_type'),
        'reverses_source_id': payload.get('reverses_source_id'),
    }
    return await client.post(_join(base, path), json=receivable_payload)


async def _push_order(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    path = config.get('current_erp_pos_order_path') or '/integrations/pos/order'
    lines = [
        {
            'catalog_item_id': line.get('catalog_item_id'),
            'inventory_menu_item_id': line.get('inventory_menu_item_id'),
            'inventory_variant_id': line.get('inventory_variant_id'),
            'sku_code': line.get('sku_code'),
            'item_name': line.get('item_name_snapshot'),
            'quantity': line.get('quantity'),
            'unit_price': line.get('unit_price'),
            'discount_amount': line.get('discount_amount') or 0,
            'notes': line.get('note'),
        }
        for line in payload.get('lines') or []
    ]
    payment_breakdown = payload.get('payment_breakdown') or []
    payment_method = payload.get('primary_tender') or 'cash'
    if len(payment_breakdown) > 1:
        payment_method = 'mixed'
    mapped = {
        'order_no': payload.get('order_no'),
        'order_uuid': payload.get('order_uuid'),
        'external_id': payload.get('order_uuid') or payload.get('order_no'),
        'order_date': payload.get('business_date'),
        'payment_method': payment_method,
        'channel': payload.get('order_type') or payload.get('source_channel'),
        'counterparty': payload.get('guest_name') or 'Walk-in Guest',
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
        'reverse_inventory': False,
        'auto_post_accounting': False,
    }
    return await client.post(_join(base, f"{path}/{sale_id}/void"), json=body)


async def _push_reconciliation(client: httpx.AsyncClient, base: str, config: dict, payload: dict):
    if not payload.get('register_accounting_financial_account_id'):
        raise ValueError('Register drawer is not mapped to an Accounting financial account. Map the register before retrying this reconciliation.')
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
    current_time = now_iso()
    query = db.query(SyncOutboxEvent).filter(
        or_(
            SyncOutboxEvent.status == 'pending',
            and_(
                SyncOutboxEvent.status == 'failed',
                or_(SyncOutboxEvent.next_retry_at.is_(None), SyncOutboxEvent.next_retry_at <= current_time),
            ),
        )
    ).order_by(SyncOutboxEvent.id.asc())
    rows = query.limit(max(int(limit or 25), 1)).all()
    synced = 0
    failed = 0
    blocked = 0
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers=_client_headers(config),
        follow_redirects=True,
    ) as client:
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

                if res is None or 200 <= res.status_code < 300:
                    row.status = 'synced'
                    row.synced_at = now_iso()
                    row.retry_count = 0
                    row.next_retry_at = None
                    row.last_error = None
                    synced += 1
                else:
                    try:
                        body = res.json()
                    except Exception:
                        body = res.text[:500]
                    row.status = 'failed'
                    row.retry_count = int(row.retry_count or 0) + 1
                    row.next_retry_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
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
                row.next_retry_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
                row.last_error = str(e)
                failed += 1
                db.add(row)
                db.commit()
    return {'ok': True, 'processed': len(rows), 'synced': synced, 'failed': failed, 'blocked': blocked}


async def retry_outbox_event(db: Session, event_id: int) -> dict:
    integration_row = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.id == event_id).first()
    if not integration_row:
        raise ValueError('Outbox event not found.')
    if integration_row.event_type in INVENTORY_EVENT_TYPES.values():
        if integration_row.status == 'synced':
            raise ValueError('Event is already synced.')
        integration_row.status = 'inventory_pending'
        integration_row.next_retry_at = None
        integration_row.last_error = None
        db.add(integration_row)
        db.commit()
        return await run_inventory_outbox_sync(db, limit=1, event_id=event_id)
    if integration_row.event_type.startswith(OPERATIONS_EVENT_PREFIX):
        if integration_row.status == 'synced':
            raise ValueError('Event is already synced.')
        integration_row.status = 'operations_pending'
        integration_row.next_retry_at = None
        integration_row.last_error = None
        db.add(integration_row)
        db.commit()
        return await run_operations_outbox_sync(db, limit=1, event_id=event_id)
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
    async with httpx.AsyncClient(
        timeout=settings.http_timeout_seconds,
        headers=_client_headers(config),
        follow_redirects=True,
    ) as client:
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
                db.commit()
                return {'ok': False, 'blocked': True, 'error': row.last_error}

            if res is None or 200 <= res.status_code < 300:
                row.status = 'synced'
                row.synced_at = now_iso()
                row.retry_count = 0
                row.next_retry_at = None
                row.last_error = None
                synced += 1
            else:
                try:
                    body = res.json()
                except Exception:
                    body = res.text[:500]
                row.status = 'failed'
                row.retry_count = int(row.retry_count or 0) + 1
                row.next_retry_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
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
            row.next_retry_at = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
            row.last_error = str(e)
            failed += 1
            db.add(row)
            db.commit()
            return {'ok': False, 'failed': True, 'error': str(e)}



async def unblock_outbox_event(db: Session, event_id: int) -> dict:
    row = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.id == event_id).first()
    if not row:
        raise ValueError('Sync event not found')
    if row.status not in {'blocked', 'failed', 'inventory_retry', 'operations_retry', 'operations_blocked'}:
        raise ValueError('Event is not blocked or failed')

    if row.event_type in INVENTORY_EVENT_TYPES.values():
        row.status = 'inventory_pending'
    elif row.event_type.startswith(OPERATIONS_EVENT_PREFIX):
        row.status = 'operations_pending'
    else:
        row.status = 'pending'
    row.next_retry_at = now_iso()
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
    if row.status not in {'failed', 'blocked', 'inventory_retry', 'operations_retry', 'operations_blocked'}:
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
