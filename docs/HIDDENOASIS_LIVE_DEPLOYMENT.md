# Hidden Oasis POS Live Deployment

The complete one-server deployment guide is maintained in:

```text
/opt/accounting-program-online/docs/HIDDENOASIS_LIVE_DEPLOYMENT.md
```

POS-specific live targets:

```text
Frontend: https://pos.hiddenoasis.app
Backend:  https://pos.hiddenoasis.app/api
Database: hiddenoasis_pos_live
DB user:  hiddenoasis_pos_app
Systemd:  hiddenoasis-pos-backend
Systemd:  hiddenoasis-pos-frontend
Systemd:  hiddenoasis-pos-sync-worker
```

Required POS env files:

```text
/etc/hiddenoasis/pos-backend.env
/etc/hiddenoasis/pos-frontend.env
```

Important production settings:

```text
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://hiddenoasis_pos_app:REAL_POS_DB_PASSWORD@127.0.0.1:5432/hiddenoasis_pos_live
ALLOW_DEFAULT_ADMIN_BOOTSTRAP=false
CORS_ORIGINS=https://pos.hiddenoasis.app
ACCOUNTING_API_BASE=https://hiddenoasis.app/api
ACCOUNTING_INTEGRATION_SECRET=same value as Accounting INTEGRATION_SECRET
NEXT_PUBLIC_API_BASE=/api
```

POS uses its own PostgreSQL database and consumes Accounting as the source of truth through the Accounting API.

POS structure:

```text
POS has its own FastAPI backend, Next.js frontend, PostgreSQL database, and sync worker.
POS is not frontend-only.
```

Minimum POS smoke checks:

1. Log in at `https://pos.hiddenoasis.app`.
2. Open the POS main screen / terminal.
3. Confirm POS Settings use `https://hiddenoasis.app/api`.
4. Test Accounting connection.
5. Sync catalog.
6. Open a register/session and place a test order.
7. Confirm the sync worker can push the sale/cash event to Accounting.
