"""Group 17: safe modifier selection and failure-atomic order edits."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import CatalogItem, Outlet, PosOrder, Register
from app.schemas.common import OrderCreate, OrderUpdate, RegisterSessionOpen
from app.services.order_pricing_domain import validated_modifier_total
from app.services.pos_service import create_order, open_register_session, update_order


GROUPS = [
    {
        'id': 'shot',
        'mode': 'single',
        'options': [{'label': 'Extra shot', 'price_delta': '20'}],
    },
    {
        'id': 'sinkers',
        'mode': 'multi',
        'options': [
            {'label': 'Pearls', 'price_delta': '10'},
            {'label': 'Jelly', 'price_delta': '15'},
        ],
    },
]


def test_modifier_total_accepts_exact_cent_multi_and_single_options():
    selections = [
        {'id': 'shot', 'labels': ['Extra shot']},
        {'id': 'sinkers', 'labels': ['Pearls', 'Jelly']},
    ]
    assert validated_modifier_total('Coffee', json.dumps(GROUPS), selections) == Decimal('45.00')
    assert validated_modifier_total('Coffee', json.dumps(GROUPS), []) == Decimal('0')
    assert validated_modifier_total('Coffee', None, None) == Decimal('0')


@pytest.mark.parametrize(('selections', 'message'), [
    ([{'id': 'shot', 'labels': ['Extra shot']}, {'id': 'shot', 'labels': ['Extra shot']}], 'group is selected more than once'),
    ([{'id': 'sinkers', 'labels': ['Pearls', 'Pearls']}], 'option is selected more than once'),
    ([{'id': 'shot', 'labels': ['Extra shot', 'Extra shot']}], 'option is selected more than once'),
    ([{'id': 'shot', 'labels': ['Extra shot', 'Something']}], 'allows only one selection'),
    ([{'id': 'other', 'labels': []}], 'invalid modifier group'),
    ([{'id': 'sinkers', 'labels': ['Other']}], 'invalid modifier option'),
    ([{'id': 'sinkers', 'labels': 'Pearls'}], 'labels are invalid'),
    ([{'id': 'sinkers', 'labels': [10]}], 'labels are invalid'),
    (['not a selection'], 'selections are invalid'),
])
def test_invalid_modifier_shapes_fail_as_client_errors(selections, message):
    with pytest.raises(ValueError, match=message):
        validated_modifier_total('Coffee', json.dumps(GROUPS), selections)


@pytest.mark.parametrize('raw', ['{broken', '{}', 'false'])
def test_invalid_config_is_not_silently_accepted(raw):
    with pytest.raises(ValueError, match='configuration is invalid'):
        validated_modifier_total('Coffee', raw, [])


def test_nonfinite_modifier_amount_is_rejected():
    groups = [{'id': 'shot', 'mode': 'single', 'options': [{'label': 'Bad', 'price_delta': 'NaN'}]}]
    with pytest.raises(ValueError, match='finite'):
        validated_modifier_total('Coffee', json.dumps(groups), [{'id': 'shot', 'labels': ['Bad']}])


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, future=True)
    with Session() as session:
        yield session
    engine.dispose()


def _order_context(db):
    outlet = Outlet(code='CAFE', name='Cafe', business_unit='F&B', is_active=True)
    db.add(outlet)
    db.flush()
    register = Register(
        outlet_id=outlet.id, code='MAIN', name='Main',
        accounting_financial_account_id=1, accounting_financial_account_code='CASH-CAFE',
        is_active=True,
    )
    db.add(register)
    item = CatalogItem(
        menu_item_name='Coffee', display_name='Coffee', category_name='Drinks',
        module_slug='cafe', prep_station='bar', price=Decimal('100'),
        modifier_groups_json=json.dumps(GROUPS), is_active=True, is_available=True,
    )
    db.add(item)
    db.commit()
    session = open_register_session(db, RegisterSessionOpen(
        register_id=register.id, business_date='2026-04-19',
        shift_name='AM', opening_float=0,
    ))
    return item.id, session['id']


def test_modifier_price_is_server_authoritative_at_checkout(db):
    item_id, session_id = _order_context(db)
    selected = [{'id': 'shot', 'labels': ['Extra shot']}]
    order = create_order(db, OrderCreate(register_session_id=session_id, lines=[
        {'catalog_item_id': item_id, 'quantity': 2, 'unit_price': 120, 'modifiers': selected},
    ]))
    assert Decimal(str(order['total_amount'])) == Decimal('240.00')
    with pytest.raises(ValueError, match='price does not match'):
        create_order(db, OrderCreate(register_session_id=session_id, lines=[
            {'catalog_item_id': item_id, 'quantity': 1, 'unit_price': 100, 'modifiers': selected},
        ]))
    db.rollback()


def test_rejected_modifier_edit_keeps_original_lines_and_totals_before_rollback(db):
    item_id, session_id = _order_context(db)
    order = create_order(db, OrderCreate(register_session_id=session_id, lines=[
        {'catalog_item_id': item_id, 'quantity': 1, 'unit_price': 100},
    ]))
    original_row = db.get(PosOrder, order['id'])
    original_line_id = original_row.lines[0].id

    # A valid first line followed by an invalid second line must not erase or
    # stage replacements for the original lines, even before caller rollback.
    with pytest.raises(ValueError, match='option is selected more than once'):
        update_order(db, order['id'], OrderUpdate(lines=[
            {'catalog_item_id': item_id, 'quantity': 2, 'unit_price': 100},
            {'catalog_item_id': item_id, 'quantity': 1, 'unit_price': 120,
             'modifiers': [{'id': 'sinkers', 'labels': ['Pearls', 'Pearls']}]},
        ]))
    assert [line.id for line in original_row.lines] == [original_line_id]
    assert original_row.lines[0].quantity == Decimal('1.0000')
    assert Decimal(str(original_row.total_amount)) == Decimal('100.00')
    db.rollback()
    persisted = db.get(PosOrder, order['id'])
    assert [line.id for line in persisted.lines] == [original_line_id]
    assert Decimal(str(persisted.total_amount)) == Decimal('100.00')
