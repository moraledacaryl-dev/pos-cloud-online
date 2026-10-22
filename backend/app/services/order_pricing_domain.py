"""Validate catalog-defined order modifiers without database side effects.

The POS service remains responsible for locking catalog rows, resolving
conditional prices, and persisting orders.  This module validates untrusted
selection shapes and totals configured modifier deltas using exact Decimals.
"""

from __future__ import annotations

import json
from decimal import Decimal

from app.services.financial_precision import _validated_money


def validated_modifier_total(catalog_name: str, raw_groups: str | None,
                             selections: list[dict] | None) -> Decimal:
    """Return a verified modifier adjustment, rejecting duplicate selections.

    A selected group may occur only once, and an option label may occur only
    once within that group.  This also prevents single-select limits from being
    bypassed by submitting the same group in multiple entries.
    """
    try:
        configured_groups = json.loads(raw_groups or '[]')
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{catalog_name} modifier configuration is invalid.') from exc
    if not isinstance(configured_groups, list):
        raise ValueError(f'{catalog_name} modifier configuration is invalid.')
    if selections is None:
        selections = []
    if not isinstance(selections, list):
        raise ValueError(f'{catalog_name} modifier selections are invalid.')

    groups_by_id = {
        str(group.get('id')): group
        for group in configured_groups
        if isinstance(group, dict) and group.get('id')
    }
    used_groups: set[str] = set()
    total = Decimal('0')
    for selected_group in selections:
        if not isinstance(selected_group, dict):
            raise ValueError(f'{catalog_name} modifier selections are invalid.')
        group_id = str(selected_group.get('id') or '')
        group = groups_by_id.get(group_id)
        if group is None:
            raise ValueError(f'{catalog_name} contains an invalid modifier group.')
        if group_id in used_groups:
            raise ValueError(f'{catalog_name} modifier group is selected more than once.')
        used_groups.add(group_id)

        labels = selected_group.get('labels')
        if labels is None:
            labels = []
        if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
            raise ValueError(f'{catalog_name} modifier labels are invalid.')
        if len(labels) != len(set(labels)):
            raise ValueError(f'{catalog_name} modifier option is selected more than once.')
        if group.get('mode') != 'multi' and len(labels) > 1:
            raise ValueError(f'{catalog_name} modifier allows only one selection.')

        options = group.get('options', [])
        if not isinstance(options, list):
            raise ValueError(f'{catalog_name} modifier configuration is invalid.')
        allowed = {
            str(option.get('label')): option
            for option in options
            if isinstance(option, dict) and option.get('label') is not None
        }
        for label in labels:
            option = allowed.get(label)
            if option is None:
                raise ValueError(f'{catalog_name} contains an invalid modifier option.')
            total += _validated_money(
                option.get('price_delta') or 0,
                f'{catalog_name} modifier adjustment',
                allow_negative=True,
            )
    return total
