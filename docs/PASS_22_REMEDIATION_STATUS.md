# Pass 22 — POS remediation status

Date: 2026-09-02 (Asia/Manila)

This document reconciles the comprehensive POS audit with the current source tree. It distinguishes implemented code from evidence that can only be produced in staging, production, or on physical POS hardware.

## Release summary

The release-blocking application defects found in the latest browser and source audit have been corrected. The application is **code/deployment ready**, subject to the external acceptance gates in `PASS_16_OPERATIONAL_ACCEPTANCE.md`. It must not be described as 100% operationally accepted until those gates have dated evidence.

## Remediation delivered

### Checkout and transaction correctness

- Frontend totals now use the same net tax and service-charge calculation as the backend. The real-browser verification sale displayed and posted `₱152.10` from a `₱130.00` item with 12% tax and 5% service charge.
- Catalog tax and service-charge rates survive cart construction and held-order reopening.
- The backend rejects any client-supplied price that differs from the current catalog price. Authorized discounts remain the supported price-reduction path.
- Payment failures stay inside the payment dialog with a recoverable error instead of losing cashier context.
- Offline drafts and cached receipts are versioned, bounded by TTL, and bound to the active user/register/session where applicable.

### Security and resilience

- Production CSP keeps JavaScript nonce-only and permits React's required inline style attributes. This fixes the blank/unstyled production UI without weakening script execution policy.
- Browser authentication remains cookie based; mutation requests include CSRF protection; KDS streams use short-lived single-use tickets instead of URL JWTs.
- Customer-display pairing is random, expiring, one-time, revocable, server backed, no-store, and excludes guest PII/internal database IDs.
- Customer-display store outages produce a typed 503 instead of an unhandled server error.
- Password hashing uses PBKDF2-SHA256 with constant-time verification while retaining legacy-hash migration support; the obsolete passlib/bcrypt runtime dependency was removed.
- Production services now use strict filesystem protection, home/device isolation, kernel/control-group protection, restricted address families, empty capability sets, restrictive umasks, and explicit task/file/memory limits.
- Deployment uses an exact release SHA, protected environments, pre-deploy test/build/lint gates, a release artifact, a least-privilege PostgreSQL backup service, service-aware replacement, readiness waits, health certification, and rollback installation from the locked dependency set.

### Usability and accessibility

- Login, loading, empty, error, disabled, success, restricted, and not-found states are explicit.
- The POS workspace has a real loading state and no longer shows a false empty-session message while requests are pending.
- All 13 POS dialogs have workflow-specific accessible names. Shared dialogs trap focus, close on Escape, and restore focus, including sequential modal transitions.
- Navigation, main content, sync status, tables, and scroll regions have named landmarks/semantics; tables are keyboard focusable and action columns are labeled.
- Mobile navigation is a controlled off-canvas drawer with inert background, focus handling, route close, body-scroll lock, 44px controls, and responsive tests at the supported breakpoints.
- Audit details are collapsed by default; audit data is cursor-paged; raw event/status/aggregate codes are rendered as staff-readable labels.
- Sync diagnostics distinguish a memory ticket store from an actual Redis outage, and queue/event labels are human readable.
- Customer display uses `Dine-in` rather than the internal `dine_in` code and shows consistent Philippine peso formatting.

### Maintainability and automated gates

- Frontend source audit, ESLint 9 configuration, UI/domain tests, full production build, and a production-server route smoke test are part of `npm run verify` and standard CI.
- The smoke test requests every application route, the not-found route, customer display, a built static asset, CSP headers, and the API path.
- Backend Ruff checks and the locked development requirements are part of standard CI.
- PostgreSQL, Redis, Alembic, worker, KDS concurrency, role matrix, Playwright/Axe, dependency audit, and container-parity suites remain enforced in the production-equivalent workflows.
- Shared POS domain helpers were extracted from the page into `frontend/lib/posWorkspace.mjs` with characterization tests.
- Systemd hardening and release-script executable bits now have regression assertions.

## Audit backlog reconciliation

| Audit area | Current status | Evidence or remaining action |
|---|---|---|
| SEC-001 server-bound approvals | Implemented | Approval-token binding/replay/expiry/entity/amount contracts and backend suites. Re-run the role matrix on the release SHA. |
| REL-001 KDS DB lifecycle | Implemented | One-time ticket stream and disconnect/load contracts. Re-run the production-equivalent KDS soak. |
| SEC-002 URL JWT removal | Implemented | KDS source and tests contain no access JWT query parameter. |
| SEC-003 strict production secrets | Implemented | Production/staging validation and negative deployment contracts. |
| SEC-004 local-only bootstrap | Implemented | Explicit guarded bootstrap behavior and tests. |
| UX-001 responsive shell | Implemented in code | Source/interaction tests pass. Capture the final staging viewport matrix at 360/390/768/820/1024 and 200% zoom. |
| SEC-005 customer display | Implemented | Pair, activate, update, revoke, and re-pair require final device/network acceptance. |
| SEC-006 browser token storage | Implemented | Cookie/BFF/CSRF contracts pass. |
| SEC-007 security headers | Implemented in app | CSP and browser smoke pass. Verify HSTS at the real TLS ingress. |
| DEP-001 supported frontend stack | Implemented | Node 24, Next 16.3.3, patched overrides, immutable reviewed Docker base-image digest, and clean production dependency audit. |
| DB-001 integrity/PostgreSQL CI | Implemented | SQLite foreign-key checks and PostgreSQL production-equivalent workflow exist. Execute workflow on release SHA. |
| AUD-001/002 audit design and paging | Implemented | Business/security audit separation, filters, cursor paging, readable details. |
| OBS-001 protected diagnostics | Implemented | Public health is minimal; detailed endpoints are private/authenticated. |
| AUTH-001 auth abuse control | Implemented | Rate-limit/proxy/negative tests; staging abuse probe remains an operational gate. |
| CI-001 production-equivalent gates | Implemented | Workflow exists; green run on exact release SHA is required. |
| A11Y/KDS/ROUTE/I18N/API/INT/SYNC/UX/PERF | Implemented in code | Local contracts and browser smoke pass; staging Axe/viewport/integration evidence remains. |
| ARCH-001 frontend decomposition | Improved, not complete | Domain calculations/configuration were extracted and tested; `app/pos/page.js` remains large and should be split by workspace panel in a non-release refactor. |
| ARCH-002 backend decomposition | Not release blocking; still open | `pos_service.py` remains a large transactional service. Split by sessions/orders/payments/refunds/treasury/KDS behind the existing 241-test characterization suite. |
| DEP-002 hashed Python lock | Implemented | Runtime and development locks contain exact versions and package hashes and were installed successfully in a clean Python 3.12 environment. |
| DEP-003 JWT dependency chain | Implemented | Maintained PyJWT path and algorithm allowlisting; obsolete passlib/bcrypt dependency removed. |
| TIME-001 aware UTC | Implemented by existing migration/contracts | Revalidate against PostgreSQL during release certification. |
| DEP-004/005 deployment and migrations | Implemented | Exact-SHA protected deploy, single-run migration, certification, and rollback scripts. Run only against approved staging/production targets. |
| OPS-001 service hardening | Implemented | Hardened units and regression contracts; run `systemd-analyze verify` on the Linux host. |
| OFF-001 offline lifecycle | Implemented | TTL, schema version, identity/register/session binding and logout/close cleanup. Complete controlled network-loss acceptance. |

## Verification completed on this pass

- Backend: Ruff clean; `243 passed, 2 skipped`. The two skips are production-only PostgreSQL/Redis checks represented in CI.
- Frontend: source audit clean; ESLint clean; `55 passed`; Next production build compiled all 22 routes.
- Production smoke: 20 routed page checks plus CSP, static asset, not-found, protected shell, customer-display, and API-path checks passed.
- Dependency audit: npm production audit and Python locked-dependency audit reported no known vulnerabilities during this remediation pass.
- Configuration: all GitHub workflow YAML parsed; the release shell script passed syntax validation; `git diff --check` passed.
- Real browser: styled login, authenticated shell, POS loading/session state, tools menu, workflow dialogs, customer-display pairing, sale/payment/receipt, sync diagnostics, audit, and cash-movement views were exercised. The completed test sale was `POS-20260901-0010` for `₱152.10`.

## Required before calling the product 100% complete

1. Merge a reviewed commit and run every CI workflow on that exact SHA.
2. Deploy that SHA to an isolated PostgreSQL/Redis staging clone and run `scripts/pass16-staging-certify.sh`.
3. Perform and record a backup restore plus forward/rollback migration rehearsal.
4. Exercise real staging credentials for Accounting, Inventory, Staff, and Operations, including outage, retry, idempotency, and reconciliation.
5. Certify the receipt/kitchen printers, cash drawer, card terminal, KDS, and customer display on the actual supported devices and network.
6. Capture the final role × route × viewport × dialog/error-state matrix and obtain zero serious/critical Axe findings or a dated waiver.
7. Run a controlled live pilot and collect role acceptance from Owner/Admin, Manager, Cashier/Reception, Kitchen/Bar, and Accounting.
8. Complete the two remaining maintainability refactors as scheduled engineering work; neither should be combined with the live pilot unless the release date allows another full regression cycle.

The evidence templates and safety constraints for steps 2–7 are in `PASS_16_OPERATIONAL_ACCEPTANCE.md`.
