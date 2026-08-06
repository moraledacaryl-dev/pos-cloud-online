# Pass 2 — Catalog Ownership Consolidation

## Final authority

Inventory & Procurement is the business owner of product identity, SKUs, recipes, stock, and master availability.

Accounting remains the compatibility transport for the current POS menu feed until a direct Inventory catalog endpoint is enabled. Transport does not imply business ownership.

POS owns only:

- the local selling snapshot used during service
- local sold-out / restore overrides
- POS presentation and station-routing behavior
- emergency local-only fallback items

## Editing rules

Synchronized products cannot be renamed, repriced, remapped, or deleted in POS. POS may only apply a local availability override.

Local-only fallback items are exceptional and temporary. The permanent product must be created in Inventory, synchronized into POS, and the fallback then removed.

## Freshness contract

`GET /catalog/status` returns:

- `fresh` when the last successful refresh is no more than 24 hours old
- `stale` when it is older than 24 hours
- `never_synced` when no successful refresh is recorded

The response also identifies Inventory as business owner, Accounting as compatibility transport, and POS as the selling-snapshot owner.

## Deployment impact

This pass adds no database migration. It adds one backend policy module, one read-only status endpoint, catalog-page freshness warnings, and unit tests.

The existing `POST /catalog/sync-from-accounting` endpoint remains operational for compatibility and now returns ownership metadata.
