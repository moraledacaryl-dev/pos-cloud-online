# Exact-SHA production release CI gate

## Purpose

A manually dispatched POS production deployment must **not** rely only on
the shorter `verify-release` frontend/backend test pair. That pair is kept as
an additional check, but is insufficient evidence that real-database,
recovery, Accounting, Inventory and role-security tests passed.

`scripts/verify-release-ci.py` is a **read-only, fail-closed** check that runs
inside `.github/workflows/deploy-pos.yml` immediately after the 40-character
release SHA validation and **before any SSH, backup, migration or service
change**. The GitHub Actions token has `actions: read`, not administration
permissions.

For a **production** release the script requires:

1. `release_sha` is identical to the dispatch workflow's `github.sha`.
2. The dispatch ref is `refs/heads/main`.
3. For each of the eight mandatory workflows, GitHub reports a `push` run
   on branch `main` and exactly that 40-character SHA.
4. The **newest** eligible run for each workflow is `completed/success`.
   A newer failure, cancellation, queued run or incomplete rerun blocks the
   release; an older success cannot mask it.
5. The API response is well formed and within the single-response limit.
   Missing evidence, API errors, permission failures or timeouts block
   production deployment without contacting the POS server.

Mandatory workflows:

- `ci.yml`
- `production-equivalent-ci.yml`
- `container-parity-ci.yml`
- `role-matrix-recertification.yml`
- `pass16-staging-ci.yml`
- `pass16-restore-ci.yml`
- `pass16-accounting-replay-ci.yml`
- `pass16-inventory-replay-ci.yml`

The separate `visual-audit-screenshots.yml` is path-filtered and
dispatchable; it is not an always-on `main` push requirement. Maintain its
separate user-facing visual acceptance workflow.

## Safe verification

- Run `PYTHONPATH=backend pytest -q backend/tests/test_release_ci_gate.py` in
  a test environment after installing backend dev requirements. These
  contract tests have no network or server side effects.
- Run the normal eight CI workflows on the **merged** SHA.
- A production deployment of any older commit or commit lacking one required
  green workflow must fail before the SSH step.
- A staging deployment is intentionally **not** subject to the production
  main-branch gate, allowing staged validation of unmerged work; staging
  continues to rely on the pre-existing target isolation and remote safety
  checks.

## Boundaries

- CI status is evidence of automated tests, not proof of genuine cashier
  acceptance or accounting reconciliation. Operational acceptance issue #99
  remains open until real-world evidence is captured.
- This gate is defense in depth, **not GitHub branch protection**. Owners
  must still enforce repository rulesets and production environment approvals
  (issue #107).
- This gate never overrides the Accounting-availability production setting;
  the existing strict `allow_accounting_unavailable=false` default remains.
- No real orders, payments, inventory events or Accounting journals are
  created by this gate.
