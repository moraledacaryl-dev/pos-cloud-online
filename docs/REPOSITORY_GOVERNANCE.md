# POS repository governance — owner configuration

**Status (2026-10-22):** GitHub reported `main.protected=false` and no active repository rulesets.
This document does not apply protections automatically. The connected GitHub integration
does not have the repository administration permission needed to enforce them.

## Protect the production code line

In GitHub: **Settings → Rules → Rulesets → New ruleset → New branch ruleset**.

- Name: `protect-pos-main`; enforcement: **Active**; target: branch `main`.
- Require a pull request before merging. If only one maintainer is available,
  approval-count requirements must be calibrated so urgent production fixes
  remain possible; use an independent reviewer when available.
- Require status checks to pass before merging and require branches to be
  up to date before merging. Select checks from a completed `main` run,
  not guessed display names. Minimum mandatory jobs:
  - `Backend tests`
  - `Frontend build and tests`
  - `PostgreSQL, Redis, Alembic, worker, abuse tests`
  - `Dependency security scans`
  - `Playwright browser E2E + Axe`
  - `Pass 16 isolated staging runtime` workflow job(s), if present in GitHub's selector.
  The remaining Inventory/Accounting replay, synthetic restore, container
  parity, roles, and visual workflows should also be required when reliable
  and selected by their actual GitHub job check names.
- Block force pushes and branch deletion. Do not give routine automation
  broad bypass privileges. Limit ruleset edits to repository administrators.
- Where the GitHub plan supports it, require resolved PR conversations.
- Keep production deployments **manual** via `workflow_dispatch`, restricted
  GitHub `production` environment approval and the exact 40-character SHA.
  Verify the environment's reviewer, branch/tag and secrets settings in
  **Settings → Environments → production**; a workflow declaring an environment
  is not itself proof that approval is required.

## Non-destructive verification

1. Confirm `main` shows as protected in GitHub or that an **active** ruleset
   targets the branch.
2. Open a trivial test PR with one intentionally failing required check.
   Verify GitHub blocks merge; do not merge this test PR.
3. Attempt to edit a tracked file directly on `main` using a non-admin
   development identity; GitHub should reject the push. Do not test with
   production secrets or financial data.
4. Verify a production workflow dispatch requires the intended environment
   approvals; cancel the test before server modifications.
5. Confirm ordinary passing PRs remain mergeable and the emergency break-glass
   procedure is documented and audited.

## Release and data-safety invariants

- Never test idempotency or stock changes using fake payments on production.
- Changes to payment, refunds, inventory events, migrations and authorization
  require production-equivalent CI and targeted regression tests.
- Successful deployment and synthetic outage tests **do not** close [operational
  acceptance issue #99](https://github.com/moraledacaryl-dev/pos-cloud-online/issues/99).
- Preserve the development-only dependency advisory [#75](https://github.com/moraledacaryl-dev/pos-cloud-online/issues/75)
  until the full tree can be patched without downgrading Next.js.
