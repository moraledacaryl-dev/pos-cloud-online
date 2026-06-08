# Hidden Oasis Deployment Portal Plan

Use `hiddenoasis.app` as the production root domain. The root should eventually serve a static launcher only; it should not authenticate users, store sessions, merge permissions, call app APIs, or load heavy JavaScript.

## Routing

- `https://hiddenoasis.app` -> static launcher
- `https://www.hiddenoasis.app` -> static launcher
- `https://accounting.hiddenoasis.app` -> Accounting Program
- `https://pos.hiddenoasis.app` -> POS Cloud
- `https://operations.hiddenoasis.app` -> Operations Command Center
- `https://staff.hiddenoasis.app` -> Staff & Payroll

Each app keeps its own login, permissions, and database. There is no SSO, no shared session, and no shared permission store.

## Launcher

Use static HTML or a minimal static Next.js export with four clear cards: Accounting Program, POS Cloud, Operations Command Center, and Staff & Payroll. Serve it with Nginx/CDN edge caching. The launcher must perform no server-side app API calls and should load in under one second.

## Reverse Proxy

Use subdomains for the cleanest routing and least app complexity. Nginx should route each subdomain directly to the correct app service, preserve `X-Forwarded-*` headers, enable gzip/Brotli where useful, and let Nginx/CDN serve static assets.

## Environment Variables

- `PUBLIC_APP_URL`
- `APP_BASE_PATH`
- `ACCOUNTING_API_BASE_URL`
- `POS_API_BASE_URL`
- `OPERATIONS_API_BASE_URL`
- `STAFF_PAYROLL_API_BASE_URL`
- `ALLOWED_ORIGINS`
- `CORS_ORIGINS`
- `INTEGRATION_API_KEY`

## Health Checks

- Accounting: `/healthz`
- POS: `/healthz`
- Operations: `/api/health`
- Staff/Payroll: `/health` when productionized; use process-level monitoring while it remains a Streamlit prototype.

## Deployment Order

1. Accounting
2. POS
3. Operations
4. Staff/Payroll
5. Static launcher

## Backup And Rollback

Back up each app database separately. Back up uploaded files, exported payload ZIPs where retained, service logs, and Nginx config. Keep a rollback plan that can point each subdomain back to the previous app release independently.

## Performance Requirements

Keep apps separate for fault isolation. Do not make the launcher call app APIs on page load. Lazy-load heavy dashboard panels, cache overview counts where safe, index `external_source`, `external_id`, `event_type`, `status`, and `created_at`, avoid loading raw payloads in list views, paginate large review queues, use outbox/background retries for integration posting, and never block POS cashier actions on Accounting availability.
