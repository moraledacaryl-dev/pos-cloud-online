# POS Cloud Online

This is the deployment copy for the live Hidden Oasis POS.

Live target:

```text
Frontend: https://pos.hiddenoasis.app
Backend:  https://pos.hiddenoasis.app/api
Database: hiddenoasis_pos_live
DB user:  hiddenoasis_pos_app
```

It is deployed together with:

```text
/Users/carylmoraleda/accounting-program-online
```

Server path:

```text
/opt/pos-cloud-online
```

Primary deployment guide:

```text
/Users/carylmoraleda/accounting-program-online/docs/HIDDENOASIS_LIVE_DEPLOYMENT.md
```

POS connects to Accounting at:

```text
https://accounting.hiddenoasis.app/api
```

`https://hiddenoasis.app` is reserved for the future static launcher. POS must not depend on `https://hiddenoasis.app/api` for Accounting sync.

The POS keeps its own live database for sessions, orders, payments, kitchen routing, and sync state. Inventory & Procurement is the system of record for product/SKU identity, recipes, physical stock, consumption, and inventory valuation. Accounting is the system of record for financial accounts, tax, receivables, journals, reconciliation, and reporting. Existing Accounting-hosted catalog/sale endpoints are a temporary compatibility transport, not the final ownership boundary. See `docs/SYSTEM_OWNERSHIP.md`.
