# Pass 5 — Inventory Consumption and Reversal Handoff

## Authority

Inventory & Procurement remains the system of record for recipes, ingredient consumption, physical stock, and inventory valuation. POS records the operational sale and emits durable facts; it never calculates ingredient deductions itself.

## Sale flow

When an order is successfully finalized, POS queues one dedicated Inventory event with:

- `external_event_id = pos:{order_uuid}:sale_completed`
- `external_sale_id = order_uuid`
- `pos_system = hidden-oasis-pos`
- `event_type = sale_completed`
- one line per POS item using `sku_code`, with `external_sku_id` as the compatibility fallback

The sync worker sends the event to `POST /api/v1/integrations/pos/events` using `X-Integration-Token`.

## Durable delivery

Inventory events reuse the POS sync outbox but use dedicated states:

- `inventory_pending` — queued for Inventory only
- `inventory_retry` — network or downstream 5xx; retry with backoff
- `blocked` — configuration, mapping, or downstream validation problem requiring operator action
- `synced` — Inventory accepted the event

The Inventory processor runs before the existing Accounting outbox processor. Dedicated Inventory states prevent Accounting from consuming or misclassifying Inventory events.

## Mapping failure

A sale is atomic from the Inventory perspective. If any positive-quantity POS line has no Inventory product identifier, the Inventory event is blocked rather than partially consuming only the mapped lines. The outbox error identifies the unmapped POS item so the mapping can be corrected and the event replayed.

## Reversals

### Void

A void queues `sale_voided` only if the order had already reached `paid` or `folio_pending`. Voiding an unfinalized draft/open/service order does not send an Inventory reversal because no Inventory sale consumption should exist yet.

### Refund

Inventory currently supports full-sale reversal, not quantity-aware partial stock reversal. Therefore:

- partial refund: financial refund only; no Inventory stock reversal
- fully refunded order: queue one deterministic `sale_refunded` full reversal

This prevents a partial monetary refund from restoring the entire recipe to stock. Quantity-aware physical returns require a future Inventory contract before POS may send partial stock reversals.

## Idempotency

POS outbox key:

`inventory:pos:{order_uuid}:{event_type}`

Inventory receiver key:

`external_event_id = pos:{order_uuid}:{event_type}`

Both layers are replay-safe. A repeated worker attempt must not create a second stock document.

## Production configuration

Inventory backend:

`POS_INTEGRATION_TOKEN=<shared long random secret>`

POS backend:

- `INVENTORY_INTEGRATION_ENABLED=true`
- `INVENTORY_API_BASE=https://inventory.hiddenoasis.app/api/v1`
- `INVENTORY_INTEGRATION_TOKEN=<same shared long random secret>`
- `INVENTORY_POS_EVENTS_PATH=/integrations/pos/events`

Do not commit the real token.

## Deployment impact

No POS database migration is required. Deploy the Inventory receiver first, configure the shared secret on both apps, then deploy POS and restart the POS backend and sync worker. This ordering prevents POS from attempting the new handoff before Inventory can authenticate it.
