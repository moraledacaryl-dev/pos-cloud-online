# Pass 16 — Final Operational Acceptance and Disaster-Recovery Evidence

## Status semantics

Pass 16 separates **release code certification** from **literal operational acceptance**.

- `CODE/DEPLOYMENT PASS` means CI, container parity, production certification, and adversarial certification pass on the deployed commit.
- `OPERATIONAL ACCEPTANCE PASS` may be recorded only after every applicable evidence item below has actually been executed and dated.
- A checklist, script, or CI result is not evidence that a physical peripheral, restore, downstream transaction, or human workflow was tested.

Never record an unexecuted item as passing.

## 1. Staging clone

Use a staging environment isolated from production data and credentials.

- [ ] Staging runs the exact intended release commit.
- [ ] PostgreSQL and Redis are staging-only instances or namespaces.
- [ ] `TARGET_ENVIRONMENT=staging PUBLIC_BASE=<staging-url> EXPECTED_COMMIT=<sha> bash scripts/pass16-staging-certify.sh` passes.
- [ ] Production-equivalent CI and adversarial checks for the same commit are green.
- [ ] Public detailed health remains hidden.

Record staging URL, commit, date/time, operator, and certification output location.

## 2. Backup restore and RTO/RPO

Never restore a production dump over the live database.

- [ ] Identify the production backup used and its creation timestamp.
- [ ] Prepare a clean disposable non-production PostgreSQL database.
- [ ] Run `scripts/pass16-restore-rehearsal.sh` with the explicit non-production confirmation guard.
- [ ] Record `RESTORE_ELAPSED_SECONDS` as measured RTO evidence.
- [ ] Compare backup timestamp with rehearsal start to calculate observed recovery point age.
- [ ] Verify representative users/registers/catalog/orders and reconciliation totals after restore without recording sensitive data in Git.
- [ ] Record backup retention and the business-approved RTO/RPO targets.

## 3. Migration forward/rollback rehearsal

Perform only on a disposable non-production database.

- [ ] Restore or initialize at the previous Alembic head.
- [ ] Upgrade to current head.
- [ ] Run `alembic check` and application readiness.
- [ ] Downgrade to the supported previous revision.
- [ ] Verify expected schema/application behavior at the rollback revision.
- [ ] Upgrade to current head again.
- [ ] Record elapsed time and any manual intervention required.

If a future migration is intentionally irreversible, document the release-specific rollback strategy rather than pretending downgrade is available.

## 4. Downstream staging contracts

Use staging/test identities and disposable transaction references.

For Accounting, Inventory, Staff, and Operations as applicable:

- [ ] authentication succeeds with staging credentials;
- [ ] expected request/response schema is accepted;
- [ ] timeout/unreachable behavior is typed and does not corrupt local selling;
- [ ] retry after recovery succeeds;
- [ ] replay with the same idempotency/external reference does not create a duplicate;
- [ ] downstream record can be reconciled to the POS source reference;
- [ ] no secret/token is included in saved evidence.

Record only non-sensitive IDs, timestamps, response classes, and reconciliation results.

## 5. Physical peripheral acceptance

Execute on the actual supported hardware/network path.

- [ ] customer receipt printer: correct content, totals, cut/feed behavior;
- [ ] kitchen printer, if used: correct station routing and duplicate prevention;
- [ ] cash drawer: opens only at intended workflow points and remains closed for unauthorized actions;
- [ ] card terminal: approved/declined/cancel flow is reconciled without storing cardholder data;
- [ ] KDS: new ticket, update, completion, audible alert opt-in, reconnect;
- [ ] customer display: pair, cart update, payment/final state, revoke/re-pair;
- [ ] peripheral reconnect after device/network interruption.

Record hardware model/identifier at a non-sensitive level, result, operator, and timestamp.

## 6. Offline / dependency recovery

Use staging or an explicitly controlled non-production network path.

- [ ] Accounting unavailable: local selling remains available where designed and degraded state is visible.
- [ ] Redis interruption: strict staging startup/readiness fails closed where Redis is required.
- [ ] sync worker interruption/restart: queued work resumes without duplication.
- [ ] browser/network interruption during an in-progress sale follows the documented recovery path.
- [ ] KDS reconnect leaves active-stream/listener metrics at zero after clients close.
- [ ] all dependencies recover to healthy readiness after restoration.

## 7. Controlled live pilot

This section intentionally mutates production and requires explicit operator authorization. Do not run it merely because the repository contains this checklist.

Use a designated low-volume register/session outside a rush period and record the test references.

- [ ] cashier login and register open;
- [ ] standard sale and single tender;
- [ ] hold/resume;
- [ ] split tender if supported/used;
- [ ] KDS/kitchen progression;
- [ ] customer display/receipt path;
- [ ] Accounting and Inventory consequences appear once;
- [ ] manager approval path for one explicitly authorized disposable reversal/refund/void scenario, if business approval permits;
- [ ] register close/reconciliation;
- [ ] outbox returns to zero failed/blocked/attention-required items.

Do not perform destructive production scenarios without explicit business authorization.

## 8. Role acceptance

Obtain dated acceptance or defects from the people who actually perform the workflows:

- [ ] Owner/Admin
- [ ] Manager/Supervisor
- [ ] Cashier/Reception
- [ ] Kitchen/Bar user
- [ ] Accounting/finance reviewer

For each role record name/role, date, tested workflows, result, defects, and disposition. Store signatures/PII in the organization’s approved evidence location rather than source control if required.

## 9. Final audit rerun

After the above evidence is complete:

- [ ] rerun the same comprehensive route/role/viewport/interaction capture used by the August 27 audit;
- [ ] Axe has zero serious/critical findings across the acceptance matrix;
- [ ] no unexpected 5xx, hydration error, console/page error, stretched panel, clipped initial content, or dead-end denial state remains;
- [ ] npm production audit and locked Python audit have zero known vulnerabilities at the required threshold;
- [ ] all production-equivalent and container gates are green on the deployed commit;
- [ ] reconcile every remaining POS-001 through POS-021 item against current code and evidence.

## Final declaration

Only declare `OPERATIONAL ACCEPTANCE PASS` when all applicable sections above are backed by dated evidence and any exceptions are explicitly accepted by the business owner. Until then, a successfully deployed Pass 16 release is accurately described as **code/deployment certified with operational evidence pending**.
