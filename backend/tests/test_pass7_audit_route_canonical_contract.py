from pathlib import Path


def test_audit_router_declares_collection_without_trailing_slash():
    source = Path('app/api/audit.py').read_text(encoding='utf-8')
    assert "@router.get('')" in source
    assert "@router.get('/')" not in source
