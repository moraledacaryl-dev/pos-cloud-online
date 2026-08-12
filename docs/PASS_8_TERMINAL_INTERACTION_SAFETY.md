# Pass 8 — Terminal Interaction Safety

## Goal

Make the cashier terminal resilient to rapid double taps and repeated keyboard submissions without changing valid business workflows.

## Implemented

- Added a deterministic mutation request key based on HTTP method, path, and serialized payload.
- Added an in-flight mutation registry shared by the POS frontend API client.
- Identical POST/PUT/DELETE requests issued while the first request is still pending now reuse the original promise instead of sending a second HTTP request.
- Read-only GET/HEAD/OPTIONS requests are never coalesced.
- FormData and Blob uploads are excluded from coalescing so file operations retain normal behavior.
- Mutation locks clear after either success or failure, allowing intentional later retries.

## Operational effect

This protects high-risk cashier actions such as:

- order creation and updates,
- payment submission,
- hold/resume,
- void/refund actions,
- drawer movements,
- register close/reopen,
- table transfer/merge,
- sync retry actions.

The backend remains the final authority for idempotency and transaction state. This frontend guard is an additional UX safety layer, not a replacement for server-side controls.

## Validation

`npm run test:ui` includes dedicated request-guard tests and the normal production `next build` must remain green before merge.
