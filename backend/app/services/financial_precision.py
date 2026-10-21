"""Exact Decimal monetary and quantity rules used by POS transactions.

Keep this module independent of the database and HTTP layer. The public
transaction service re-exports the existing helper names for compatibility.
Do not use binary floating-point arithmetic for settlement calculations.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


MONEY_QUANTUM = Decimal('0.01')
QUANTITY_QUANTUM = Decimal('0.0001')


def _decimal(value) -> Decimal:
    if value is None or value == '':
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _money(value) -> Decimal:
    return _decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantity(value) -> Decimal:
    return _decimal(value).quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)


def _validated_money(value, label: str, *, allow_negative: bool = False) -> Decimal:
    """Reject non-finite and negative money before quantization can conceal them."""
    try:
        amount = _decimal(value)
        if not amount.is_finite():
            raise ValueError(f'{label} must be a finite amount.')
        if amount < 0 and not allow_negative:
            raise ValueError(f'{label} cannot be negative.')
        return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, OverflowError) as exc:
        raise ValueError(f'{label} must be a valid finite amount.') from exc


def _validated_rate(value, label: str) -> Decimal:
    """Catalog tax/service rates are stored as fractions (0.12 means 12%)."""
    try:
        rate = _decimal(value)
        if not rate.is_finite() or not Decimal('0') <= rate <= Decimal('1'):
            raise ValueError(f'{label} must be a finite fraction between 0 and 1.')
        return rate.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, OverflowError) as exc:
        raise ValueError(f'{label} must be a finite fraction between 0 and 1.') from exc


def _validated_quantity(value) -> Decimal:
    try:
        quantity = _decimal(value)
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError('Line quantity must be greater than zero and finite.')
        rounded = quantity.quantize(QUANTITY_QUANTUM, rounding=ROUND_HALF_UP)
        if rounded <= 0:
            raise ValueError('Line quantity must be greater than zero after rounding.')
        return rounded
    except (InvalidOperation, TypeError, OverflowError) as exc:
        raise ValueError('Line quantity must be greater than zero and finite.') from exc
