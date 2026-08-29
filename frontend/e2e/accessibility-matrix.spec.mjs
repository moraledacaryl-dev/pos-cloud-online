import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const ownerUsername = process.env.E2E_OWNER_USERNAME || 'ci-owner';
const ownerPassword = process.env.E2E_OWNER_PASSWORD || 'CiOwnerPassword-2026!';
const cashierUsername = process.env.E2E_CASHIER_USERNAME || 'ci-cashier';
const cashierPassword = process.env.E2E_CASHIER_PASSWORD || 'CiCashierPassword-2026!';

const OWNER_ROUTES = [
  '/dashboard',
  '/kitchen',
  '/kitchen-board',
  '/bar',
  '/expo',
  '/orders',
  '/registers',
  '/sessions',
  '/cash-movements',
  '/catalog',
  '/recipes',
  '/room-charges',
  '/audit',
  '/sync',
  '/settings',
  '/users',
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

async function keyboardLogin(page, username, password) {
  await page.goto('/login');
  await page.getByLabel('Username').focus();
  await page.keyboard.type(username);
  await page.getByLabel('Password').focus();
  await page.keyboard.type(password);
  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login'),
    page.keyboard.press('Enter'),
  ]);
}

async function seriousAxeViolations(page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  return result.violations.filter((violation) => ['serious', 'critical'].includes(violation.impact));
}

async function scanRoute(page, route) {
  const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
  expect(response?.status(), `${route} returned an unexpected HTTP status`).toBeLessThan(400);
  await page.waitForTimeout(150);
  expect(await seriousAxeViolations(page), `serious/critical Axe violations on ${route}`).toEqual([]);
}

test.describe.serial('Pass 13 full-route accessibility matrix', () => {
  test('owner desktop routes have zero serious or critical Axe violations', async ({ page }) => {
    await login(page, ownerUsername, ownerPassword);
    for (const route of OWNER_ROUTES) await scanRoute(page, route);
  });

  test('owner mobile routes have zero serious or critical Axe violations', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, ownerUsername, ownerPassword);
    for (const route of OWNER_ROUTES) await scanRoute(page, route);
  });

  test('login is completable without pointer input and terminal semantics remain valid', async ({ page }) => {
    await keyboardLogin(page, ownerUsername, ownerPassword);
    await page.goto('/pos', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(150);
    await expect(page.getByRole('heading', { level: 1, name: 'Point of Sale' })).toBeAttached();
    expect(await seriousAxeViolations(page), 'serious/critical Axe violations on keyboard-entered POS').toEqual([]);
  });

  test('cashier denied states remain keyboard recoverable and Axe-clean', async ({ page }) => {
    await keyboardLogin(page, cashierUsername, cashierPassword);
    await page.goto('/users', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-route-status="403"]')).toBeVisible();
    await page.getByRole('button', { name: 'Open my workspace' }).focus();
    await expect(page.getByRole('button', { name: 'Open my workspace' })).toBeFocused();
    expect(await seriousAxeViolations(page), 'serious/critical Axe violations on cashier denial state').toEqual([]);
  });
});
