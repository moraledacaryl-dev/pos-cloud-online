from __future__ import annotations

TERMINAL_ROOM_CHARGE_STATUSES = {
    'settled_at_frontdesk',
    'written_off',
    'rejected',
    'cancelled',
}


def _clean(value) -> str:
    return str(value or '').strip()


def validate_room_charge_status_update(current: dict, payload) -> None:
    """Fail fast on status updates that would destroy front-desk traceability.

    The state-transition graph remains owned by the POS service. This policy adds
    evidence requirements for financially meaningful room-charge outcomes.
    """
    current_status = _clean(current.get('posting_status')).lower().replace(' ', '_')
    target_status = _clean(getattr(payload, 'posting_status', None)).lower().replace(' ', '_')

    if current_status in TERMINAL_ROOM_CHARGE_STATUSES and target_status == current_status:
        raise ValueError('Finalized room-charge records are immutable. Create a corrective workflow instead of editing the final record.')

    reference = _clean(getattr(payload, 'beds24_posting_reference', None)) or _clean(current.get('beds24_posting_reference'))
    rejected_reason = _clean(getattr(payload, 'rejected_reason', None)) or _clean(current.get('rejected_reason'))
    dispute_note = _clean(getattr(payload, 'dispute_note', None)) or _clean(current.get('dispute_note'))
    note = _clean(getattr(payload, 'note', None)) or _clean(current.get('note'))

    if target_status == 'posted_to_beds24' and not reference:
        raise ValueError('Beds24 posting reference is required before a room charge can be marked posted.')

    if target_status == 'rejected' and not rejected_reason:
        raise ValueError('Rejected room charges require a rejection reason.')

    if target_status == 'disputed' and not dispute_note:
        raise ValueError('Disputed room charges require a dispute note.')

    if target_status == 'written_off' and not note:
        raise ValueError('Written-off room charges require a clear write-off note.')

    if target_status == 'settled_at_frontdesk':
        if not reference:
            raise ValueError('A room charge cannot be settled without a Beds24 posting reference.')
        if current_status == 'disputed' and not _clean(current.get('posted_to_beds24_at')):
            raise ValueError('A disputed charge that was never confirmed posted cannot be settled. Resolve it through rejection/write-off or confirm posting first.')
        later_payment_status = _clean(getattr(payload, 'later_payment_status', None))
        if later_payment_status and later_payment_status.lower() != 'settled':
            raise ValueError('Front-desk settlement must use later_payment_status="settled".')
