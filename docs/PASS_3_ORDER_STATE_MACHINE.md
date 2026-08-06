# Pass 3 — Order State Machine

## Purpose

This pass replaces scattered API assumptions with one explicit order-action policy.

## Operational states

Editable/payable states:

- `draft`
- `held`
- `open`
- `sent`
- `served`
- `unpaid`

Financially finalized states:

- `paid`
- `folio_pending`
- `refunded`

Terminal states:

- `voided`
- `cancelled`
- `merged`
- `closed`

## Enforced rules

- Only active orders can be edited, paid, transferred, or merged.
- Only a held order can be resumed.
- An order cannot be held twice.
- Paid and folio-pending orders cannot be edited or paid again.
- Paid and folio-pending orders may still enter the controlled void or refund workflows.
- Terminal orders accept no cashier actions.
- Unknown states and unknown actions fail closed.

The existing service-level financial, approval, payment, table, and refund validations remain in place. This policy is an additional gate rather than a replacement.

## API

`GET /api/orders/state-policy` returns the machine-readable policy for diagnostics and future UI action gating.

## Deployment

No database migration or frontend build is required. Restart the POS backend after pulling the merged commit.
