from __future__ import annotations

KNOWN_ORDER_STATES = {
    'draft', 'held', 'open', 'sent', 'served', 'unpaid',
    'paid', 'folio_pending', 'voided', 'cancelled', 'refunded',
    'merged', 'closed',
}

TERMINAL_ORDER_STATES = {'voided', 'cancelled', 'merged', 'closed'}
EDITABLE_ORDER_STATES = {'draft', 'held', 'open', 'sent', 'served', 'unpaid'}
PAYABLE_ORDER_STATES = {'draft', 'held', 'open', 'sent', 'served', 'unpaid'}
REFUNDABLE_ORDER_STATES = {'paid', 'folio_pending', 'refunded'}
VOIDABLE_ORDER_STATES = EDITABLE_ORDER_STATES | {'paid', 'folio_pending'}
TABLE_MUTABLE_ORDER_STATES = {'draft', 'held', 'open', 'sent', 'served', 'unpaid'}

ACTION_STATES = {
    'edit': EDITABLE_ORDER_STATES,
    'hold': {'draft', 'open', 'sent', 'served', 'unpaid'},
    'resume': {'held'},
    'pay': PAYABLE_ORDER_STATES,
    'void': VOIDABLE_ORDER_STATES,
    'refund': REFUNDABLE_ORDER_STATES,
    'transfer_table': TABLE_MUTABLE_ORDER_STATES,
    'merge_table': TABLE_MUTABLE_ORDER_STATES,
}


def normalize_order_state(value: str | None) -> str:
    return str(value or '').strip().lower()


def allowed_actions(state: str | None) -> list[str]:
    normalized = normalize_order_state(state)
    return sorted(action for action, states in ACTION_STATES.items() if normalized in states)


def assert_order_action(state: str | None, action: str) -> None:
    normalized_state = normalize_order_state(state)
    normalized_action = str(action or '').strip().lower()
    if normalized_state not in KNOWN_ORDER_STATES:
        raise ValueError(f'Unknown order state: {normalized_state or "blank"}.')
    states = ACTION_STATES.get(normalized_action)
    if states is None:
        raise ValueError(f'Unknown order action: {normalized_action or "blank"}.')
    if normalized_state not in states:
        raise ValueError(
            f'Order action {normalized_action} is not allowed while the order is {normalized_state}. '
            f'Allowed actions: {", ".join(allowed_actions(normalized_state)) or "none"}.'
        )


def policy_snapshot() -> dict:
    return {
        'known_states': sorted(KNOWN_ORDER_STATES),
        'terminal_states': sorted(TERMINAL_ORDER_STATES),
        'actions': {action: sorted(states) for action, states in ACTION_STATES.items()},
    }
