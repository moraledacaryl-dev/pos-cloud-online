import { test, expect } from '@playwright/test';

const ownerUsername = process.env.E2E_OWNER_USERNAME || 'ci-owner';
const ownerPassword = process.env.E2E_OWNER_PASSWORD || 'CiOwnerPassword-2026!';

async function login(page) {
  await page.goto('/login');
  await page.getByLabel('Username').fill(ownerUsername);
  await page.getByLabel('Password').fill(ownerPassword);
  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login'),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ]);
}

async function streamMetrics(page) {
  return page.evaluate(async () => {
    const response = await fetch('/api/kitchen/stream-metrics', {
      credentials: 'same-origin',
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(`stream metrics returned ${response.status}`);
    return response.json();
  });
}

test('closing the KDS page tears down proxy upstream stream and listener state', async ({ page }) => {
  await login(page);
  await page.goto('/kitchen');
  await expect(page.getByText('connected', { exact: true })).toBeVisible({ timeout: 15_000 });

  await expect.poll(async () => {
    const metrics = await streamMetrics(page);
    return Number(metrics.active_streams || 0);
  }, { timeout: 10_000 }).toBeGreaterThan(0);

  await page.goto('/dashboard');

  await expect.poll(async () => {
    const metrics = await streamMetrics(page);
    return {
      active_streams: Number(metrics.active_streams || 0),
      listeners: Number(metrics.listeners || 0),
    };
  }, { timeout: 15_000 }).toEqual({ active_streams: 0, listeners: 0 });
});
