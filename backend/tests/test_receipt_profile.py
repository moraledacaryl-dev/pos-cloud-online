import pytest
from fastapi import HTTPException

from app.api.system_settings import public_receipt_profile, update_settings
from app.schemas.common import SystemSettingsUpdate


def test_public_receipt_profile_discards_unknown_fields_and_bounds_values():
    profile = public_receipt_profile({'registered_name': 'A' * 600, 'private': 'secret'})
    assert len(profile['registered_name']) == 500
    assert 'private' not in profile


def test_registered_receipt_profile_requires_verified_terminal_fields():
    payload = SystemSettingsUpdate(receipt_profile={
        'registration_status': 'registered',
        'tax_registration_type': 'vat',
        'registered_name': 'Hidden Oasis',
    })
    with pytest.raises(HTTPException, match='Complete the registered receipt profile'):
        update_settings(payload, db=None, current_user=None)
