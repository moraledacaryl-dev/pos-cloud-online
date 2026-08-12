# Pass 9 — Room-charge settlement integrity

## Goal

Keep the POS room-charge queue operationally useful while preventing front-desk actions from creating ambiguous or unauditable final states.

## Rules added

- A charge cannot be marked `posted_to_beds24` without a Beds24 posting reference.
- A rejected charge requires a rejection reason.
- A disputed charge requires a dispute note.
- A written-off charge requires a clear note in addition to the existing manager-approval requirement.
- A charge cannot be marked `settled_at_frontdesk` without a Beds24 posting reference.
- A charge disputed before any posting confirmation cannot jump directly to settlement.
- Front-desk settlement uses the canonical `later_payment_status=settled` value.
- Final states (`settled_at_frontdesk`, `written_off`, `rejected`, `cancelled`) are immutable through the ordinary status-update endpoint. Corrections must use an explicit corrective workflow rather than silently rewriting history.

## Existing controls retained

The existing transition graph remains authoritative. Disputes and write-offs continue to require manager approval. The service continues to record posting, settlement, rejection, dispute, write-off, and dispute-resolution audit events.

## Deployment

No schema migration is required. Deploy the backend code and restart `pos-backend`. Restarting the frontend and sync worker is optional for code-version consistency but not required by the policy itself.
