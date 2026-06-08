# Hidden Oasis Deployment Portal Plan

`https://hiddenoasis.app` should become a static launcher with four links:

- `/accounting` -> `https://accounting.hiddenoasis.app`
- `/pos` -> `https://pos.hiddenoasis.app`
- `/operations` -> `https://operations.hiddenoasis.app`
- `/staff` -> `https://staff.hiddenoasis.app`

Each app keeps its own login. No SSO is planned for this phase.

Use a static HTML or minimal Next.js launcher with four buttons, long-lived CDN/edge caching, and no server-side integration calls. This keeps launcher latency negligible and avoids CPU spikes.

Required environment variables by app as applicable:

- `APP_BASE_PATH`
- `PUBLIC_APP_URL`
- `ACCOUNTING_API_BASE_URL`
- `POS_API_BASE_URL`
- `OPERATIONS_API_BASE_URL`
- `STAFF_PAYROLL_API_BASE_URL`
- `ALLOWED_ORIGINS`
- `INTEGRATION_API_KEY`

Reverse proxy guidance: route subdomains directly to each app service with Nginx, preserve `X-Forwarded-*` headers, enable gzip for API responses where useful, and serve static assets through Nginx/CDN. Keep databases separate.

Health checks:

- Accounting: `/healthz`
- POS: `/healthz`
- Operations: `/api/health`
- Staff/Payroll: add a production health route when the Streamlit prototype is rebuilt; until then use process-level monitoring.

Deployment order: Accounting, POS, Operations, Staff/Payroll.
