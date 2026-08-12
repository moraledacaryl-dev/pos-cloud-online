# Pass 11 — Reliability and Observability Hardening

## Purpose

Separate process liveness, core POS readiness, and downstream integration health so operational failures cannot be hidden behind a generic `ok: true` response.

## Changes

- `/healthz` remains a lightweight liveness endpoint.
- `/readyz` returns HTTP 200 only when the POS database, schema, and security configuration are ready for local sales; downstream outages do not stop cashier operations.
- `/readyz/integrations` returns HTTP 200 only when the full operational health report is healthy, including sync worker freshness, unresolved failed/blocked outbox events, and configured Accounting reachability.
- `/healthz/details` now reports `status`, `sales_ready`, `integrations_ready`, and explicit reason codes.
- Stale sync-worker heartbeats now degrade detailed health.
- Failed and blocked outbox events now degrade detailed health.
- Configured-but-unreachable Accounting now degrades detailed health without making local selling unready.
- Outbox metrics now include every status in `total`, plus `attention_required`, oldest unresolved event ID/UUID/status/age, maximum retry depth, and status counts.

## Operational interpretation

- `healthy`: local selling and downstream integrations are operational.
- `degraded`: local selling is safe, but at least one integration requires attention.
- `unready`: a core dependency such as the database/schema/security configuration is unsafe for POS operation.

## Deployment

No database migration is required. Restart the backend after deployment. The sync worker does not require a code-path change for this pass, but should remain active and fresh in the resulting health report.
