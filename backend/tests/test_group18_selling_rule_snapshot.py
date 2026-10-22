"""Group 18: single-snapshot pricing and poisoned-rule resilience."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.entities import CatalogItem, Outlet, Register, SystemSetting
from app.schemas.common import OrderCreate, RegisterSessionOpen
from app.services.pos_service import create_order, open_register_session
from app.services.selling_rules import resolve_unit_price, resolve_unit_price_from_rules


@pytest.fixture
def db():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _item(price, *, tags=None, prices=None, role=None):
    return CatalogItem(
        menu_item_name='Cafe item', display_name='Cafe item',
        category_name='Cafe', module_slug='cafe', prep_station='bar',
        price=Decimal(str(price)), pricing_role=role,
        pricing_tags_json=json.dumps(tags or []),
        conditional_prices_json=json.dumps(prices or []),
        is_active=True, is_available=True,
    )


def test_pure_resolver_matches_legacy_wrapper(db):
    target = _item(100, tags=['target'], prices=[{'rule_id': 'combo', 'price': '75'}])
    drink = _item(50, tags=['drink'], role='drink')
    rules = [{'id': 'combo', 'qualifier_tag': 'drink', 'target_tag': 'target', 'priority': 2}]
    db.add(SystemSetting(key='catalog_sync', value_json=json.dumps({'pricing_rules': rules})))
    db.commit()
    assert resolve_unit_price(db, target, [target, drink]) == Decimal('75')
    assert resolve_unit_price_from_rules(target, [target, drink], rules) == Decimal('75')
    assert resolve_unit_price(db, target, [target, drink], rules=rules) == Decimal('75')


@pytest.mark.parametrize('snapshot', ['{bad', '[]', '{"pricing_rules":"bad"}', 'null'])
def test_invalid_persisted_rule_snapshots_use_regular_price(db, snapshot):
    target = _item(100, tags=['target'], prices=[{'rule_id': 'combo', 'price': '75'}])
    drink = _item(50, tags=['drink'])
    db.add(SystemSetting(key='catalog_sync', value_json=snapshot))
    db.commit()
    assert resolve_unit_price(db, target, [target, drink]) == Decimal('100')


@pytest.mark.parametrize('priority', ['invalid', {}, 'NaN', None])
def test_poisoned_priority_does_not_abort_otherwise_valid_selling_rule(priority):
    target = _item(100, tags=['target'], prices=[{'rule_id': 'combo', 'price': '75'}])
    drink = _item(50, tags=['drink'])
    rules = [{'id': 'combo', 'qualifier_tag': 'drink', 'target_tag': 'target', 'priority': priority}]
    assert resolve_unit_price_from_rules(target, [target, drink], rules) == Decimal('75')


def test_invalid_candidate_price_skipped_without_affecting_valid_candidate():
    target = _item(100, tags=['target'], prices=[
        {'rule_id': 'bad', 'price': 'NaN'},
        {'rule_id': 'good', 'price': '90'},
        {'rule_id': 'bad', 'price': '-5'},
    ])
    drink = _item(50, tags=['drink'])
    rules = [
        {'id': 'bad', 'qualifier_tag': 'drink', 'target_tag': 'target'},
        {'id': 'good', 'qualifier_tag': 'drink', 'target_tag': 'target'},
    ]
    assert resolve_unit_price_from_rules(target, [target, drink], rules) == Decimal('90')


def test_generic_checkout_reads_config_once_for_multiple_targets(db):
    outlet = Outlet(code='CAFE', name='Cafe', business_unit='F&B', is_active=True)
    db.add(outlet)
    db.flush()
    register = Register(
        outlet_id=outlet.id, code='CASH', name='Drawer',
        accounting_financial_account_id=1,
        accounting_financial_account_code='CASH-CAFE', is_active=True,
    )
    db.add(register)
    drink = _item(50, tags=['qualifier'], role='drink')
    pastry_one = _item(100, tags=['target'], prices=[{'rule_id': 'combo', 'price': '80'}])
    pastry_two = _item(110, tags=['target'], prices=[{'rule_id': 'combo', 'price': '90'}])
    db.add_all([drink, pastry_one, pastry_two])
    db.add(SystemSetting(key='catalog_sync', value_json=json.dumps({
        'pricing_rules': [{'id': 'combo', 'qualifier_tag': 'qualifier', 'target_tag': 'target'}],
    })))
    db.commit()
    session = open_register_session(db, RegisterSessionOpen(
        register_id=register.id, business_date='2026-04-19',
        shift_name='AM', opening_float=0,
    ))

    reads = []
    def count_config_reads(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith('select') and 'system_settings' in statement.lower():
            reads.append(statement)

    event.listen(db.bind, 'before_cursor_execute', count_config_reads)
    try:
        result = create_order(db, OrderCreate(register_session_id=session['id'], lines=[
            {'catalog_item_id': drink.id, 'quantity': 1, 'unit_price': 50},
            {'catalog_item_id': pastry_one.id, 'quantity': 1, 'unit_price': 80},
            {'catalog_item_id': pastry_two.id, 'quantity': 1, 'unit_price': 90},
        ]))
    finally:
        event.remove(db.bind, 'before_cursor_execute', count_config_reads)

    assert Decimal(str(result['total_amount'])) == Decimal('220.00')
    assert len(reads) == 1
