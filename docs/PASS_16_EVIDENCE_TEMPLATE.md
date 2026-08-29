# Pass 16 Evidence Record

> Template only. Copy to the approved operational evidence location for each executed certification. Do not mark items PASS unless they were actually performed.

## Release

- Release commit:
- Environment:
- Date/time (UTC and local):
- Operator:
- CI run IDs:
- Production-equivalent CI run ID:
- Container parity CI run ID:

## Staging certification

- Staging URL:
- Exact commit:
- Automated staging certification: NOT RUN / PASS / FAIL
- Evidence location:

## Backup / restore

- Backup identifier (non-secret):
- Backup creation timestamp:
- Disposable restore target identifier:
- Restore start/end:
- RESTORE_ELAPSED_SECONDS:
- Observed recovery point age:
- Business RTO target:
- Business RPO target:
- Structural/data reconciliation result: NOT RUN / PASS / FAIL
- Evidence location:

## Migration rehearsal

- Previous revision:
- Current revision:
- Forward upgrade: NOT RUN / PASS / FAIL
- Downgrade rehearsal: NOT RUN / PASS / FAIL / NOT APPLICABLE
- Re-upgrade: NOT RUN / PASS / FAIL
- Elapsed time:
- Evidence location:

## Downstream staging contracts

| Integration | Auth/schema | Timeout/degraded | Retry/recovery | Idempotency/replay | Reconciled source ID | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Accounting | NOT RUN | NOT RUN | NOT RUN | NOT RUN |  |  |
| Inventory | NOT RUN | NOT RUN | NOT RUN | NOT RUN |  |  |
| Staff | NOT RUN | NOT RUN | NOT RUN | NOT RUN |  |  |
| Operations | NOT RUN | NOT RUN | NOT RUN | NOT RUN |  |  |

## Physical peripherals

| Peripheral | Result | Model/path | Timestamp | Operator | Evidence / defect |
| --- | --- | --- | --- | --- | --- |
| Receipt printer | NOT RUN |  |  |  |  |
| Kitchen printer | NOT RUN / N/A |  |  |  |  |
| Cash drawer | NOT RUN |  |  |  |  |
| Card terminal | NOT RUN / N/A |  |  |  |  |
| KDS | NOT RUN |  |  |  |  |
| Customer display | NOT RUN |  |  |  |  |

## Offline / recovery

- Accounting outage/recovery: NOT RUN / PASS / FAIL
- Redis required-dependency behavior: NOT RUN / PASS / FAIL
- Sync worker restart/recovery: NOT RUN / PASS / FAIL
- Browser/network interruption recovery: NOT RUN / PASS / FAIL
- KDS disconnect cleanup: NOT RUN / PASS / FAIL
- Evidence location:

## Controlled production pilot

- Explicit business authorization reference:
- Test register/session:
- Pilot order IDs:
- Accounting references:
- Inventory references:
- Controlled reversal/refund/void performed: NO / YES (authorization required)
- Register close/reconciliation result:
- Final outbox failed/blocked/attention counts:
- Overall pilot: NOT RUN / PASS / FAIL

Do not record passwords, API keys, card details, guest-sensitive data, or secret tokens.

## Role acceptance

| Role | Date | Workflows tested | PASS/FAIL | Defects/disposition | Evidence location |
| --- | --- | --- | --- | --- | --- |
| Owner/Admin |  |  | NOT RUN |  |  |
| Manager/Supervisor |  |  | NOT RUN |  |  |
| Cashier/Reception |  |  | NOT RUN |  |  |
| Kitchen/Bar |  |  | NOT RUN |  |  |
| Accounting/Finance |  |  | NOT RUN |  |  |

## Final comprehensive recertification

- Audit rerun date:
- Route/viewport checks:
- Role/access checks:
- Interaction/state checks:
- Axe serious/critical count:
- Unexpected 5xx count:
- Console/unhandled page errors:
- npm production audit:
- locked Python audit:
- Remaining POS-001…POS-021 exceptions:

## Declaration

- CODE/DEPLOYMENT CERTIFIED: YES / NO
- OPERATIONAL ACCEPTANCE: PENDING / PASS / FAIL
- Accepted exceptions:
- Business owner approval/date:
