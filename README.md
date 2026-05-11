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
https://hiddenoasis.app/api
```

The POS keeps its own live database for sessions, orders, payments, kitchen routing, and sync state. Accounting remains the source of truth for catalog, categories, variants, financial accounts, receivables, and reporting.
