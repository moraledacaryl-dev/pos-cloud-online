from decimal import Decimal
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


def test_fractional_split_payment_uses_decimal_not_binary_float_math():
    result = validate_payment_control(
        {'status': 'draft', 'total_amount': '0.30'},
        [payment('cash', '0.10', '0.10'), payment('cash', '0.20', '0.20')],
    )
    assert result['applied_total'] == Decimal('0.30')


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
    # The policy validates the cash fields; the API enforces the manager grant
    # from an authenticated server-side approval instead of a client user ID.
    valid = validate_cash_movement_control(cash('out', 'paid_out', 100, note='Petty cash', reference='PC-1'))
    assert valid['ok'] is True


def test_sensitive_cash_out_is_valid_with_approval():
    result = validate_cash_movement_control(cash('out', 'paid_out', 100, note='Petty cash', reference='PC-1', approved_by=2))
    assert result['ok'] is True


def test_cash_direction_must_match_movement_type():
    with pytest.raises(ValueError, match='direction out'):
        validate_cash_movement_control(cash('in', 'safe_drop', 100, note='Safe', reference='SD-1', approved_by=2))


@pytest.mark.parametrize('bad', [
    '99.995', '99.991', Decimal('99.999'), Decimal('0.005'),
])
def test_cashier_cannot_silently_round_applied_payment_to_cents(bad):
    with pytest.raises(ValueError, match='fractions of a cent'):
        validate_payment_control(
            {'status': 'draft', 'total_amount': '100.00'},
            [payment('cash', bad, '100.00')],
        )


@pytest.mark.parametrize('tender,reference', [
    ('cash', None), ('gcash', 'GC-precision-1'),
    ('bank_transfer', 'BPI-precision-1'), ('room_charge', None),
])
def test_received_amount_must_use_exact_cents_for_all_tenders(tender, reference):
    kwargs = {'room_number': '101'} if tender == 'room_charge' else {}
    with pytest.raises(ValueError, match='fractions of a cent'):
        validate_payment_control(
            {'status': 'draft', 'total_amount': '100.00'},
            [payment(tender, '100.00', Decimal('100.005'), reference, **kwargs)],
        )


@pytest.mark.parametrize('bad', ['200.005', '0.005', Decimal('100.001')])
def test_cashier_cannot_silently_round_drawer_movement(bad):
    with pytest.raises(ValueError, match='fractions of a cent'):
        validate_cash_movement_control(
            cash('in', 'paid_in', bad),
        )


def test_financial_entry_accepts_exact_cents_and_trailing_zeros():
    result = validate_payment_control(
        {'status': 'draft', 'total_amount': Decimal('100.00')},
        [payment('cash', Decimal('99.9000'), '100.00'), payment('gcash', '0.100', '0.10', 'GC-TEST')],
    )
    assert result['applied_total'] == Decimal('100.00')
    drawer = validate_cash_movement_control(cash('in', 'paid_in', Decimal('10.000')))
    assert drawer['amount'] == Decimal('10.00')


@pytest.mark.parametrize('invalid', [float('inf'), Decimal('NaN'), Decimal('Infinity')])
def test_financial_entry_rejects_non_finite_values(invalid):
    with pytest.raises(ValueError, match='finite'):
        validate_payment_control(
            {'status': 'draft', 'total_amount': Decimal('100.00')},
            [payment('cash', invalid, '100.00')],
        )
    with pytest.raises(ValueError, match='finite'):
        validate_cash_movement_control(cash('in', 'paid_in', invalid))


def test_fractional_cent_is_not_hidden_in_split_payment():
    # Before this control each line could round separately and still match the
    # server total even though the cashier submitted non-cent values.
    with pytest.raises(ValueError, match='fractions of a cent'):
        validate_payment_control(
            {'status': 'draft', 'total_amount': '0.03'},
            [payment('cash', Decimal('0.015')), payment('cash', Decimal('0.015'))],
        )
