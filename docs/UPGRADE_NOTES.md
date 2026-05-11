# POS Upgrade Notes

This upgraded package adds the most important missing pieces identified in the review:

- resume and continue an existing held or draft order without creating a duplicate order
- non-cash settlement outbox events for GCash, card, bank transfer, and room charge
- order void outbox event for accounting-side sale reversal
- transfer outbox events for safe drop, bank deposit, and drawer transfer
- accounting financial account picker and validation endpoint for register mapping
- richer cashier UI: search, barcode/code add, line notes, line discounts, quick quantities, quick payment buttons, receipt preview
- richer order history: deeper filters and reopen in POS
- richer cash movement UI with transfer semantics
- richer session close UI with denomination lines and reopen flow
- improved kitchen view with grouping and auto-refresh
- basic health endpoint and audit-log setting stream
- backend smoke tests added under `backend/tests`
- dedicated room-charge posting workflow with front-desk posting queue, in-house booking picker, and separated service / folio-post / payment dates

## Validation completed in container

- backend Python files compile successfully with `py_compile`
- original repo structure preserved and extended in place
- upgraded repo zipped after patching

## Validation not completed in container

- full frontend Next.js build
- full backend runtime integration against a live accounting server
- pytest execution, because this container does not include the POS backend runtime dependencies preinstalled

## Phase 2 room-charge redesign

This package now treats room charge as a service posting workflow, not an immediate payment method.

Added in this pass:
- dedicated `RoomChargePosting` records as café-side source of truth
- in-house booking snapshot / picker for stay date, room, and guest selection
- front-desk queue to mark `posted_to_beds24`, `rejected`, `disputed`, `settled_at_frontdesk`, `written_off`, or `cancelled`
- separated service date, folio post date, and payment date tracking
- room-charge metadata restored in POS, Orders, and API payloads

## Phase 9 UX refinement
- Cashier/front-desk: ranked POS search, quicker payment keypad flow, improved room-charge booking matching, clearer room-charge status chips and queue views.
- Manager/admin: session archive filters, sync diagnostics/recovery queue, richer audit and approval review workspace.
- Validation: node UI contract tests pass; frontend page syntax checked with the TypeScript JSX parser in this container.
