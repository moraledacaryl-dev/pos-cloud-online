# Pass 12 — Production Acceptance and Certification

## Purpose

Pass 12 is the final certification pass. It does not add business features. It proves that the hardened POS release can be deployed, observed, reconciled, and operated safely.

## Automated certification

Run from the production server after deploying the intended `main` commit:

```bash
cd /opt/pos-cloud-online
EXPECTED_COMMIT=<expected-main-sha> bash scripts/production-certify.sh
```

The script is intentionally read-only. It verifies:

- clean Git checkout and expected commit;
- `pos-backend`, `pos-frontend`, and `pos-sync-worker` are active;
- local backend liveness/readiness and frontend HTTP response;
- public homepage, liveness, detailed health, core readiness, and integration readiness;
- database migration readiness from the production health payload;
- fresh sync-worker heartbeat;
- Accounting reachability;
- zero failed/blocked/attention-required outbox events;
- configured integration reachability;
- Alembic current/head commands;
- Nginx configuration validity when Nginx is available.

Automated certification must fail closed if a required production condition is not satisfied.

## CI release gate

Before merge to `main`, the repository CI must pass:

1. complete backend pytest suite;
2. frontend contract tests;
3. production Next.js build;
4. Pass 12 production-certification contract tests.

CI validates code in isolated test environments. The production certification script validates the deployed host. Neither substitutes for the controlled live pilot below.

## Controlled live pilot

Use one clearly identified test cashier/register and small-value test items. Do not perform destructive production experiments during service. Record order numbers, external references, and observed downstream records.

### 1. Login and register

- [ ] Log in as a normal cashier account.
- [ ] Confirm the account has the intended Staff identity link where configured.
- [ ] Open the designated test register/session with a known opening float.
- [ ] Confirm another cashier cannot silently take over the same drawer contrary to policy.

### 2. Standard sale

- [ ] Create a small standard order.
- [ ] Send items to the correct kitchen/bar station.
- [ ] Confirm kitchen/expo state progresses correctly.
- [ ] Complete payment with one tender.
- [ ] Confirm receipt/order totals match exactly.
- [ ] Confirm only one finalized order exists after a deliberate rapid double-click attempt.

### 3. Hold/resume and split tender

- [ ] Create a second order and hold it.
- [ ] Resume it and verify the cart is unchanged.
- [ ] Pay using two tenders whose total exactly equals the order total.
- [ ] Confirm duplicate tender references are rejected where applicable.

### 4. Inventory handoff

- [ ] Confirm the finalized sale appears once in Inventory & Procurement POS consumption.
- [ ] Confirm mapped recipe/stock consumption is correct.
- [ ] Confirm no duplicate legacy Accounting inventory consumption occurs.
- [ ] Record the Inventory event/idempotency reference.

### 5. Accounting handoff

- [ ] Confirm the sale/review record appears once in Accounting.
- [ ] Confirm tender/cashflow details match the POS payment.
- [ ] Confirm replay/retry does not create a duplicate Accounting transaction.
- [ ] Record the Accounting external/reference ID.

### 6. Refund

- [ ] Use an eligible test order and perform a controlled refund.
- [ ] Confirm refund amount cannot exceed the eligible paid amount.
- [ ] Confirm Accounting receives exactly one refund consequence.
- [ ] For a fully refunded order, confirm Inventory receives the intended reversal once.
- [ ] Do not expect a full stock reversal for a partial refund unless quantity-aware partial reversal is explicitly supported.

### 7. Void/reversal

- [ ] Create a disposable test order appropriate for voiding.
- [ ] Execute the void using the required manager authorization.
- [ ] Confirm the audit record contains actor, reason, and approval context.
- [ ] Confirm the worker delivers the Accounting Review Inbox void event once.
- [ ] Confirm Inventory reversal behavior is correct for the void.

### 8. Cash movement and close

- [ ] Record one approved test cash movement if policy allows.
- [ ] Confirm note/reference/approval requirements are enforced for controlled outflows.
- [ ] Close the test register with a counted amount.
- [ ] Confirm expected cash, actual cash, and variance are visible and correct.
- [ ] Confirm Accounting reconciliation receives the close result once.

### 9. Room charge

- [ ] Create a controlled room-charge order against a valid active booking.
- [ ] Confirm the room charge remains pending until front-desk posting evidence is supplied.
- [ ] Save the Beds24 posting reference.
- [ ] Confirm posted/settled transition rules reject invalid shortcuts.
- [ ] Confirm final status cannot be casually edited after settlement/rejection/write-off.

### 10. Failure/recovery observation

Do not intentionally break production dependencies. Use a controlled service restart only if operationally safe.

- [ ] Restart `pos-sync-worker` once outside a rush period.
- [ ] Confirm `/readyz/integrations` temporarily reflects worker staleness only if the heartbeat exceeds its threshold.
- [ ] Confirm the worker resumes and readiness returns healthy.
- [ ] Confirm no failed or blocked outbox event remains afterward.

### 11. Backup/restore readiness

- [ ] Confirm the current PostgreSQL backup mechanism/timer exists and last backup completed successfully.
- [ ] Confirm backup retention is sufficient for the business requirement.
- [ ] Record the latest verified restore-test date.
- [ ] If no restore test has ever been demonstrated, certification remains conditional until a restore is proven on a non-production database/server.

### 12. Final acceptance

Certification is `PASS` only when:

- automated production certification passes;
- GitHub CI is green on the deployed commit;
- database migration is current;
- no critical/high-severity application defect is open for the release;
- no unreconciled POS/Inventory/Accounting duplicate or missing transaction is found in the pilot;
- the controlled pilot scenarios applicable to the business pass;
- backup restoration has been demonstrated or is explicitly recorded as the sole remaining conditional infrastructure item.

## Evidence record

Record at minimum:

- deployed commit SHA;
- certification date/time;
- operator;
- test register/session ID;
- pilot order IDs;
- Inventory event IDs;
- Accounting external/reference IDs;
- room-charge reference if tested;
- final outbox counts;
- backup/restore evidence date;
- defects found and disposition.

Do not store passwords, API keys, integration secrets, card details, or sensitive guest data in the evidence record.
