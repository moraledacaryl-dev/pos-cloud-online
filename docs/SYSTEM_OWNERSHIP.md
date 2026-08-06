# Hidden Oasis System Ownership and Handoff Contract

Status: **Pass 1 architecture decision**

This document is the authoritative boundary for POS integrations. It replaces older statements that treated Accounting as the owner of recipes, physical inventory, or POS catalog structure.

## Canonical business flow

```text
Staff identity
  -> POS operational transaction
  -> Inventory physical-stock consequence
  -> Accounting financial consequence

POS room charge
  -> PMS/front desk folio confirmation
  -> Accounting receivable/settlement consequence

Command Center receives exceptions and follow-up work only.
```

## System-of-record matrix

| Domain | System of record | POS responsibility | Handoff completion |
|---|---|---|---|
| Employee identity and employment status | Staff & Payroll | Store the external employee ID and POS authorization | Active identity/role is available to POS |
| Register sessions and drawer actions | POS | Create, control, audit, and close | Session is closed and reconciliation event is queued |
| Orders, tenders, receipts, kitchen state | POS | Full operational ownership | Transaction is final and immutable except through controlled reversal |
| Product/SKU identity | Inventory & Procurement | Maintain a sellable snapshot and POS-only presentation overrides | Snapshot version is imported and mapped |
| Recipes/BOM and physical stock | Inventory & Procurement | Emit finalized-sale and reversal facts; never calculate stock truth | Inventory acknowledges consumption/reversal |
| Inventory valuation and sale cost | Inventory & Procurement | Preserve sale facts and downstream acknowledgement | Cost consequence is emitted to Accounting |
| GL, tax, revenue, cash, receivables and reporting | Accounting | Emit financial transaction facts and retain acknowledgement | Accounting returns a durable posting/reference ID |
| Room/guest folio | PMS/front desk | Create a pending room-charge request and track status | PMS/front desk accepts or rejects the posting |
| Planning, tasks, fixes and exception follow-up | Operations Command Center | Emit only actionable exceptions | Task/exception is accepted by Command Center |

## Catalog boundary

Inventory & Procurement owns:

- global product and SKU identity
- category/master structure
- recipe mapping
- base sellability and stock-related availability
- master price when pricing is centrally governed

Accounting owns:

- tax and financial-account mappings
- financial reporting classifications

POS owns:

- local display name/customer-facing label
- tile order and quick keys
- preparation station and routing override
- temporary sold-out/hidden state
- other local presentation settings

A POS-local item without an external product/SKU ID is an explicit temporary or emergency item. It must not silently become a new master product in another application.

## Event ownership

| Event | Producer | Primary consumer | Required idempotency key | Reversal |
|---|---|---|---|---|
| `order.finalized` | POS | Inventory integration facade | `order_uuid` | `order.voided` or `order.refunded` |
| `inventory.sale_consumed` | Inventory | Accounting | Inventory posting UUID | Inventory correction/reversal event |
| `payment.refunded` | POS | Accounting | `refund-payment:{payment_id}` | Controlled correction only |
| `order.voided` | POS | Inventory, then Accounting | `void:{order_uuid}` | No second void; correction event required |
| `cash_movement.created` | POS | Accounting | `cash_event_uuid` | Opposing controlled movement |
| `session.closed` | POS | Accounting | `session:{session_id}:closed` | Reopen/correction workflow |
| `room_charge.requested` | POS | PMS/front desk | `posting_uuid` | Reject/cancel/adjust workflow |
| `pos.exception.raised` | POS | Command Center | Exception UUID | Resolve/close in Command Center |

## Current transport compatibility

The deployed POS currently uses Accounting endpoints for catalog export and sale transport. During migration, those endpoints may remain as a compatibility facade, but they must route responsibilities according to this contract:

1. Catalog requests return Inventory-owned product/SKU data, even when proxied through Accounting.
2. Finalized-sale requests must reach Inventory exactly once for physical-stock consumption.
3. Accounting receives the financial consequence exactly once and must not independently perform a second stock deduction.
4. Voids and refunds must reverse the same downstream records created by the original event.

The endpoint hostname does not determine business ownership. A temporary Accounting-hosted facade is a transport adapter, not proof that Accounting owns catalog, recipes, or stock.

## Failure and retry rules

- POS records the local transaction before attempting downstream delivery.
- Network or downstream 5xx failures remain retryable in the POS outbox.
- Receivers must return the same successful outcome for a replayed idempotency key without creating duplicates.
- Validation failures are visible as operator-actionable dead-letter events.
- A failed Inventory handoff must not be hidden by a successful Accounting handoff.
- A room charge remains pending until the PMS/front desk explicitly accepts it.

## Prohibited duplicate workflows

- Do not enter a normal POS sale manually in Accounting after it has synced.
- Do not deduct recipe ingredients independently in both Accounting and Inventory.
- Do not create an unrelated POS employee when an active Staff employee identity already exists.
- Do not create routine Command Center tasks for successful sales.
- Do not mark a room charge settled merely because the restaurant order is complete.

## Pass 1 acceptance decision

The final target is:

```text
Staff -> POS -> Inventory -> Accounting
                 \-> PMS for room charges

Command Center <- exceptions only
```

Existing Accounting-hosted endpoints may remain temporarily, but all new integration work must preserve the ownership rules above.
