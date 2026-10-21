"""Contract tests for the shared Decimal precision rules.

Protect payment, refund, inventory quantity and tax calculations against
float conversion, nonfinite data and silent rounding-to-zero.
"""

from decimal import Decimal

import pytest

from app.services import financial_precision as fp
from app.services import pos_service


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('0.1', Decimal('0.10')),
        ('0.2', Decimal('0.20')),
        ('1.005', Decimal('1.01')),
        ('1.004', Decimal('1.00')),
        ('-1.005', Decimal('-1.01')),
    ],
)
def test_decimal_money_half_up_quantization(value, expected):
    assert fp._money(value) == expected


def test_money_addition_is_exact_after_quantization():
    assert fp._money('0.1') + fp._money('0.2') == Decimal('0.30')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', 'not money', None])
def test_validated_money_rejects_invalid_or_nonfinite_amounts(value):
    if value is None:
        assert fp._validated_money(value, 'Total') == Decimal('0.00')
    else:
        with pytest.raises(ValueError):
            fp._validated_money(value, 'Total')


def test_validated_money_rejects_negative_by_default_and_allows_signed_adjustments():
    with pytest.raises(ValueError, match='cannot be negative'):
        fp._validated_money('-0.01', 'Adjustment')
    assert fp._validated_money('-0.015', 'Adjustment', allow_negative=True) == Decimal('-0.02')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '-0.001', '1.001', 'invalid'])
def test_validated_rate_rejects_nonfinite_and_out_of_range_values(value):
    with pytest.raises(ValueError):
        fp._validated_rate(value, 'Tax rate')


def test_validated_rate_fraction_quantization():
    assert fp._validated_rate('0.1255555', 'Tax rate') == Decimal('0.125556')
    assert fp._validated_rate('1', 'Tax rate') == Decimal('1.000000')
    assert fp._validated_rate('0', 'Tax rate') == Decimal('0.000000')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '-Infinity', '0', '-1', '0.00004', 'invalid'])
def test_quantity_rejects_nonpositive_nonfinite_and_rounding_to_zero(value):
    with pytest.raises(ValueError):
        fp._validated_quantity(value)


def test_quantity_uses_four_decimal_places_and_half_up():
    assert fp._validated_quantity('0.00005') == Decimal('0.0001')
    assert fp._validated_quantity('1.23456') == Decimal('1.2346')


def test_pos_service_keeps_existing_precision_helper_api():
    for helper in ('_decimal', '_money', '_quantity', '_validated_money', '_validated_quantity', '_validated_rate'):
        assert getattr(pos_service, helper) is getattr(fp, helper)
    assert pos_service.MONEY_QUANTUM == Decimal('0.01')
    assert pos_service.QUANTITY_QUANTUM == Decimal('0.0001')
