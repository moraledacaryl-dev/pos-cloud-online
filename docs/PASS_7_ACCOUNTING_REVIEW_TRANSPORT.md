# Pass 7 — Accounting Review Transport Hardening

## Goal

Make every POS process use the same review-first Accounting transport so financial events cannot silently take a different path depending on whether they are processed by the API process or the background worker.

## Defect fixed

The API process installed `review_aware_order_void_push`, but `app.workers.sync_worker` imported and ran `sync_service.run_outbox_sync` without installing that adapter.

For `order.voided`, the legacy sender first looks up an Accounting sale using `current_erp_sales_path`. In review-first deployments that path is `/integrations/pos-review/order`, which is an intake POST route rather than the legacy sale resource. A worker-processed void could therefore return `None` from the legacy lookup and be marked synced without creating the Accounting order-void review item.

## Final behavior

Both processes now call the same idempotent installer:

- POS API process
- POS background sync worker

The installer wraps `_push_order_void` exactly once. When `current_erp_sales_void_path` is configured, a void is posted directly to `/integrations/pos-review/order-void` with the stable order UUID/external ID. Explicit deployments that intentionally omit the review void path retain the legacy fallback.

## Cross-app ownership

- POS owns the operational order, payment, refund, void, register session, and drawer events.
- Accounting receives review items and owns financial acceptance/posting.
- Inventory & Procurement owns physical stock consumption, recipe/BOM effects, valuation, and stock reversal.
- Accounting's POS order review remains `reference_only`; it must not independently consume physical stock or calculate a second COGS event.

## Acceptance criteria

1. API and worker install the same Accounting review transport.
2. Installation is idempotent.
3. POS void sends directly to the Accounting review route when configured.
4. Stable `external_id` is retained for replay safety.
5. Legacy fallback remains available only when the review void path is intentionally absent.
6. Full backend and frontend CI remain green.
