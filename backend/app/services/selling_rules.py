from __future__ import annotations

import json
from decimal import Decimal

from app.models.entities import CatalogItem
from app.services.pos_service import setting_json


def _json_list(raw):
    try:
        value=json.loads(raw or "[]")
        return value if isinstance(value,list) else []
    except Exception:
        return []

def pricing_tags(item:CatalogItem)->set[str]:
    return {str(x).strip() for x in _json_list(item.pricing_tags_json) if str(x).strip()}

def conditional_prices(item:CatalogItem)->list[dict]:
    return [x for x in _json_list(item.conditional_prices_json) if isinstance(x,dict)]

def resolve_unit_price(db,item:CatalogItem,cart_items:list[CatalogItem])->Decimal:
    """Server-authoritative generic price. Lowest price wins; priority then rule id make ties deterministic."""
    regular=Decimal(str(item.price))
    meta=setting_json(db,'catalog_sync',default={}) or {}
    rules=meta.get('pricing_rules') or []
    cart_tags=set()
    for cart_item in cart_items:
        cart_tags.update(pricing_tags(cart_item))
    by_id={str(r.get('id')):r for r in rules if isinstance(r,dict) and r.get('id')}
    candidates=[]
    target_tags=pricing_tags(item)
    for cp in conditional_prices(item):
        rule=by_id.get(str(cp.get('rule_id')))
        if not rule or rule.get('is_active', True) is False or str(rule.get('target_tag') or '') not in target_tags or str(rule.get('qualifier_tag') or '') not in cart_tags:
            continue
        try: price=Decimal(str(cp.get('price')))
        except Exception: continue
        if not price.is_finite() or price < 0:
            continue
        candidates.append((price,int(rule.get('priority') or 100),str(rule.get('id')),price))
    return min(candidates,key=lambda x:(x[0],x[1],x[2]))[3] if candidates else regular
