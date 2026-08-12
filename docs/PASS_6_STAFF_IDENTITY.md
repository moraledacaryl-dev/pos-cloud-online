# Pass 6 — Canonical Staff identity integration

## Objective

Close the employee-identity boundary between Staff/Payroll and POS without turning POS authentication into an HR system.

Staff/Payroll is authoritative for employee identity. POS remains authoritative for its own login credentials, roles, permissions, sessions, register actions, orders, refunds, and cash accountability.

## Receiver contract

Staff/Payroll already sends `employee.sync` to:

`POST /api/integrations/staff/employees`

POS accepts that exact endpoint using `X-Integration-Api-Key` and the POS `STAFF_INTEGRATION_KEY` setting.

Accepted envelope identity is strictly:

- `external_source = hidden_oasis_staff_payroll`
- `event_type = employee.sync`
- employee code
- display name
- department
- position
- employment-role label
- active/inactive status
- primary department
- source Staff employee ID

The schema forbids extra employee fields. Salary, benefits, government IDs, leave details, disciplinary records, private notes, and other HR/payroll data are rejected at the API boundary.

## Identity model

Canonical employees are stored in `staff_identities` and keyed independently by Staff source ID and employee code.

POS authentication users are not generated from Staff records. A separate `pos_user_staff_links` table links one POS login to one canonical employee identity.

Rules:

1. Employee sync never creates a POS password.
2. POS never guesses links by name, username, or department.
3. A Staff identity can be linked to only one POS user.
4. A POS user can be linked to only one Staff identity.
5. Links can be removed without deleting either the POS login or employee history.
6. Employee status changes update the canonical identity; they do not silently rewrite POS roles or credentials.

## Management UI

The Users page shows the canonical Staff identity selector next to POS-local role and login controls. Staff employee code and display name are shown in the user table and included in search.

## Configuration

POS:

```text
STAFF_INTEGRATION_ENABLED=false
STAFF_INTEGRATION_KEY=<shared-secret>
```

Staff/Payroll must use the same secret as `STAFF_PAYROLL_POS_SYNC_TOKEN` and its POS sync URL must resolve to `https://pos.hiddenoasis.app`.

## Rollout order

1. Deploy the POS receiver and migration first with `STAFF_INTEGRATION_ENABLED=false`.
2. Install the same strong shared secret on POS and Staff/Payroll.
3. Set `STAFF_INTEGRATION_ENABLED=true` on POS and restart the backend.
4. Send/retry one Staff employee sync canary.
5. Verify one canonical identity appears in POS without a login being created automatically.
6. Explicitly link that identity to the correct existing POS user.
7. Verify register/order audit accountability still points to the POS user while the management view resolves the canonical Staff identity.
8. Only then expand Staff/Payroll employee sync delivery.

## Pass gate

Pass 6 is code-complete only when backend tests, frontend contract/build checks, migration validation, privacy rejection tests, idempotent sync tests, and one-to-one link tests are green. Production activation remains a separate deployment gate.
