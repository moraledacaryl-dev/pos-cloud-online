from types import SimpleNamespace

import pytest

from app.services.room_charge_policy import validate_room_charge_status_update


def payload(status, **kwargs):
    base = {
        'posting_status': status,
        'beds24_posting_reference': None,
        'rejected_reason': None,
        'dispute_note': None,
        'note': None,
        'later_payment_status': None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def current(status='pending_frontdesk_post', **kwargs):
    base = {
        'posting_status': status,
        'beds24_posting_reference': None,
        'rejected_reason': None,
        'dispute_note': None,
        'note': None,
        'posted_to_beds24_at': None,
    }
    base.update(kwargs)
    return base


def test_posted_requires_reference():
    with pytest.raises(ValueError, match='posting reference'):
        validate_room_charge_status_update(current(), payload('posted_to_beds24'))


def test_posted_accepts_reference():
    validate_room_charge_status_update(
        current(),
        payload('posted_to_beds24', beds24_posting_reference='B24-7788'),
    )


def test_rejected_requires_reason():
    with pytest.raises(ValueError, match='rejection reason'):
        validate_room_charge_status_update(current(), payload('rejected'))


def test_disputed_requires_note():
    with pytest.raises(ValueError, match='dispute note'):
        validate_room_charge_status_update(current(), payload('disputed'))


def test_write_off_requires_note():
    with pytest.raises(ValueError, match='write-off note'):
        validate_room_charge_status_update(
            current(status='posted_to_beds24', beds24_posting_reference='B24-1', posted_to_beds24_at='2026-08-12T10:00:00'),
            payload('written_off'),
        )


def test_settlement_requires_posting_reference():
    with pytest.raises(ValueError, match='cannot be settled without'):
        validate_room_charge_status_update(
            current(status='posted_to_beds24', posted_to_beds24_at='2026-08-12T10:00:00'),
            payload('settled_at_frontdesk'),
        )


def test_disputed_never_posted_cannot_jump_to_settlement():
    with pytest.raises(ValueError, match='never confirmed posted'):
        validate_room_charge_status_update(
            current(status='disputed', beds24_posting_reference='B24-1'),
            payload('settled_at_frontdesk'),
        )


def test_disputed_previously_posted_can_settle():
    validate_room_charge_status_update(
        current(
            status='disputed',
            beds24_posting_reference='B24-1',
            posted_to_beds24_at='2026-08-12T10:00:00',
        ),
        payload('settled_at_frontdesk', later_payment_status='settled'),
    )


def test_final_status_is_immutable():
    with pytest.raises(ValueError, match='immutable'):
        validate_room_charge_status_update(
            current(status='settled_at_frontdesk', beds24_posting_reference='B24-1'),
            payload('settled_at_frontdesk', note='changed later'),
        )


def test_settlement_rejects_noncanonical_later_payment_status():
    with pytest.raises(ValueError, match='later_payment_status'):
        validate_room_charge_status_update(
            current(
                status='posted_to_beds24',
                beds24_posting_reference='B24-1',
                posted_to_beds24_at='2026-08-12T10:00:00',
            ),
            payload('settled_at_frontdesk', later_payment_status='paid'),
        )
