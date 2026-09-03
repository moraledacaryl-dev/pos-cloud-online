import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const ownerUsername = process.env.E2E_OWNER_USERNAME || 'ci-owner';
const ownerPassword = process.env.E2E_OWNER_PASSWORD || 'CiOwnerPassword-2026!';
const cashierUsername = process.env.E2E_CASHIER_USERNAME || 'ci-cashier';
const cashierPassword = process.env.E2E_CASHIER_PASSWORD || 'CiCashierPassword-2026!';

async function login(page, username, password) {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login'),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ]);
  await expect(page.locator('body')).not.toContainText('Authentication Required');
}

async function browserJson(page, method, path, body) {
  return page.evaluate(async ({ method, path, body }) => {
    const csrfRow = document.cookie.split(';').map((value) => value.trim()).find((value) => value.startsWith('pos_csrf='));
    const csrf = csrfRow ? decodeURIComponent(csrfRow.slice('pos_csrf='.length)) : '';
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method) && csrf) headers['X-CSRF-Token'] = csrf;
    const response = await fetch(`/api${path}`, {
      method,
      credentials: 'same-origin',
      cache: 'no-store',
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await response.json(); } catch {}
    return { status: response.status, data };
  }, { method, path, body });
}

async function seriousAxeViolations(page) {
  const result = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  return result.violations.filter((violation) => ['serious', 'critical'].includes(violation.impact));
}

test.describe.serial('production-equivalent browser acceptance', () => {
  test('browser auth uses HttpOnly cookies, rotates refresh, and logs out cleanly', async ({ page, context }) => {
    await login(page, ownerUsername, ownerPassword);

    const storage = await page.evaluate(() => ({
      access: localStorage.getItem('pos_token'),
      refresh: localStorage.getItem('pos_refresh_token'),
    }));
    expect(storage).toEqual({ access: null, refresh: null });

    const before = await context.cookies();
    const access = before.find((cookie) => cookie.name === 'pos_access');
    const refresh = before.find((cookie) => cookie.name === 'pos_refresh');
    const csrf = before.find((cookie) => cookie.name === 'pos_csrf');
    expect(access?.httpOnly).toBe(true);
    expect(refresh?.httpOnly).toBe(true);
    expect(csrf?.httpOnly).toBe(false);

    const oldRefresh = refresh?.value;
    const rotated = await browserJson(page, 'POST', '/auth/refresh');
    expect(rotated.status).toBe(200);
    const afterRefresh = await context.cookies();
    expect(afterRefresh.find((cookie) => cookie.name === 'pos_refresh')?.value).not.toBe(oldRefresh);

    await Promise.all([
      page.waitForURL((url) => url.pathname === '/login'),
      page.getByRole('button', { name: 'Logout' }).click(),
    ]);
    const afterLogout = await context.cookies();
    expect(afterLogout.some((cookie) => cookie.name === 'pos_access')).toBe(false);
    expect(afterLogout.some((cookie) => cookie.name === 'pos_refresh')).toBe(false);
  });

  test('mobile drawer is keyboard-safe and returns focus to the opener', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await login(page, ownerUsername, ownerPassword);

    // Use a DOM-identity-stable locator because the accessible name correctly
    // changes from "Open navigation menu" to "Close navigation menu" while open.
    const opener = page.locator('button.mobile-menu-button');
    await expect(opener).toBeVisible();
    await expect(opener).toHaveAttribute('aria-label', 'Open navigation menu');
    await opener.click();
    await expect(opener).toHaveAttribute('aria-expanded', 'true');
    await expect(opener).toHaveAttribute('aria-label', 'Close navigation menu');
    await expect(page.locator('#primary-navigation')).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(opener).toHaveAttribute('aria-expanded', 'false');
    await expect(opener).toHaveAttribute('aria-label', 'Open navigation menu');
    await expect(opener).toBeFocused();
  });

  test('known unauthorized route is 403 UI while unknown route remains a real 404', async ({ page }) => {
    await login(page, cashierUsername, cashierPassword);

    await page.goto('/users');
    await expect(page.locator('[data-route-status="403"]')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Access Restricted' })).toBeVisible();

    const response = await page.goto('/pass9-route-that-does-not-exist');
    expect(response?.status()).toBe(404);
    await expect(page.getByRole('heading', { name: /Page Not Found/i })).toBeVisible();
  });

  test('customer display pairing is one-use, channel-bound, and revocable', async ({ browser, page }) => {
    await login(page, ownerUsername, ownerPassword);
    const pairing = await browserJson(page, 'POST', '/customer-display/pairing-code', { channel: 'ci-display' });
    expect(pairing.status).toBe(200);
    expect(pairing.data?.pairing_code).toBeTruthy();

    const displayContext = await browser.newContext();
    const displayPage = await displayContext.newPage();
    await displayPage.goto('/customer-display?channel=ci-display');
    await expect(displayPage.getByRole('heading', { name: 'Connect this display' })).toBeVisible();
    await displayPage.getByLabel('Pairing code').fill(pairing.data.pairing_code);
    await displayPage.getByRole('button', { name: 'Pair display' }).click();
    await expect(displayPage.getByRole('heading', { name: 'Ready when you are' })).toBeVisible();

    const displayCookies = await displayContext.cookies();
    const displayCredential = displayCookies.find((cookie) => cookie.name === 'pos_display');
    expect(displayCredential?.httpOnly).toBe(true);

    const wrongChannel = await displayPage.evaluate(async () => {
      const response = await fetch('/api/customer-display/not-ci-display', { credentials: 'same-origin', cache: 'no-store' });
      return response.status;
    });
    expect(wrongChannel).toBe(403);

    const replayContext = await browser.newContext();
    const replayPage = await replayContext.newPage();
    await replayPage.goto('/customer-display?channel=ci-display');
    const replay = await replayPage.evaluate(async (pairingCode) => {
      const response = await fetch('/api/customer-display/activate', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pairing_code: pairingCode }),
      });
      return response.status;
    }, pairing.data.pairing_code);
    expect(replay).toBe(401);
    await replayContext.close();

    const devices = await browserJson(page, 'GET', '/customer-display/devices');
    expect(devices.status).toBe(200);
    const device = devices.data.find((row) => row.channel === 'ci-display' && row.is_active);
    expect(device?.device_uuid).toBeTruthy();
    const revoked = await browserJson(page, 'POST', `/customer-display/devices/${device.device_uuid}/revoke`, {});
    expect(revoked.status).toBe(200);

    const afterRevoke = await displayPage.evaluate(async () => {
      const response = await fetch('/api/customer-display/ci-display', { credentials: 'same-origin', cache: 'no-store' });
      return response.status;
    });
    expect(afterRevoke).toBe(401);
    await displayContext.close();
  });

  test('login, POS workspace, and mobile POS have no serious or critical Axe violations', async ({ page }) => {
    await page.goto('/login');
    expect(await seriousAxeViolations(page), 'serious/critical Axe violations on login').toEqual([]);

    await login(page, ownerUsername, ownerPassword);
    await page.goto('/pos');
    // /pos is an immersive workspace and intentionally does not render the
    // application Header. Wait for a semantic landmark owned by the POS page
    // itself so Axe scans the actual ready workspace state.
    await expect(page.getByRole('heading', { name: 'Open a Session' })).toBeVisible();
    expect(await seriousAxeViolations(page), 'serious/critical Axe violations on desktop POS').toEqual([]);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload();
    await expect(page.getByRole('heading', { name: 'Open a Session' })).toBeVisible();
    expect(await seriousAxeViolations(page), 'serious/critical Axe violations on mobile POS').toEqual([]);
  });
});
