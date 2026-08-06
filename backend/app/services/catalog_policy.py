from __future__ import annotations

from datetime import datetime, timezone

CATALOG_STALE_AFTER_MINUTES = 24 * 60

CATALOG_OWNERSHIP = {
    'business_owner': 'inventory-procurement',
    'compatibility_transport': 'accounting-program-online',
    'pos_role': 'selling_snapshot_and_local_availability',
    'master_fields': [
        'external_menu_item_id',
        'external_sku_id',
        'menu_item_name',
        'sku_code',
        'variant_name',
        'category_name',
        'price',
        'tax_rate',
        'service_charge_rate',
        'is_active',
    ],
    'pos_local_fields': [
        'is_available',
        'availability_override',
        'prep_station',
        'sort_order',
    ],
}


def build_catalog_sync_status(meta: dict | None, *, now: datetime | None = None) -> dict:
    meta = meta if isinstance(meta, dict) else {}
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)

    last_sync_at = meta.get('last_sync_at')
    age_minutes = None
    stale = True
    if last_sync_at:
        try:
            parsed = datetime.fromisoformat(str(last_sync_at).replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_minutes = max(int((current - parsed).total_seconds() // 60), 0)
            stale = age_minutes > CATALOG_STALE_AFTER_MINUTES
        except (TypeError, ValueError):
            stale = True

    return {
        'ok': bool(last_sync_at) and not stale,
        'state': 'fresh' if last_sync_at and not stale else ('stale' if last_sync_at else 'never_synced'),
        'last_sync_at': last_sync_at,
        'age_minutes': age_minutes,
        'stale_after_minutes': CATALOG_STALE_AFTER_MINUTES,
        'imported_rows': int(meta.get('imported_rows') or 0),
        'menu_items_seen': int(meta.get('menu_items_seen') or 0),
        'skus_seen': int(meta.get('skus_seen') or 0),
        'ownership': CATALOG_OWNERSHIP,
    }
