from datetime import datetime, timezone

from scripts.seed_visual_audit import visual_audit_business_date


def test_visual_audit_seed_uses_philippine_business_date_after_utc_midnight():
    # 19:02 UTC is already 03:02 the next day in the Philippines.
    instant = datetime(2026, 10, 22, 19, 2, tzinfo=timezone.utc)
    assert visual_audit_business_date(instant) == "2026-10-23"


def test_visual_audit_seed_uses_current_philippine_date_before_rollover():
    instant = datetime(2026, 10, 22, 15, 59, tzinfo=timezone.utc)
    assert visual_audit_business_date(instant) == "2026-10-22"
