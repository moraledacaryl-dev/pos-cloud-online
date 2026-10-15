import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.entities import CatalogItem, SystemSetting
from app.services.selling_rules import resolve_unit_price


@pytest.fixture
def db_session():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def item(price, tags=None, prices=None):
    return CatalogItem(price=Decimal(str(price)), pricing_tags_json=json.dumps(tags or []), conditional_prices_json=json.dumps(prices or []))


def set_rules(db, rules):
    row=SystemSetting(key="catalog_sync",value_json=json.dumps({"pricing_rules":rules}))
    db.add(row); db.commit()


def test_generic_conditional_price_requires_qualifier(db_session):
    target=item(100,["pastry-combo"],[{"rule_id":"r1","price":"95"}])
    qualifier=item(50,["drink-combo"])
    set_rules(db_session,[{"id":"r1","qualifier_tag":"drink-combo","target_tag":"pastry-combo","priority":100}])
    assert resolve_unit_price(db_session,target,[]) == Decimal("100")
    assert resolve_unit_price(db_session,target,[qualifier,target]) == Decimal("95")


def test_generic_conditional_price_uses_lowest_then_priority(db_session):
    target=item(100,["target"],[{"rule_id":"later","price":"90"},{"rule_id":"best","price":"85"},{"rule_id":"tie","price":"85"}])
    qualifier=item(50,["qualifier"])
    set_rules(db_session,[
        {"id":"later","qualifier_tag":"qualifier","target_tag":"target","priority":1},
        {"id":"best","qualifier_tag":"qualifier","target_tag":"target","priority":20},
        {"id":"tie","qualifier_tag":"qualifier","target_tag":"target","priority":30},
    ])
    assert resolve_unit_price(db_session,target,[qualifier,target]) == Decimal("85")
