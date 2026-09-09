# POS visual-audit screenshot harness

This harness produces deterministic screenshot evidence for the POS frontend without using production transactions or production credentials.

## Coverage

Full mode captures the protected route matrix for these roles:

- owner
- manager
- cashier
- kitchen

Protected routes:

- `/dashboard`
- `/pos`
- `/kitchen`
- `/kitchen-board`
- `/bar`
- `/expo`
- `/orders`
- `/registers`
- `/sessions`
- `/cash-movements`
- `/room-charges`
- `/catalog`
- `/recipes`
- `/sync`
- `/settings`
- `/users`
- `/audit`

Viewports:

- desktop: 1440 × 1000
- tablet: 1024 × 768
- mobile: 390 × 844

For every role/route combination the harness records the actual allowed page or the expected 403 access-restricted page. Full-page and viewport screenshots are both captured by default.

Additional states include:

- empty login
- invalid login
- unauthenticated protected-route access
- customer display waiting for pairing
- customer display management/setup
- real 404 page
- mobile navigation drawer open for each authenticated role
- POS initial workspace
- POS browser-offline state
- dependency/network-failure views for dashboard, POS, orders, and sync

## Output

Screenshots are written under:

```text
frontend/visual-audit/<role>/<viewport>/<route>/<state>--viewport.png
frontend/visual-audit/<role>/<viewport>/<route>/<state>--full.png
```

`frontend/visual-audit/manifest.json` records every capture with:

- role
- viewport
- route
- state
- screenshot kind
- relative file path
- final browser URL
- scenario note

This manifest is the canonical index for automated review and prevents ambiguity between visually similar screens.

## GitHub Actions

Run **Visual audit screenshots** manually and select:

- `full` for the complete matrix
- `smoke` for a small owner/cashier desktop/mobile validation set

The workflow starts isolated PostgreSQL, Redis, backend, frontend, and proxy services. It provisions disposable role accounts, runs Playwright, and uploads the screenshots and manifest as a GitHub Actions artifact for 14 days.

Pull requests that change the screenshot harness automatically run smoke mode so broken selectors or capture logic cannot merge unnoticed.

## Local / server command

Once an isolated test stack is already running at the configured `E2E_BASE_URL` with the four E2E users provisioned:

```bash
cd frontend
VISUAL_AUDIT_MODE=full npm run test:visual-audit
```

Useful filters:

```bash
VISUAL_AUDIT_MODE=full \
VISUAL_AUDIT_ROLES=owner,cashier \
VISUAL_AUDIT_VIEWPORTS=desktop,mobile \
npm run test:visual-audit
```

To reduce artifact size:

```bash
VISUAL_AUDIT_FULL_PAGE=false npm run test:visual-audit
```

## Safety

The workflow is intended for isolated/disposable data only. It must not be pointed at production for scenario capture. Some states intentionally submit an invalid login and intentionally abort API calls; the harness also exercises authenticated role navigation. Keep production screenshot collection read-only and use a separate workflow if production evidence is ever required.
