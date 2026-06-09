# POS End-to-End Scenario Tests

Date: 2026-06-09

POS owns orders, tenders, refunds, voids, room charges, cash drawer sessions, cash movements, reconciliation source data, and daily operational context. It does not compute payroll or post final Accounting journals.

| Scenario | Expected Result | Actual Result | Status | Notes |
| --- | --- | --- | --- | --- |
| POS sale to Accounting | Finalized sale creates one Accounting import/review item; replay is idempotent | Existing contract and sync flow documented | Partial | Live replay not executed in this shell |
| Split tender | Accounting receives tender breakdown without duplicate downstream sale | Existing contract documented | Partial | Full pytest not run because `pytest` is missing locally |
| Refund | Refund creates one outgoing Accounting review/cashflow payload | Existing contract documented | Partial | Live refund fixture needed |
| Void/reversal | Void reverses downstream sale once and preserves audit trail | Existing contract documented | Partial | Live void fixture needed |
| Drawer/session reconciliation | Closed session sends expected/actual cash and variance | Existing contract documented | Partial | Live sync not executed |
| Room charge | POS stores pending front-desk post, then posted/settled lifecycle | Existing contract documented | Partial | Browser workflow not run |
| Daily operations context | `/api/reports/daily-ops-context` returns totals/counts only and no PII | Compile check passed after route hardening; test file exists | Partial | Pytest missing locally |
| Operations status | Daily context envelope can be sent as `daily_sales_context` | Endpoint returns `integration_event` envelope | Partial | Live Operations POST not executed |
| Integration auth | Production daily-context route requires `X-Integration-Api-Key` | Code compile check passed | Pass for static check |
| Launcher routing | POS opens at `https://pos.hiddenoasis.app` from static launcher | Live POS currently returns HTTP 200 | Pass for current subdomain |
