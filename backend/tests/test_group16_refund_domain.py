"""Pure refund planning regression tests; no database or external HTTP needed."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.refund_domain import allocate_refund_tenders, prepare_refund_line_plan


def order_line(line_id, qty, total, discount=0):
    return SimpleNamespace(
        id=line_id, quantity=Decimal(str(qty)), line_total=Decimal(str(total)),
        discount_amount=Decimal(str(discount)), unit_price=Decimal("50.00"),
        item_name_snapshot=f"Item {line_id}",
    )


def refund_payload(mode, *, amount=None, lines=None, note="Refund reason"):
    return SimpleNamespace(
        refund_mode=mode, amount=amount, lines=lines or [],
        note=note, reason_text="Guest approved", reason_code="guest_request",
    )


def test_full_refund_prorates_remaining_lines_and_preserves_order_adjustment():
    line = order_line(15, 2, "100.00", "10.00")
    row = SimpleNamespace(lines=[line])
    mode, result_lines, amount = prepare_refund_line_plan(
        row, refund_payload("full"), {15: Decimal("1")},
        Decimal("60.00"),
    )
    assert mode == "full"
    assert amount == Decimal("60.00")
    assert result_lines[0]["order_line_id"] == 15
    assert result_lines[0]["quantity"] == Decimal("1.0000")
    assert result_lines[0]["refunded_line_total"] == Decimal("50.00")
    assert result_lines[0]["discount_amount"] == Decimal("5.00")
    assert result_lines[1]["item_name_snapshot"] == "Order-Level Adjustment"
    assert result_lines[1]["refunded_line_total"] == Decimal("10.00")


def test_line_refund_rejects_quantity_over_original_and_previous_refunds():
    row = SimpleNamespace(lines=[order_line(15, 2, "100.00")])
    requested = [SimpleNamespace(order_line_id=15, quantity=Decimal("1.0001"), note=None)]
    with pytest.raises(ValueError, match="exceeds remaining refundable quantity"):
        prepare_refund_line_plan(row, refund_payload("lines", lines=requested),
                                 {15: Decimal("1.0000")}, Decimal("100.00"))


def test_line_refund_rejects_duplicate_lines_exceeding_remaining_quantity():
    row = SimpleNamespace(lines=[order_line(15, 2, "100.00")])
    requested = [
        SimpleNamespace(order_line_id=15, quantity=Decimal("1.5000"), note=None),
        SimpleNamespace(order_line_id=15, quantity=Decimal("1.0000"), note=None),
    ]
    with pytest.raises(ValueError, match="exceeds remaining refundable quantity"):
        prepare_refund_line_plan(row, refund_payload("lines", lines=requested),
                                 {}, Decimal("100.00"))


def test_amount_refund_uses_exact_money_and_prohibits_over_refund():
    row = SimpleNamespace(lines=[])
    mode, result_lines, amount = prepare_refund_line_plan(
        row, refund_payload("amount", amount=Decimal("25.005")),
        {}, Decimal("50.00"),
    )
    assert mode == "amount"
    assert amount == Decimal("25.01")
    assert result_lines[0]["refunded_line_total"] == Decimal("25.01")
    with pytest.raises(ValueError, match="exceeds remaining refundable balance"):
        prepare_refund_line_plan(
            row, refund_payload("amount", amount=Decimal("50.01")),
            {}, Decimal("50.00"),
        )


def tender(kind, amount, *, reference=None, is_cash=False, account=None, id=1):
    return SimpleNamespace(
        id=id, tender_type=kind, amount_applied=Decimal(str(amount)),
        reference_no=reference, is_cash=is_cash, accounting_financial_account_id=account,
    )


def test_refund_tender_allocation_respects_prior_cash_refunds_and_original_tenders():
    row = SimpleNamespace(
        order_no="POS-15", register=SimpleNamespace(accounting_financial_account_id=8),
        payments=[
            tender("cash", "70.00", is_cash=True),
            tender("gcash", "50.00", reference="GC-15", account=2),
        ],
    )
    paid_out, reversals = allocate_refund_tenders(
        None, row, refund_payload("amount"), Decimal("80.00"),
        {"cash": Decimal("20.00")},
    )
    assert reversals == []
    assert [(x["tender_type"], x["amount"]) for x in paid_out] == [
        ("cash", Decimal("50.00")), ("gcash", Decimal("30.00")),
    ]
    assert paid_out[0]["accounting_financial_account_id"] == 8
    assert paid_out[1]["reference_no"] == "GC-15"


def test_refund_tender_allocation_fails_without_enough_original_money():
    row = SimpleNamespace(
        order_no="POS-15", register=SimpleNamespace(accounting_financial_account_id=8),
        payments=[tender("cash", "10.00", is_cash=True)],
    )
    with pytest.raises(ValueError, match="Unable to allocate refund"):
        allocate_refund_tenders(None, row, refund_payload("amount"), Decimal("11.00"), {})


def test_room_charge_allocation_creates_reversal_instead_of_cash_refund():
    posting = SimpleNamespace(id=115)

    class FakeDb:
        def query(self, model):
            return self

        def filter(self, *args):
            return self

        def first(self):
            return posting

    row = SimpleNamespace(
        order_no="POS-15", register=SimpleNamespace(accounting_financial_account_id=8),
        payments=[
            tender("cash", "40.00", is_cash=True),
            tender("room_charge", "60.00", reference="ROOM-15", id=2),
        ],
    )
    paid_out, reversals = allocate_refund_tenders(
        FakeDb(), row, refund_payload("amount"), Decimal("70.00"), {},
    )
    assert len(paid_out) == 1
    assert paid_out[0]["amount"] == Decimal("40.00")
    assert reversals == [{
        "original_posting_id": 115, "amount": Decimal("30.00"),
        "reason": "Guest approved", "note": "Refund reason",
    }]
