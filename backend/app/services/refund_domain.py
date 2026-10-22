"""Pure refund calculations and tender allocation for POS settlement.

The caller holds a lock on the paid order and owns the transaction.
These helpers only derive a refund plan; they never commit, write or dispatch.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.entities import RoomChargePosting
from app.services.financial_precision import MONEY_QUANTUM, _money, _quantity


def prepare_refund_line_plan(row, payload, refunded_qty_by_line: dict[int, Decimal],
                             refundable_remaining: Decimal) -> tuple[str, list[dict], Decimal]:
    """Keep line/amount/full refund computations consistent across entry points."""
    refund_mode = (payload.refund_mode or 'full').strip().lower()
    refund_lines_payload = []
    refund_amount = Decimal('0')

    if refund_mode == 'full':
        line_total_accum = Decimal('0')
        for line in (row.lines or []):
            already_qty = _quantity(refunded_qty_by_line.get(line.id, Decimal('0')))
            remaining_qty = _quantity(max(_quantity(line.quantity) - already_qty, Decimal('0')))
            if remaining_qty <= 0:
                continue
            source_quantity = _quantity(line.quantity)
            ratio = remaining_qty / (source_quantity or Decimal('1'))
            line_total = _money(_money(line.line_total) * ratio)
            refund_lines_payload.append({
                'order_line_id': line.id,
                'item_name_snapshot': line.item_name_snapshot,
                'quantity': remaining_qty,
                'unit_price': line.unit_price,
                'discount_amount': _money(_money(line.discount_amount) * ratio),
                'refunded_line_total': line_total,
                'note': payload.note,
            })
            line_total_accum += line_total
        refund_amount = _money(refundable_remaining)
        remainder = _money(refund_amount - _money(line_total_accum))
        if abs(remainder) >= MONEY_QUANTUM:
            refund_lines_payload.append({
                'order_line_id': None,
                'item_name_snapshot': 'Order-Level Adjustment',
                'quantity': Decimal('1'),
                'unit_price': remainder,
                'discount_amount': Decimal('0'),
                'refunded_line_total': remainder,
                'note': 'Taxes / service charge / rounding',
            })
    elif refund_mode == 'lines':
        if not payload.lines:
            raise ValueError('Refund by line requires at least one refund line.')
        requested_qty_by_line = dict(refunded_qty_by_line)
        for req in payload.lines:
            if not req.order_line_id:
                raise ValueError('Refund line requires order_line_id.')
            source_line = next((line for line in (row.lines or []) if line.id == int(req.order_line_id)), None)
            if not source_line:
                raise ValueError(f'Order line {req.order_line_id} not found.')
            requested_qty = _quantity(req.quantity)
            if requested_qty <= 0:
                raise ValueError('Refund line quantity must be greater than zero.')
            already_qty = _quantity(requested_qty_by_line.get(source_line.id, Decimal('0')))
            remaining_qty = _quantity(max(_quantity(source_line.quantity) - already_qty, Decimal('0')))
            if requested_qty > remaining_qty:
                raise ValueError(f'Refund quantity exceeds remaining refundable quantity for {source_line.item_name_snapshot}.')
            # Include earlier lines in this same request, not just prior refunds.
            requested_qty_by_line[source_line.id] = _quantity(already_qty + requested_qty)
            source_quantity = _quantity(source_line.quantity)
            ratio = requested_qty / (source_quantity or Decimal('1'))
            line_total = _money(_money(source_line.line_total) * ratio)
            refund_lines_payload.append({
                'order_line_id': source_line.id,
                'item_name_snapshot': source_line.item_name_snapshot,
                'quantity': requested_qty,
                'unit_price': source_line.unit_price,
                'discount_amount': _money(_money(source_line.discount_amount) * ratio),
                'refunded_line_total': line_total,
                'note': req.note or payload.note,
            })
            refund_amount += line_total
        refund_amount = _money(refund_amount)
    elif refund_mode == 'amount':
        refund_amount = _money(payload.amount)
        if refund_amount <= 0:
            raise ValueError('Refund amount must be greater than zero.')
        if refund_amount - refundable_remaining >= MONEY_QUANTUM:
            raise ValueError('Refund amount exceeds remaining refundable balance.')
        refund_lines_payload.append({
            'order_line_id': None,
            'item_name_snapshot': 'Amount Refund',
            'quantity': Decimal('1'),
            'unit_price': refund_amount,
            'discount_amount': Decimal('0'),
            'refunded_line_total': refund_amount,
            'note': payload.note or payload.reason_text,
        })
    else:
        raise ValueError('refund_mode must be one of: full, lines, amount.')

    refund_amount = _money(refund_amount)
    if refund_amount <= 0:
        raise ValueError('Refund amount must be greater than zero.')
    if refund_amount - refundable_remaining >= MONEY_QUANTUM:
        raise ValueError('Refund exceeds remaining refundable balance.')
    return refund_mode, refund_lines_payload, refund_amount


def allocate_refund_tenders(db: Session, row, payload, refund_amount: Decimal,
                            refunded_tender_by_type: dict[str, Decimal]) -> tuple[list[dict], list[dict]]:
    """Allocate an approved amount to original tenders, respecting previous refunds."""
    allocations = []
    room_charge_reversals = []
    remaining_to_allocate = refund_amount
    for payment in (row.payments or []):
        tender = (payment.tender_type or '').strip().lower()
        remaining_for_tender = _money(
            _money(payment.amount_applied) - refunded_tender_by_type.get(tender, Decimal('0'))
        )
        if remaining_for_tender <= 0:
            continue
        alloc = _money(min(remaining_for_tender, remaining_to_allocate))
        if alloc <= 0:
            continue
        
        if tender == 'room_charge':
            # For room charges, create reversal posting instead of refund payment
            original_posting = db.query(RoomChargePosting).filter(RoomChargePosting.order_payment_id == payment.id).first()
            if not original_posting:
                raise ValueError('Room charge posting not found for refund allocation.')
            room_charge_reversals.append({
                'original_posting_id': original_posting.id,
                'amount': alloc,
                'reason': payload.reason_text or payload.reason_code or 'Refund',
                'note': payload.note,
            })
        else:
            allocations.append({
                'tender_type': tender,
                'amount': alloc,
                'reference_no': payment.reference_no,
                'note': f'Refund for {row.order_no}',
                'is_cash': bool(payment.is_cash),
                'accounting_financial_account_id': payment.accounting_financial_account_id or (row.register.accounting_financial_account_id if payment.is_cash else None),
            })
        
        remaining_to_allocate = _money(remaining_to_allocate - alloc)
        if remaining_to_allocate < MONEY_QUANTUM:
            break
    if remaining_to_allocate >= MONEY_QUANTUM:
        raise ValueError('Unable to allocate refund across original payment tenders.')
    return allocations, room_charge_reversals
