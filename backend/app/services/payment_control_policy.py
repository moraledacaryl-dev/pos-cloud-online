from __future__ import annotations

import math

REFERENCE_TENDERS = {'gcash', 'card', 'bank_transfer'}
SUPPORTED_TENDERS = {'cash', 'gcash', 'card', 'bank_transfer', 'room_charge'}
CASH_DIRECTIONS = {'in', 'out'}
CASH_MOVEMENT_DIRECTIONS = {
    'opening_float': 'in',
    'cash_sale': 'in',
    'paid_in': 'in',
    'float_addition': 'in',
    'paid_out': 'out',
    'refund': 'out',
    'safe_drop': 'out',
    'owner_withdrawal': 'out',
    'adjustment_out': 'out',
}
SENSITIVE_CASH_MOVEMENTS = {'paid_out', 'safe_drop', 'owner_withdrawal', 'adjustment_out'}


def _money(value, label: str) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} must be a valid amount.') from exc
    if not math.isfinite(amount):
        raise ValueError(f'{label} must be finite.')
    return round(amount, 2)


def validate_payment_control(order: dict, payments) -> dict:
    if str(order.get('status') or '').lower() not in {'draft', 'held', 'open', 'sent', 'served', 'unpaid'}:
        raise ValueError('This order is not eligible for payment.')
    if not payments:
        raise ValueError('At least one payment line is required.')

    order_total = _money(order.get('total_amount') or 0, 'Order total')
    if order_total <= 0:
        raise ValueError('Order total must be greater than zero before payment.')

    applied_total = 0.0
    references: set[tuple[str, str]] = set()
    for index, payment in enumerate(payments, start=1):
        tender = str(getattr(payment, 'tender_type', '') or '').strip().lower()
        if tender not in SUPPORTED_TENDERS:
            raise ValueError(f'Payment line {index} has an unsupported tender type.')
        applied = _money(getattr(payment, 'amount_applied', None), f'Payment line {index} amount')
        if applied <= 0:
            raise ValueError(f'Payment line {index} amount must be greater than zero.')
        applied_total = round(applied_total + applied, 2)

        received_raw = getattr(payment, 'amount_received', None)
        if tender == 'cash':
            received = _money(received_raw if received_raw is not None else applied, f'Payment line {index} amount received')
            if received < applied:
                raise ValueError('Cash amount received cannot be lower than the applied amount.')
        elif received_raw is not None and abs(_money(received_raw, f'Payment line {index} amount received') - applied) > 0.009:
            raise ValueError('Non-cash amount received must equal the applied amount.')

        reference = str(getattr(payment, 'reference_no', '') or '').strip()
        if tender in REFERENCE_TENDERS and not reference:
            raise ValueError(f'{tender.replace("_", " ").title()} requires a transaction reference.')
        if reference:
            key = (tender, reference.casefold())
            if key in references:
                raise ValueError('Duplicate tender references are not allowed in one payment.')
            references.add(key)

        if tender == 'room_charge':
            snapshot_id = getattr(payment, 'room_charge_booking_snapshot_id', None)
            room_number = str(getattr(payment, 'room_charge_room_number', '') or '').strip()
            if not snapshot_id and not room_number:
                raise ValueError('Room charge requires a selected booking or room number.')

    difference = round(applied_total - order_total, 2)
    if abs(difference) > 0.009:
        if difference < 0:
            raise ValueError('Payment total is lower than the order total.')
        raise ValueError('Payment applied total cannot exceed the order total.')

    return {'ok': True, 'order_total': order_total, 'applied_total': applied_total, 'payment_count': len(payments)}


def validate_cash_movement_control(payload) -> dict:
    direction = str(getattr(payload, 'direction', '') or '').strip().lower()
    movement_type = str(getattr(payload, 'movement_type', '') or '').strip().lower()
    amount = _money(getattr(payload, 'amount', None), 'Cash movement amount')
    note = str(getattr(payload, 'note', '') or '').strip()
    reference = str(getattr(payload, 'reference_no', '') or '').strip()

    if direction not in CASH_DIRECTIONS:
        raise ValueError('Cash movement direction must be in or out.')
    if amount <= 0:
        raise ValueError('Cash movement amount must be greater than zero.')
    expected_direction = CASH_MOVEMENT_DIRECTIONS.get(movement_type)
    if expected_direction and direction != expected_direction:
        raise ValueError(f'{movement_type.replace("_", " ").title()} must use direction {expected_direction}.')
    if movement_type in SENSITIVE_CASH_MOVEMENTS:
        if not note:
            raise ValueError('Sensitive cash-out movements require a reason note.')
        if not reference:
            raise ValueError('Sensitive cash-out movements require a reference number.')
        if not getattr(payload, 'approved_by_user_id', None):
            raise ValueError('Sensitive cash-out movements require manager approval.')

    return {'ok': True, 'direction': direction, 'movement_type': movement_type, 'amount': amount}
