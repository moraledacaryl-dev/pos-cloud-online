# POS Cloud Architecture

## Goal
This application is the fast operational selling layer for the restaurant and café. It deliberately keeps recipes, physical-stock truth, inventory valuation, and accounting journals out of the cashier workflow. Finalized transaction facts flow to Inventory & Procurement for stock consequences and then to Accounting for financial consequences. Existing Accounting-hosted endpoints remain a compatibility transport during migration.

## Core boundaries

### POS owns
- live catalog snapshot for selling
- register sessions and drawer control
- draft, held, paid, and void orders
- split tenders
- kitchen and prep routing
- paid in / paid out drawer events
- outbox-based downstream sync

### Inventory & Procurement owns
- product/SKU master identity and category structure
- recipe/BOM lines and physical-stock deduction
- lot/FIFO consumption and inventory valuation
- POS product mappings and stock reversals

### Accounting owns
- tax and financial-account mappings
- treasury and receivables truth
- journal posting and financial reconciliation
- statutory and management reporting

### Staff & Payroll owns
- employee identity, employment status, schedules, attendance, and payroll

### Operations Command Center owns
- planning, assignments, fixes, approvals, and exception follow-up

## Key models
- `Outlet`: selling location
- `Register`: physical or logical drawer
- `RegisterSession`: one shift under one drawer
- `CatalogItem`: sellable local snapshot mapped to external product / SKU IDs
- `PosOrder`: ticket-level transaction
- `PosOrderLine`: sellable lines with station and external IDs
- `PosOrderPayment`: split tender settlement
- `CashMovement`: every physical drawer movement
- `SyncOutboxEvent`: reliable integration queue

## Sync strategy
The POS never writes directly into another application's database. It records locally first, then pushes outbound events through an outbox.

### Event types
- `order.finalized` -> Inventory integration facade
- `order.voided` -> Inventory reversal, then Accounting reversal
- `payment.refunded` -> Accounting refund and Inventory reversal when applicable
- `cash_movement.created` -> Accounting
- `session.closed` -> Accounting reconciliation
- `room_charge.requested` -> PMS/front desk
- `pos.exception.raised` -> Operations Command Center

### Why the outbox matters
- no lost sales if a downstream system is temporarily unavailable
- retry-safe pushes with idempotency keys
- operational speed for cashiers even while sync is delayed

## Drawer logic
Expected drawer cash is calculated from session cash movements:
- opening float
- cash sales
- paid in
- paid out
- refunds
- safe drops
- owner withdrawals
- adjustments

At close, actual counted cash is stored, variance is calculated, and a reconciliation payload is prepared for Accounting.

## Catalog strategy
The POS does not own recipes or product-master truth. It imports an Inventory-owned sellable snapshot, currently through Accounting-hosted compatibility endpoints, using external identifiers:
- `external_menu_item_id`
- `external_sku_id`

Those identifiers are sent with finalized sales so Inventory can deduct ingredients exactly once using the authoritative recipe and stock ledger. Accounting receives the resulting financial consequence and must not perform a second stock deduction. See `SYSTEM_OWNERSHIP.md`.
