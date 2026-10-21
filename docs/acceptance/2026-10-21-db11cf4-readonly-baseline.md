# Pass 16 — Read-only deployment evidence baseline (2026-10-21)

**Purpose:** Preserve independently traceable, non-sensitive GitHub Actions evidence for the exact deployed release. This record does **not** certify unexecuted operational checks and is **not** a business-owner sign-off.

## Release identity and provenance

| Field | Observed evidence |
| --- | --- |
| Repository / branch at inspection | `moraledacaryl-dev/pos-cloud-online` / `main` |
| Main and certified production release SHA | `db11cf4f967297ec91afc284d39102aaa4d6ca0b` |
| GitHub inspection date | 2026-10-21 (Philippines, UTC+08:00) |
| Last deployment certification timestamp | 2026-10-21 09:43:41 UTC / 17:43:41 PHT |
| Deploy workflow | [Deploy POS #39578885679](https://github.com/moraledacaryl-dev/pos-cloud-online/actions/runs/39578885679), `completed / success` |
| Deployment artifact | [Artifact #12334893973](https://github.com/moraledacaryl-dev/pos-cloud-online/actions/runs/39578885679/artifacts/12334893973), `pos-deployment-production-db11cf4f967297ec91afc284d39102aaa4d6ca0b` |
| Artifact SHA-256 digest reported by GitHub | `a3ea86831a229474b873c1a0b1f7c01bd5e24aba0bc360f5c327def48e89873c` |
| Deployment mode | `allow_accounting_unavailable=false` |
| Deploy script recorded | `result=passed`, `certification=passed`, `backup=completed-before-deploy` |

This is a point-in-time log check, **not continuous production monitoring**. The deployment log's `backup=completed-before-deploy` asserts only that a pre-deploy backup step completed; it does **not** prove a successful backup restoration, integrity reconciliation, or RTO/RPO.

## Automated quality gates — exact release SHA

| Workflow | Run | Result |
| --- | --- | --- |
| CI | [#39578300493](https://github.com/moraledacaryl-dev/pos-cloud-online/actions/runs/39578300493) | `completed / success` |
| Production-equivalent CI | [#39578300485](https://github.com/moraledacaryl-dev/pos-cloud-online/actions/runs/39578300485) | `completed / success` |
| Container parity CI | [#39578300562](https://github.com/moraledacaryl-dev/pos-cloud-online/actions/runs/39578300562) | `completed / success` |
| Role matrix recertification | [#39578300546](https://github.com/moraledacaryl-dev/pos-cloud-online/actions/runs/39578300546) | `completed / success` |

Deployment job [`deploy` #119151752017](https://github.com/moraledacaryl-dev/pos-cloud-online/actions/runs/39578885679/job/119151752017) reports:

- Exact Git checkout matched the release SHA; working tree clean.
- `pos-backend`, `pos-frontend`, and `pos-sync-worker` active.
- Local core health/readiness, public homepage, `/healthz`, `/readyz`, and public integration readiness returned HTTP 200 at certification.
- Public detailed health endpoint was **not** exposed.
- Production health payload reported fully ready, without the Accounting-unavailable exception.
- Outbox summary: `total=8, pending=0, failed=0, blocked=0, attention_required=0`; oldest unresolved age `null`.
- Alembic revision commands and nginx configuration test passed.
- `AUTOMATED PRODUCTION CERTIFICATION: PASS`; `DEPLOY PASS: db11cf4f967297ec91afc284d39102aaa4d6ca0b`.
- The deployment verification output reported 365 backend tests passed, 3 skipped; 94 frontend tests passed, 0 failed. These are counts from the deployment job, not independent fresh test runs.

## Security tracking

- The exact release's CI has a successful `npm audit --omit=dev --audit-level=high` gate. This is a **CI result**, not a fresh standalone production filesystem audit.
- [Issue #75](https://github.com/moraledacaryl-dev/pos-cloud-online/issues/75) remains **OPEN**, tracking dev-only `braces@3.0.3` / `GHSA-vfj7-8cjw-p6xm`.
- At this review, the checked-in lockfile locates `eslint-config-next@16.4.0 -> @next/eslint-plugin-next@16.4.0 -> fast-glob@3.3.1 -> micromatch@4.0.8 -> braces@3.0.3`; the guard asserts the chain is `dev=true`. The advisory [currently lists no patched version](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm). No unaudited override or force downgrade is authorized.
- This record does **not** claim that a full current `npm audit`, Node 24 `npm ls`, actual shipped-image package inspection, or independent npm registry audit was executed in this review.

## Outstanding operational acceptance — not tested by this record

| Pass 16 requirement | Result as of this evidence capture |
| --- | --- |
| Isolated staging clone, exact SHA and `pass16-staging-certify.sh` | **NOT TESTED** |
| Disposable PostgreSQL backup restore / measured RTO and RPO | **NOT TESTED** |
| Isolated migration forward / downgrade / re-upgrade | **NOT TESTED** |
| Staging Accounting / Inventory / Staff / Operations replay and reconciliation | **NOT TESTED** |
| Physical receipt/kitchen printers, cash drawer and optional card terminal | **NOT TESTED** |
| Actual KDS and customer display hardware/browser workflow | **NOT TESTED** |
| Network/offline/Redis/worker interruption and recovery rehearsal | **NOT TESTED** |
| Controlled production sale/hold/split tender/reversal and reconciliation | **NOT TESTED — owner approval required** |
| Dated owner, manager, cashier, kitchen and finance acceptance | **NOT TESTED / NOT SIGNED** |
| New screenshots at 1440/1024/390/320, complete Axe and interaction checks | **NOT TESTED in this review** |

**Scope control:** No production order, money movement, stock consequence, database modification, restoration or production pilot occurred in preparing this record. Automated job results do not substitute for hardware tests or user acceptance. Pre-existing screenshots and earlier GitHub Actions remain independently inspectable but were not freshly captured here.

## Decision and next action

- **CODE/DEPLOYMENT CERTIFIED for deployed SHA:** **YES** (based on run #39578885679 and exact-release CI evidence).
- **OPERATIONAL ACCEPTANCE:** **PENDING**.
- **Next non-destructive work:** an isolated staging certification and disposable backup-restore rehearsal with real timings and evidence, when staging resources and secure backup inputs are available. Perform hardware checks with the actual terminal; schedule any production transaction pilot only on explicit business-owner authorization.
- Keep issue #75 open until a compatible fix or upstream replacement is tested. Continue the existing production dependency security gate; do not change financial/Inventory source-of-truth semantics.

See [Pass 16 checklist](../PASS_16_OPERATIONAL_ACCEPTANCE.md) and [evidence template](../PASS_16_EVIDENCE_TEMPLATE.md). This baseline is limited to the evidence sources explicitly linked above.
