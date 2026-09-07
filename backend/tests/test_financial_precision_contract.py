from decimal import Decimal

from sqlalchemy import Numeric

from app.models.entities import CatalogItem, PosOrder, PosOrderLine, PosOrderPayment, Refund, RegisterSession
from app.services.pos_service import _money


def test_all_critical_financial_columns_use_exact_numeric_storage():
    columns = [
        CatalogItem.__table__.c.price,
        PosOrder.__table__.c.subtotal_amount,
        PosOrder.__table__.c.discount_amount,
        PosOrder.__table__.c.tax_amount,
        PosOrder.__table__.c.service_charge_amount,
        PosOrder.__table__.c.total_amount,
        PosOrder.__table__.c.paid_amount,
        PosOrder.__table__.c.balance_due,
        PosOrderLine.__table__.c.unit_price,
        PosOrderLine.__table__.c.line_total,
        PosOrderPayment.__table__.c.amount_applied,
        RegisterSession.__table__.c.opening_float,
        RegisterSession.__table__.c.closing_actual_cash,
        Refund.__table__.c.refunded_amount,
    ]
    assert all(isinstance(column.type, Numeric) for column in columns)


def test_money_rounding_is_decimal_and_half_up():
    assert _money('0.1') + _money('0.2') == Decimal('0.30')
    assert _money('1.005') == Decimal('1.01')


def test_database_prevents_two_open_sessions_per_register():
    index = next(index for index in RegisterSession.__table__.indexes if index.name == 'uq_register_sessions_one_open')
    assert index.unique is True
    assert str(index.dialect_options['postgresql']['where']) == 'status = \'open\''
