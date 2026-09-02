# Hidden Oasis POS Live Deployment

The complete hardened one-server deployment guide is maintained in the
Accounting repository:

```text
../accounting-program-online/docs/HIDDENOASIS_LIVE_DEPLOYMENT.md
```

The canonical supported production profile is:

```text
Frontend: https://pos.hiddenoasis.app
Backend:  https://pos.hiddenoasis.app/api
Database: hiddenoasis_pos_live
DB user:  hiddenoasis_pos_app
Source:   /opt/pos-cloud-online
Systemd:  pos-backend
Systemd:  pos-frontend
Systemd:  pos-sync-worker
/etc/hiddenoasis/pos-backend.env
/etc/hiddenoasis/pos-frontend.env
```

The deprecated `/root/pos-cloud-online` and `hiddenoasis-pos-*` names are not
certified by this repository. Migrate them explicitly before using the release
workflow; never mix legacy and canonical units in one deployment.

Before running `npm install`, `npm ci`, or `npm run build` on the live host,
stop `accounting-frontend` and `pos-frontend`. Never replace `node_modules` or
`.next` underneath a running Next.js server: the old process can serve a
mismatched build and return `500` for pages, JavaScript, and CSS. Restart both
frontend services only after both builds finish.

The live POS API and UI units must bind ports `8100` and `3100` to `127.0.0.1`,
not `0.0.0.0`. Nginx is the only public POS entry point.

Important production settings:

```text
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://hiddenoasis_pos_app:REAL_POS_DB_PASSWORD@127.0.0.1:5432/hiddenoasis_pos_live
ALLOW_DEFAULT_ADMIN_BOOTSTRAP=false
CORS_ORIGINS=https://pos.hiddenoasis.app
ACCOUNTING_API_BASE=https://accounting.hiddenoasis.app/api
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

1. Confirm `https://pos.hiddenoasis.app/healthz` returns `ok`.
2. Confirm `https://accounting.hiddenoasis.app/healthz` returns `ok`.
3. Run `alembic upgrade head` before restarting the POS backend.
4. Log in at `https://pos.hiddenoasis.app`.
5. Confirm the persistent POS sync banner is green.
6. Confirm POS Settings use `https://accounting.hiddenoasis.app/api` with health path `/healthz`.
7. Test Accounting connection.
8. Open Registers and verify every active drawer has a numeric Accounting drawer ID.
9. Sync catalog.
10. Open a mapped register/session and place a controlled test order.
11. Confirm the sync worker can push the sale/cash event to Accounting.
12. Open `/customer-display?channel=main` on a separate browser/device and confirm it updates.
13. Open `/recipes` and verify a staff PDF can be read.

Room-charge note:

```text
POS room charges sync into Accounting receivables, then remain a tracked manual
front-desk posting step into Beds24. Staff must save the Beds24 posting reference
in the POS Room Charges queue.
```

Staff handbook:

```text
https://hiddenoasis.app/guides/HIDDEN_OASIS_STAFF_READY_GUIDE.md
```

Root-domain note:

```text
https://hiddenoasis.app is reserved for the future static launcher. POS must
not use https://hiddenoasis.app/api as Accounting. If a live PostgreSQL
system_settings row still contains the old root API, startup repair updates
the row automatically. Manual repair, if ever needed:

UPDATE system_settings
SET value_json = replace(value_json, 'https://hiddenoasis.app/api', 'https://accounting.hiddenoasis.app/api')
WHERE key = 'accounting_sync';
```
