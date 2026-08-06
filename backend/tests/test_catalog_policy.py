from datetime import datetime, timedelta, timezone

from app.services.catalog_policy import CATALOG_STALE_AFTER_MINUTES, build_catalog_sync_status


def test_catalog_status_never_synced():
    status = build_catalog_sync_status({}, now=datetime(2026, 8, 7, tzinfo=timezone.utc))
    assert status['state'] == 'never_synced'
    assert status['ok'] is False
    assert status['ownership']['business_owner'] == 'inventory-procurement'
    assert status['ownership']['compatibility_transport'] == 'accounting-program-online'


def test_catalog_status_fresh():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    status = build_catalog_sync_status(
        {
            'last_sync_at': (now - timedelta(minutes=30)).isoformat(),
            'imported_rows': 18,
            'menu_items_seen': 12,
            'skus_seen': 18,
        },
        now=now,
    )
    assert status['state'] == 'fresh'
    assert status['ok'] is True
    assert status['age_minutes'] == 30
    assert status['imported_rows'] == 18


def test_catalog_status_stale_after_24_hours():
    now = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    status = build_catalog_sync_status(
        {'last_sync_at': (now - timedelta(minutes=CATALOG_STALE_AFTER_MINUTES + 1)).isoformat()},
        now=now,
    )
    assert status['state'] == 'stale'
    assert status['ok'] is False
