# POS ↔ Accounting and Beds24 Integration Contract

This document is the stable contract for the POS package in this repository. It formalizes the payloads produced by the POS, the expected receiver-side outcomes, and the idempotency rules that must remain stable when either side evolves.

## General contract rules
- `external_source` is always `dedicated_pos_cloud` for accounting-facing payloads.
- `external_id` is the idempotency key the receiver must treat as unique for replay safety.
- Amounts are decimal numbers in Philippine Peso.
- Dates use `YYYY-MM-DD`.
- Timestamps use ISO-8601 UTC text.
- Room-charge posting to Beds24 is currently a manual front-desk workflow. The POS contract for those events is an internal record contract unless a future transport is added.

## Receiver outcome vocabulary
- **accept**: create the downstream record and return HTTP 2xx.
- **already_applied**: receiver detects the idempotency key or reference number and does not create a duplicate.
- **reject**: receiver returns 4xx because the payload is invalid.
- **retryable_failure**: receiver returns 5xx or the network fails; the POS keeps or retries the outbox event.

## Daily operations context

`GET /api/reports/daily-ops-context?date=YYYY-MM-DD`

Purpose: provide Staff/Payroll and Operations with read-only operational context for a business date. The response contains totals and counts only; it does not expose payroll, HR data, guest names, customer PII, or receipt-level customer details.

Production access requires `X-Integration-Api-Key` when `INTEGRATION_API_KEY` is configured. If production still has a placeholder key, the endpoint rejects requests until a real shared key is installed.

Response fields:

- Flat fields: `business_date`, `generated_at`, `gross_sales`, `net_sales`, `order_count`, `refund_count`, `void_count`
- Tender fields: `cash_sales`, `gcash_sales`, `card_sales`, `bank_transfer_sales`, `room_charge_total`
- Status counts: `open_order_count`, `held_order_count`, `unpaid_order_count`, `pending_room_charge_count`, `active_session_count`
- Timing and variance: `drawer_variance_total`, `first_order_time`, `last_order_time`, `peak_hour`
- Compatibility groups: `totals.*` and `counts.*`
- `warnings[]`
- Optional `integration_event` envelope with `external_source=dedicated_pos_cloud`, `external_id=daily-sales-context:{business_date}`, `event_type=daily_sales_context`, `schema_version=2026-06-v1`, and `payload` equal to the context body.

Warnings may include `drawer_variance.alert`, `room_charge.pending_frontdesk_post`, and `unpaid_orders.warning`. POS users may later be mapped to `employee_code` using safe fields only: display name, role, and active/inactive status.

## 1. Sale sync
**Outbox event:** `order.finalized`

### POS payload shape
```json
{
  "id": 15,
  "order_uuid": "d95a4f53-2b7b-4c3f-a9bf-5c06c98ff2aa",
  "order_no": "ORD-20260420-0001",
  "business_date": "2026-04-20",
  "order_type": "dine_in",
  "source_channel": "pos",
  "guest_name": "Walk-in Guest",
  "table_label": "T1",
  "primary_tender": "cash",
  "payment_breakdown": [
    {"id": 21, "tender_type": "cash", "amount_applied": 120.0, "accounting_financial_account_id": 1, "reference_no": "ORD-20260420-0001:cash"},
    {"id": 22, "tender_type": "card", "amount_applied": 80.0, "accounting_financial_account_id": 9, "reference_no": "CARD-7788"}
  ],
  "lines": [
    {"external_menu_item_id": 3001, "external_sku_id": 4001, "quantity": 2, "unit_price": 100.0, "discount_amount": 0.0, "note": null}
  ]
}
```

### Accounting mapping
`POST /menu/sales`
```json
{
  "order_no": "ORD-20260420-0001",
  "order_date": "2026-04-20",
  "payment_method": "mixed",
  "channel": "dine_in",
  "counterparty": "Walk-in Guest",
  "notes": "{... payment breakdown embedded ...}",
  "strict_inventory": true,
  "auto_post_accounting": false,
  "external_source": "dedicated_pos_cloud",
  "external_id": "d95a4f53-2b7b-4c3f-a9bf-5c06c98ff2aa",
  "lines": [
    {"menu_item_id": 3001, "sku_id": 4001, "quantity": 2, "unit_price": 100.0, "discount_amount": 0.0, "notes": null}
  ]
}
```

### Expected outcome
- accept: create one sale
- already_applied: if `external_id` or `order_no` already exists
- reject: if any sale line is missing `external_menu_item_id`

## 2. Refund sync
**Outbox event:** `payment.refunded`

### POS payload shape
```json
{
  "refund_no": "RFD-20260420-0001",
  "order_no": "ORD-20260420-0001",
  "created_at": "2026-04-20T08:15:00",
  "guest_name": "Walk-in Guest",
  "payment": {"id": 44, "tender_type": "gcash", "amount": 100.0, "accounting_financial_account_id": 12, "reference_no": "GC-REF-1"}
}
```

### Accounting mapping
`POST /cashflow/transactions`
```json
{
  "transaction_date": "2026-04-20T08:15:00",
  "direction": "out",
  "financial_account_id": 12,
  "module": "restaurant",
  "category": "POS Refund",
  "subcategory": "gcash",
  "level3_item": "Refund RFD-20260420-0001",
  "amount": 100.0,
  "payment_method": "gcash",
  "reference_no": "GC-REF-1",
  "counterparty_name": "Walk-in Guest",
  "linked_record_type": "pos_refund_payment",
  "linked_record_id": 44,
  "external_source": "dedicated_pos_cloud",
  "external_id": "refund-payment:44"
}
```

### Expected outcome
- accept: create one outgoing cashflow transaction
- already_applied: if `external_id` or `reference_no` already exists
- reject: room-charge refund payments are not emitted as cashflow payloads

## 3. Reversal sync
**Outbox event:** `order.voided`

### POS payload shape
```json
{"order_id": 15, "order_no": "ORD-20260420-0001", "business_date": "2026-04-20", "reason": "Customer cancelled"}
```

### Accounting mapping
1. Lookup existing sale by `order_no`
2. `POST /menu/sales/{sale_id}/void`
```json
{"reason": "Customer cancelled", "void_date": "2026-04-20", "reverse_inventory": true, "auto_post_accounting": false}
```

### Expected outcome
- accept: mark sale voided and reverse inventory once
- already_applied: if sale already has `status=voided`
- no-op: if no downstream sale exists yet

## 4. Cash movement sync
**Outbox event:** `cash_movement.created`

### POS payload shape
```json
{"id": 18, "cash_event_uuid": "b1f6", "event_date": "2026-04-20", "direction": "out", "movement_type": "paid_out", "category": "Taxi", "amount": 150.0, "reference_no": "PO-20260420-0003", "accounting_financial_account_id": 1, "note": "Taxi reimbursement"}
```

### Accounting mapping
`POST /cashflow/transactions`
```json
{"transaction_date": "2026-04-20", "direction": "out", "financial_account_id": 1, "module": "restaurant", "category": "POS Drawer", "subcategory": "paid_out", "level3_item": "Taxi", "amount": 150.0, "payment_method": "cash", "reference_no": "PO-20260420-0003", "counterparty_name": "POS Cloud", "linked_record_type": "pos_cash_movement", "linked_record_id": 18, "external_source": "dedicated_pos_cloud", "external_id": "PO-20260420-0003"}
```

## 5. Reconciliation sync
**Outbox event:** `session.closed`

### POS payload shape
```json
{"session_id": 9, "session_code": "2026-04-20-AM-MAIN", "business_date": "2026-04-20", "register_accounting_financial_account_id": 1, "closing_actual_cash": 1480.0, "closing_expected_cash": 1500.0, "variance_amount": -20.0, "close_mode": "verified", "denomination_lines": [{"line_label": "1000x1", "amount": 1000.0, "sort_order": 1}, {"line_label": "20x24", "amount": 480.0, "sort_order": 2}]}
```

### Accounting mapping
`POST /reconciliations`
```json
{"financial_account_id": 1, "reconciliation_date": "2026-04-20", "shift_name": "2026-04-20-AM-MAIN", "actual_counted": 1480.0, "status": "counted", "counted_by": "Dedicated POS", "notes": "Expected 1500.0 / variance -20.0 / mode verified", "lines": [{"line_label": "1000x1", "amount": 1000.0, "sort_order": 1}, {"line_label": "20x24", "amount": 480.0, "sort_order": 2}]}
```

## 6. Room charge creation contract
**Internal POS/back-office contract**

### Trigger
Room-charge tender is applied to a finalized order.

### Stored POS record
```json
{"posting_uuid": "7ab3", "order_id": 15, "order_payment_id": 22, "booking_date": "2026-04-20", "service_date": "2026-04-20", "service_time": "2026-04-20T09:30:00", "room_number": "201", "guest_label": "Rm 201 · Juan Dela Cruz", "beds24_booking_id": "BEDS24-991", "order_source": "room_service", "service_type": "room_service", "charge_amount": 200.0, "posting_status": "pending_frontdesk_post", "later_payment_status": "pending"}
```

### Expected outcome
- create one `RoomChargePosting`
- create audit events `room_charge.created` and `room_charge.booking_selected`
- keep the order settlement state as `folio_pending` or `mixed_with_folio_pending`

## 7. Room charge posting confirmation contract
**Internal POS/back-office contract**

### Input
`PATCH /room-charges/{id}/status`
```json
{"posting_status": "posted_to_beds24", "beds24_posting_reference": "INV-POST-201", "posted_to_beds24_at": "2026-04-20T10:10:00"}
```

### Expected outcome
- update `posting_status=posted_to_beds24`
- store `beds24_posting_reference`
- set `posted_to_beds24_at_text`
- store `posted_by_user_id`
- emit audit event `room_charge.posted_to_beds24`

## 8. Room charge settlement update contract
**Internal POS/back-office contract**

### Input
`PATCH /room-charges/{id}/status`
```json
{"posting_status": "settled_at_frontdesk", "later_payment_status": "settled", "payment_date": "2026-04-21"}
```

### Expected outcome
- keep service date unchanged
- set payment date later if settlement happened later
- emit `room_charge.settlement_updated`
- if previous status was `disputed`, also emit `room_charge.dispute_resolved`

## Replay and idempotency rules
- Sale sync replays must not create duplicate downstream sales.
- Cash movement, refund, and transfer sync replays must not create duplicate downstream transactions.
- Reconciliation replay must not create duplicate reconciliation rows for the same session/date/account.
- The receiver should prefer `external_source + external_id` uniqueness. Where legacy routes do not support it, fallback replay detection uses `order_no`, `reference_no`, or `shift_name` lookups.

## Test coverage linked to this contract
- split tender sale contract
- refund contract
- duplicate replay handling
- room-charge `pending_frontdesk_post → posted_to_beds24 → settled_at_frontdesk`
- rejected room-charge handling
