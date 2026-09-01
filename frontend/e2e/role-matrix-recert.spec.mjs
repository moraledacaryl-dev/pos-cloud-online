import { test, expect } from '@playwright/test';

const ROUTES = [
  '/dashboard',
  '/pos',
  '/kitchen',
  '/kitchen-board',
  '/bar',
  '/expo',
  '/orders',
  '/registers',
  '/sessions',
  '/cash-movements',
  '/room-charges',
  '/catalog',
  '/recipes',
  '/sync',
  '/settings',
  '/users',
  '/audit',
];

const ROLE_CASES = [
  {
    role: 'owner',
    username: process.env.E2E_OWNER_USERNAME || 'ci-owner',
    password: process.env.E2E_OWNER_PASSWORD || 'CiOwnerPassword-2026!',
    allowed: new Set(ROUTES),
  },
  {
    role: 'manager',
    username: process.env.E2E_MANAGER_USERNAME || 'ci-manager',
    password: process.env.E2E_MANAGER_PASSWORD || 'CiManagerPassword-2026!',
    allowed: new Set(ROUTES.filter((route) => route !== '/users')),
  },
  {
    role: 'cashier',
    username: process.env.E2E_CASHIER_USERNAME || 'ci-cashier',
    password: process.env.E2E_CASHIER_PASSWORD || 'CiCashierPassword-2026!',
    allowed: new Set([
      '/dashboard', '/pos', '/orders', '/registers', '/sessions', '/cash-movements',
      '/room-charges', '/catalog', '/recipes',
    ]),
  },
  {
    role: 'kitchen',
    username: process.env.E2E_KITCHEN_USERNAME || 'ci-kitchen',
    password: process.env.E2E_KITCHEN_PASSWORD || 'CiKitchenPassword-2026!',
    allowed: new Set([
      '/dashboard', '/kitchen', '/kitchen-board', '/bar', '/expo', '/catalog', '/recipes',
    ]),
  },
];

async function login(page, username, password) {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login'),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ]);
}

for (const roleCase of ROLE_CASES) {
  test(`${roleCase.role} route authorization matrix is correct and free of runtime failures`, async ({ page }) => {
    const pageErrors = [];
    const unexpectedServerFailures = [];
    page.on('pageerror', (error) => pageErrors.push(String(error)));
    page.on('response', (response) => {
      if (response.status() < 500) return;
      const url = new URL(response.url());
      const expectedAccountingOutage = response.status() === 503 && url.pathname === '/api/registers/accounting-accounts';
      if (!expectedAccountingOutage) unexpectedServerFailures.push(`${response.status()} ${response.url()}`);
    });

    await login(page, roleCase.username, roleCase.password);

    for (const route of ROUTES) {
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(100);
      const denial = page.locator('[data-route-status="403"]');
      if (roleCase.allowed.has(route)) {
        await expect(denial, `${roleCase.role} should be allowed on ${route}`).toHaveCount(0);
      } else {
        await expect(denial, `${roleCase.role} should be denied on ${route}`).toBeVisible();
      }
    }

    await page.goto('/definitely-not-a-pos-route', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-route-status="403"]'), `${roleCase.role} unknown route must not be misclassified as 403`).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Page Not Found' })).toBeVisible();

    expect(pageErrors, `${roleCase.role} had unhandled page errors`).toEqual([]);
    expect(unexpectedServerFailures, `${roleCase.role} encountered unexpected 5xx responses`).toEqual([]);
  });
}
