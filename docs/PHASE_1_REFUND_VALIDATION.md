# Phase 1 Step 1 Refund Upgrade Validation

Base package: `dedicated-pos-cloud-scope-6-10.zip`
Upgrade scope applied: **true refund system only**

## Added
- Refund, RefundLine, RefundPayment backend tables
- RefundCreate / RefundLineCreate schemas
- Refund service logic for:
  - full refunds
  - partial line refunds
  - amount refunds
  - manager approval validation
  - cash refund cash-movement creation
  - non-cash refund outbox events by tender type
- Order API endpoints:
  - `GET /api/orders/{order_id}/refunds`
  - `POST /api/orders/{order_id}/refunds`
- Refund receipt printing helpers
- Orders page refund workflow with manager override modal
- Backend tests for full cash refund and partial non-cash refund

## Checks run
- Backend Python compile: passed
- Backend pytest suite: 7 passed
- No original file paths intentionally removed

## Known boundary
- This package applies **Step 1 only**.
- Room-charge folio workflow was not changed in this pass.
- Frontend Next.js production build was not certified in this sandbox.
