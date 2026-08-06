import pytest

from app.services.order_state_policy import allowed_actions, assert_order_action, policy_snapshot


def test_draft_order_supports_normal_cashier_actions():
    actions = allowed_actions('draft')
    assert {'edit', 'hold', 'pay', 'void', 'transfer_table', 'merge_table'} <= set(actions)


def test_held_order_can_resume_or_pay_but_cannot_be_held_again():
    assert_order_action('held', 'resume')
    assert_order_action('held', 'pay')
    with pytest.raises(ValueError, match='not allowed'):
        assert_order_action('held', 'hold')


def test_paid_order_is_immutable_except_refund_or_void():
    assert allowed_actions('paid') == ['refund', 'void']
    with pytest.raises(ValueError, match='not allowed'):
        assert_order_action('paid', 'edit')
    with pytest.raises(ValueError, match='not allowed'):
        assert_order_action('paid', 'pay')


def test_terminal_orders_have_no_actions():
    for state in ('voided', 'cancelled', 'merged', 'closed'):
        assert allowed_actions(state) == []


def test_policy_snapshot_is_machine_readable():
    snapshot = policy_snapshot()
    assert 'paid' in snapshot['known_states']
    assert 'voided' in snapshot['terminal_states']
    assert snapshot['actions']['refund'] == ['folio_pending', 'paid', 'refunded']
