# POS Blueprint Matching the Current Accounting Codebase

This blueprint is based on the current attached accounting project structure:
- FastAPI backend
- Next.js 14 frontend (App Router, JS)
- SQLAlchemy models and service-layer business logic
- Existing treasury models: `FinancialAccount`, `MoneyTransaction`, `AccountTransfer`, `CashReconciliation`
- Existing restaurant models: `MenuItem`, `MenuSKU`, `SaleOrder`, `SaleOrderLine`

## Core boundary

POS should own:
- order flow
- cart
- register session
- cashier actions
- payments
- cash drawer movements
- kitchen/bar routing
- receipt printing
- local sync queue / outbox

Accounting should own:
- recipes
- inventory and FIFO
- purchasing
- COGS
- journals
- financial reporting
- reconciliation source of truth for drawers and banks

## Important gaps in the current accounting code for POS integration

1. `MoneyTransaction` has no durable external integration key.
2. Cashflow summary currently treats posted money transactions without journals as failures.
3. `SaleOrder` is not POS-grade yet because it only has one `payment_method` and no split-payment lines.
4. `SaleOrder` has no cashier/register/session/outlet context.
5. Revenue posting currently maps by payment method, not by specific drawer account.

## Recommended architecture

### POS Cloud
- `frontend/` Next.js 14 App Router
- `backend/` FastAPI
- PostgreSQL in production
- SQLAlchemy + service layer + outbox sync worker

### Accounting Cloud
Keep current app, but add a thin integration facade:
- `/api/integrations/pos/catalog/export`
- `/api/integrations/pos/sales/finalize`
- `/api/integrations/pos/cash-events`
- `/api/integrations/pos/reconciliations`

The POS should not call many internal accounting endpoints directly once separated. Use a facade that orchestrates existing services.

## POS backend modules

- `app/api/pos_auth.py`
- `app/api/pos_catalog.py`
- `app/api/pos_orders.py`
- `app/api/pos_registers.py`
- `app/api/pos_cash.py`
- `app/api/pos_sync.py`
- `app/api/pos_printers.py`
- `app/services/pos_catalog_service.py`
- `app/services/pos_order_service.py`
- `app/services/pos_payment_service.py`
- `app/services/pos_register_service.py`
- `app/services/pos_cash_service.py`
- `app/services/pos_sync_service.py`

## POS data model

### Catalog snapshot
- `pos_catalog_items`
  - id
  - external_menu_item_id
  - external_sku_id
  - module_slug
  - item_name
  - variant_name
  - display_name
  - category_name
  - price
  - is_active
  - is_available
  - prep_station
  - accounting_hash
  - last_sync_at

### Register and session
- `pos_registers`
  - code
  - name
  - outlet_code
  - accounting_financial_account_code
  - is_active
- `pos_register_sessions`
  - session_code
  - register_id
  - opened_by_user_id
  - opening_float
  - expected_cash
  - counted_cash
  - variance
  - status
  - opened_at
  - closed_at

### Orders
- `pos_orders`
  - order_uuid
  - order_no
  - business_date
  - register_session_id
  - cashier_user_id
  - order_type
  - channel
  - guest_name
  - status
  - subtotal_amount
  - discount_amount
  - service_charge_amount
  - tax_amount
  - total_amount
  - notes
  - external_sync_status
- `pos_order_lines`
  - order_id
  - catalog_item_id
  - external_menu_item_id
  - external_sku_id
  - item_name_snapshot
  - qty
  - unit_price
  - line_discount
  - line_total
  - notes
- `pos_order_payments`
  - order_id
  - tender_type
  - amount_tendered
  - amount_applied
  - change_given
  - reference_no
  - accounting_financial_account_code
  - payment_status

### Drawer and cash movement
- `pos_cash_events`
  - cash_event_uuid
  - register_session_id
  - event_type
  - amount
  - reason_code
  - note
  - approved_by_user_id
  - accounting_financial_account_code
  - source_order_id nullable
  - sync_status

### Voids / refunds
- `pos_void_events`
- `pos_refund_events`

### Sync reliability
- `integration_outbox`
  - event_uuid
  - aggregate_type
  - aggregate_id
  - event_type
  - payload_json
  - idempotency_key
  - status
  - retry_count
  - next_retry_at
  - last_error

## POS frontend pages

- `/login`
- `/register/select`
- `/register/open`
- `/pos`
- `/pos/held`
- `/pos/orders/[id]`
- `/pos/pay`
- `/pos/cash-movements`
- `/pos/close-shift`
- `/pos/sync`
- `/kitchen`
- `/bar`
- `/settings/device`

## POS frontend components

- `PosShell`
- `CategoryRail`
- `ProductGrid`
- `CartPanel`
- `ModifierModal`
- `PaymentSheet`
- `SplitPaymentSheet`
- `HoldOrderModal`
- `VoidOrderModal`
- `CashMovementModal`
- `OpenShiftModal`
- `CloseShiftWizard`
- `SyncStatusPill`
- `ReceiptPreview`

## Accounting-side changes recommended

### Extend existing tables
Add to `MoneyTransaction`:
- `external_source`
- `external_id`
- `external_parent_id`
- `journal_expected` boolean default false
- unique `(external_source, external_id)`

Add similar external fields to:
- `AccountTransfer`
- `CashReconciliation`
- `SaleOrder`

### Add POS-aware sale mirror support
Either:
1. add `SaleOrderPayment` table, or
2. create dedicated integration tables for mirrored POS payments

### Add financial account GL mapping
Add optional field on `FinancialAccount`:
- `gl_control_account_code`

### Fix false journal failure alert
In cashflow summary, only flag missing journals when `journal_expected = true`.

## Integration behavior

### Catalog sync
Accounting exports sellable items only.
POS stores a snapshot with external IDs.
Do not sync recipe lines into POS.

### Sale finalization
POS finalizes order locally first.
Then outbox publishes a payload to accounting.
Accounting integration facade should:
1. mirror the sale
2. create or update revenue posting
3. consume inventory / compute COGS using accounting recipes
4. record tender movements into the correct drawer / e-wallet / bank financial account

### Cash movements not tied to sale
Examples:
- opening float
- paid out
- paid in
- safe drop
- owner withdrawal
- drawer adjustment

These should sync to accounting as drawer movements immediately.

### Reconciliation
POS closes shift and submits counted cash.
Accounting records official reconciliation against the mapped `FinancialAccount`.

## Practical rule for V1

Build POS now with:
- catalog snapshot
- order/cart flow
- payments
- register sessions
- cash movements
- close shift
- outbox sync

Do not build in POS now:
- ingredient editor
- purchase receiving
- FIFO logic
- stock ledger maintenance
- full expense module

## Best initial sequence

1. POS auth + register session
2. POS catalog snapshot
3. Cart / order / payment flow
4. Cash movements
5. Outbox + idempotency
6. Accounting integration facade
7. Sale mirror + revenue/COGS sync
8. Reconciliation and close shift

