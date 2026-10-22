"""Authoritative POS conditional pricing for Inventory-owned catalog snapshots.

Pure candidate selection is separate from database configuration reads, so one
checkout can evaluate every line against the same pricing-rule snapshot.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation

from app.models.entities import CatalogItem, SystemSetting


def _json_list(raw):
    try:
        value = json.loads(raw or '[]')
        return value if isinstance(value, list) else []
    except (TypeError, ValueError):
        return []


def pricing_tags(item: CatalogItem) -> set[str]:
    return {str(tag).strip() for tag in _json_list(item.pricing_tags_json) if str(tag).strip()}


def conditional_prices(item: CatalogItem) -> list[dict]:
    return [entry for entry in _json_list(item.conditional_prices_json) if isinstance(entry, dict)]


def _load_pricing_rules(db) -> list[dict]:
    """Read a legacy consumer's pricing snapshot without importing POS service."""
    row = db.query(SystemSetting).filter(SystemSetting.key == 'catalog_sync').first()
    if row is None:
        return []
    try:
        snapshot = json.loads(row.value_json or '{}')
    except (TypeError, ValueError):
        return []
    if not isinstance(snapshot, dict):
        return []
    rules = snapshot.get('pricing_rules')
    return rules if isinstance(rules, list) else []


def _priority(rule: dict) -> int:
    try:
        return int(rule.get('priority') or 100)
    except (TypeError, ValueError, OverflowError):
        return 100


def resolve_unit_price_from_rules(
    item: CatalogItem, cart_items: list[CatalogItem], rules: list[dict] | None,
) -> Decimal:
    """Select the lowest qualified finite nonnegative price deterministically."""
    regular = Decimal(str(item.price))
    cart_tags: set[str] = set()
    for cart_item in cart_items:
        cart_tags.update(pricing_tags(cart_item))
    target_tags = pricing_tags(item)

    by_id = {
        str(rule['id']): rule
        for rule in (rules if isinstance(rules, list) else [])
        if isinstance(rule, dict) and rule.get('id')
    }
    candidates: list[tuple[Decimal, int, str]] = []
    for candidate in conditional_prices(item):
        rule = by_id.get(str(candidate.get('rule_id')))
        if not rule or rule.get('is_active', True) is False:
            continue
        if str(rule.get('target_tag') or '') not in target_tags:
            continue
        if str(rule.get('qualifier_tag') or '') not in cart_tags:
            continue
        try:
            price = Decimal(str(candidate.get('price')))
        except (TypeError, ValueError, InvalidOperation):
            continue
        if not price.is_finite() or price < 0:
            continue
        candidates.append((price, _priority(rule), str(rule['id'])))
    return min(candidates)[0] if candidates else regular


def resolve_unit_price(
    db, item: CatalogItem, cart_items: list[CatalogItem],
    *, rules: list[dict] | None = None,
) -> Decimal:
    """Compatible wrapper; pass rules to avoid per-item configuration queries."""
    return resolve_unit_price_from_rules(
        item, cart_items, _load_pricing_rules(db) if rules is None else rules,
    )
