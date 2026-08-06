# Pass 4 — Payment and Cash Controls

## Scope

This pass adds fail-fast controls before existing settlement and drawer-movement service logic runs.

## Payment rules

- The order must still be payment-eligible.
- Payment lines must exactly equal the order total.
- Applied amounts must be positive and finite.
- Cash received cannot be less than cash applied.
- Non-cash received amounts must equal applied amounts.
- GCash, card, and bank-transfer tenders require transaction references.
- Duplicate tender references within one payment are rejected.
- Room charges require a selected booking snapshot or room number.

## Cash movement rules

- Amounts must be positive and finite.
- Movement direction must match the movement type.
- Sensitive cash-out movements require a reason note, reference number, and manager approval.

Sensitive cash-out types are:

- paid out
- safe drop
- owner withdrawal
- adjustment out

## Defense in depth

The API policy validates before mutation. Existing service-level validation, permission checks, manager approvals, audit records, and accounting outbox behavior remain authoritative and continue to run.

## Deployment

No database migration and no frontend build are required. Restart the POS backend after pulling the merged commit.
