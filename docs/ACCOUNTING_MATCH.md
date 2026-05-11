# Accounting Match Summary

This POS repo was intentionally aligned to the accounting program patterns you attached:

- FastAPI backend with `app/api`, `app/services`, `app/models`, `app/schemas`, `app/db`, `app/core`
- SQLAlchemy declarative models following the same entity style
- JWT auth flow compatible in shape with the accounting app (`/auth/bootstrap`, `/auth/login`, `/auth/me`)
- Next.js App Router frontend with shared shell pattern:
  - sidebar
  - top header
  - route guard
  - `lib/api.js`
- Visual language inherited from the accounting frontend CSS and extended for a high-end POS terminal layout
- Drawer logic separated from inventory logic so the accounting app remains the source of truth for recipes, stock, FIFO, and COGS

POS-specific additions that the accounting repo does not yet model directly:
- register sessions
- split tenders
- cashier/session-local paid in and paid out
- outbox-based sync queue
- kitchen line status
