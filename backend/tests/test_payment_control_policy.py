from types import SimpleNamespace

import pytest

from app.services.payment_control_policy import validate_cash_movement_control, validate_payment_control


def payment(tender, applied, received=None, reference=None, **extra):
    return SimpleNamespace(
        tender_type=tender,
        amount_applied=applied,
        amount_received=received,
        reference_no=reference,
        room_charge_booking_snapshot_id=extra.get('booking_snapshot_id'),
        room_charge_room_number=extra.get('room_number'),
    )


def cash(direction, movement_type, amount, note=None, reference=None, approved_by=None):
    return SimpleNamespace(
        direction=direction,
        movement_type=movement_type,
        amount=amount,
        note=note,
        reference_no=reference,
        approved_by_user_id=approved_by,
    )


def test_exact_split_payment_is_valid():
    result = validate_payment_control(
        {'status': 'draft', 'total_amount': 500},
        [payment('cash', 200, 500), payment('gcash', 300, 300, 'GC-123')],
    )
    assert result['applied_total'] == 500


def test_payment_must_exactly_cover_order():
    with pytest.raises(ValueError, match='lower'):
        validate_payment_control({'status': 'draft', 'total_amount': 500}, [payment('cash', 499, 500)])
    with pytest.raises(ValueError, match='exceed'):
        validate_payment_control({'status': 'draft', 'total_amount': 500}, [payment('cash', 501, 501)])


def test_non_cash_reference_is_required():
    with pytest.raises(ValueError, match='reference'):
        validate_payment_control({'status': 'draft', 'total_amount': 100}, [payment('gcash', 100, 100)])


def test_duplicate_tender_reference_is_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        validate_payment_control(
            {'status': 'draft', 'total_amount': 200},
            [payment('gcash', 100, 100, 'ABC'), payment('gcash', 100, 100, 'abc')],
        )


def test_sensitive_cash_out_requires_controls():
    with pytest.raises(ValueError, match='reason note'):
        validate_cash_movement_control(cash('out', 'paid_out', 100))
    with pytest.raises(ValueError, match='reference number'):
        validate_cash_movement_control(cash('out', 'paid_out', 100, note='Petty cash'))
    with pytest.raises(ValueError, match='manager approval'):
        validate_cash_movement_control(cash('out', 'paid_out', 100, note='Petty cash', reference='PC-1'))


def test_sensitive_cash_out_is_valid_with_approval():
    result = validate_cash_movement_control(cash('out', 'paid_out', 100, note='Petty cash', reference='PC-1', approved_by=2))
    assert result['ok'] is True


def test_cash_direction_must_match_movement_type():
    with pytest.raises(ValueError, match='direction out'):
        validate_cash_movement_control(cash('in', 'safe_drop', 100, note='Safe', reference='SD-1', approved_by=2))
