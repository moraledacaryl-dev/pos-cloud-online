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

### Automated isolated staging-runtime rehearsal (CI only)

The `Pass 16 isolated staging runtime` GitHub Actions workflow provisions ephemeral PostgreSQL 16 and Redis 7, runs the POS backend under its real `ENVIRONMENT=staging` security policy, starts the sync worker and production-built frontend, and verifies the read-only health/readiness surfaces through a local public proxy. It rejects production-origin URL variants and mismatched commit SHAs; it requires direct staging runtime identity, migration head/schema checks, strict worker/dependency readiness, and hidden private operational endpoints. The workflow may use `PUBLIC_API_PREFIX=/api` for the isolated CI proxy. Real deployed staging typically uses the default empty prefix.

This is a **staging-equivalent code/runtime gate on a disposable CI runner**, not a persistent independently deployed staging clone. Do not mark the staging clone checklist complete until the separate staging environment's exact commit, database/Redis isolation, restricted credentials, operator and URL are verified and its own certification is actually executed. Do not put production credentials, backups, financial transactions or real downstream data into CI. The certification command now requires `EXPECTED_COMMIT` to be the full 40-character release SHA and refuses to skip Alembic verification.


## 2. Backup restore and RTO/RPO

Never restore a production dump over the live database.

- [ ] Identify the production backup used and its creation timestamp.
- [ ] Prepare a clean disposable non-production PostgreSQL database.
- [ ] Run `scripts/pass16-restore-rehearsal.sh` with the explicit non-production confirmation guard.
- [ ] Record `RESTORE_ELAPSED_SECONDS` as measured RTO evidence.
- [ ] Compare backup timestamp with rehearsal start to calculate observed recovery point age.
- [ ] Verify representative users/registers/catalog/orders and reconciliation totals after restore without recording sensitive data in Git.
- [ ] Record backup retention and the business-approved RTO/RPO targets.

### Automated synthetic restore smoke test (separate from operational evidence)

The `Pass 16 isolated synthetic restore` GitHub Actions workflow creates **only test fixtures** in ephemeral PostgreSQL 16, makes a custom-format dump, restores it into a disposable database, checks the current Alembic revision and hashes the restored synthetic paid order, cash/GCash split tenders, line, cash movement, audit and outbox records against the source. It also corrupts a tender on the disposable restored database to prove mismatches fail, then restores its original value. The workflow exercises the restore script's fail-closed guards. Its result is code-level **restore procedure and synthetic financial-content validation**, not evidence that an actual production backup is recoverable. The fixture is SQL-seeded for recovery testing and does not claim to execute the live cashier checkout process. Do **not** use a production dump in GitHub Actions, upload it as an artifact, or put production credentials into the runner.

For a real approved restore rehearsal on isolated infrastructure, set all of these explicitly before running `scripts/pass16-restore-rehearsal.sh`:

- `BACKUP_FILE`: path to a locally secured, authorized PostgreSQL custom-format backup;
- `NON_PRODUCTION_CONFIRM=I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET`;
- `TARGET_DATABASE_URL`: a connection URI to a **new empty** loopback PostgreSQL database whose name starts with `pos_pass16_restore_` (for example `postgresql://user@127.0.0.1:5432/pos_pass16_restore_drill`);
- `EXPECTED_HEAD`: the specific Alembic revision expected **inside that backup**, such as `0013_generic_selling_rules` for the current schema; this must be reviewed for every new release rather than inheriting a stale default.

The runner blocks missing confirmation, missing expected head, unsafe target names/hosts and non-empty public schemas. Localhost checks alone cannot establish that an SSH tunnel or a database operator has not redirected the connection: verify infrastructure routing, isolation and disposable nature of the **actual database** before giving confirmation. A successful synthetic drill does not satisfy this checklist's measured production-derived RTO/RPO or restored-business-data reconciliation.

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

### Accounting HTTP failure, retry, and replay (synthetic CI only)

The `Pass 16 Accounting HTTP outage and replay` GitHub Actions workflow uses an ephemeral PostgreSQL 16 database and a loopback-only synthetic Accounting intake to exercise the **actual POS outbox transport** (not a mocked Python client). It verifies: 503 before downstream acceptance; local order and outbox preserved for retry; acceptance after recovery; downstream acceptance followed by a deliberately lost HTTP acknowledgement (503); replay with a stable `external_id`; exactly one downstream sale per source order; and no further send after an event reaches `synced`. Unknown intake routes return 404 rather than fake success. This uses only synthetic POS orders and never connects to production Accounting.

This is **transport/idempotency regression evidence**, not certification of the actual Accounting staging API, its authentication, ledger postings, Inventory stock movements, or downstream reconciliation. Those requirements remain NOT RUN until tested against appropriate isolated staging services with recorded source references.

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
