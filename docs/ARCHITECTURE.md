# POS Cloud Architecture

## Goal
This application is the fast operational selling layer for the restaurant and café. It deliberately keeps recipes, FIFO, deep inventory valuation, and accounting journals out of the cashier workflow, while still syncing every financial event back into the accounting system.

## Core boundaries

### POS owns
- live catalog snapshot for selling
- register sessions and drawer control
- draft, held, paid, and void orders
- split tenders
- kitchen and prep routing
- paid in / paid out drawer events
- outbox-based accounting sync

### Accounting system owns
- menu master data truth
- recipe lines and inventory deduction
- FIFO consumption and stock valuation
- treasury truth for financial accounts
- reconciliation truth
- accounting and reporting

## Key models
- `Outlet`: selling location
- `Register`: physical or logical drawer
- `RegisterSession`: one shift under one drawer
- `CatalogItem`: sellable local snapshot mapped to accounting menu item / sku IDs
- `PosOrder`: ticket-level transaction
- `PosOrderLine`: sellable lines with station and external IDs
- `PosOrderPayment`: split tender settlement
- `CashMovement`: every physical drawer movement
- `SyncOutboxEvent`: reliable integration queue

## Sync strategy
The POS never writes directly into the accounting database. It records locally first, then pushes outbound events through an outbox.

### Event types
- `order.finalized`
- `cash_movement.created`
- `session.closed`

### Why the outbox matters
- no lost sales if accounting is temporarily unavailable
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

At close, actual counted cash is stored, variance is calculated, and a reconciliation payload is prepared for accounting.

## Catalog strategy
The POS does not own recipes. It imports sellable items from accounting using external identifiers:
- `external_menu_item_id`
- `external_sku_id`

Those identifiers are sent back when the POS syncs finalized sales, allowing accounting to deduct ingredients using its own recipe engine.
