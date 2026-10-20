import { randomUUID } from 'node:crypto';
import { writeFileSync } from 'node:fs';

import { expect, test } from '@playwright/test';

const OWNER = process.env.E2E_OWNER_USERNAME || 'ci-owner';
const PASSWORD = process.env.E2E_OWNER_PASSWORD || 'CiOwnerPassword-2026!';
const SKU = 'E2E-FINANCE-100';

async function login(page) {
  await page.goto('/login');
  await page.getByLabel('Username').fill(OWNER);
  await page.getByLabel('Password').fill(PASSWORD);
  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login'),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ]);
}

async function api(page, method, path, body) {
  return page.evaluate(async ({ method, path, body }) => {
    const csrfCookie = document.cookie.split(';')
      .map((token) => token.trim())
      .find((token) => token.startsWith('pos_csrf='));
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (csrfCookie && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      headers['X-CSRF-Token'] = decodeURIComponent(csrfCookie.slice('pos_csrf='.length));
    }
    const res = await fetch('/api' + path, {
      method, credentials: 'same-origin', cache: 'no-store', headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await res.json(); } catch {}
    if (res.status !== 200) {
      throw new Error(method + ' ' + path + ' failed: ' + res.status + ' ' + JSON.stringify(data));
    }
    return data;
  }, { method, path, body });
}

async function seedPaidVisualOrder(page, registerCode) {
  const [registers, items] = await Promise.all([
    api(page, 'GET', '/registers'),
    api(page, 'GET', '/catalog/items'),
  ]);
  const register = registers.find((item) => item.code === registerCode);
  const catalog = items.find((item) => item.sku_code === SKU);
  expect(register).toBeTruthy();
  expect(catalog).toBeTruthy();
  const date = new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const session = await api(page, 'POST', '/register-sessions/open', {
    register_id: register.id, business_date: date,
    shift_name: 'CI Visual Audit', opening_float: '200.00',
  });
  const guest = 'Visual Review ' + randomUUID().slice(0, 8);
  const order = await api(page, 'POST', '/orders', {
    register_session_id: session.id,
    order_type: 'dine_in',
    guest_name: guest,
    table_label: 'VISUAL-1',
    lines: [{ catalog_item_id: catalog.id, quantity: 2, unit_price: '100.00' }],
  });
  const paid = await api(page, 'POST', '/orders/' + order.id + '/pay', {
    payments: [{ tender_type: 'cash', amount_applied: 200, amount_received: 200 }],
  });
  expect(paid.status).toBe('paid');
  return { session, guest, order };
}

async function expandScroller(page) {
  return page.evaluate(() => {
    const shell = document.querySelector('.app-shell:not(.standalone-shell):not(.terminal-shell)');
    const mainShell = shell?.querySelector('.main-shell');
    const main = shell?.querySelector('.main');
    if (!shell || !mainShell || !main || main.scrollHeight <= main.clientHeight + 1) return false;
    for (const node of [shell, mainShell, main]) {
      node.dataset.pass9Style = node.getAttribute('style') ?? '__none__';
    }
    shell.style.height = 'auto';
    shell.style.minHeight = '100vh';
    shell.style.overflow = 'visible';
    mainShell.style.height = 'auto';
    mainShell.style.minHeight = '0';
    mainShell.style.overflow = 'visible';
    main.style.height = 'auto';
    main.style.maxHeight = 'none';
    main.style.overflow = 'visible';
    return true;
  });
}

async function restoreScroller(page) {
  await page.evaluate(() => {
    document.querySelectorAll('[data-pass9-style]').forEach((node) => {
      const previous = node.dataset.pass9Style;
      if (previous === '__none__') node.removeAttribute('style');
      else node.setAttribute('style', previous || '');
      delete node.dataset.pass9Style;
    });
  });
}

async function record(page, testInfo, captures, label) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(175);
  const diagnostics = await page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const modal = document.querySelector('[role="dialog"][aria-modal="true"]');
    const rect = modal?.getBoundingClientRect();
    const html = document.documentElement;
    return {
      route: location.pathname,
      viewportWidth,
      viewportHeight,
      documentWidth: html.scrollWidth,
      horizontalOverflow: Math.max(0, html.scrollWidth - viewportWidth),
      dialog: rect ? {
        left: Math.round(rect.left),
        right: Math.round(rect.right),
        top: Math.round(rect.top),
        bottom: Math.round(rect.bottom),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      } : null,
      overflowingPanels: [...document.querySelectorAll('.section,.modal-card,.card-grid,.form-grid,.toolbar,.pos-terminal-top')]
        .filter((node) => {
          const styles = getComputedStyle(node);
          if (styles.display === 'none' || styles.visibility === 'hidden') return false;
          const bounds = node.getBoundingClientRect();
          return bounds.width > 10 && (bounds.right > viewportWidth + 4 || bounds.left < -4) &&
            bounds.bottom > 0 && bounds.top < viewportHeight;
        })
        .slice(0, 12).map((node) => ({
          className: String(node.className || '').slice(0, 90),
          width: Math.round(node.getBoundingClientRect().width),
          right: Math.round(node.getBoundingClientRect().right),
        })),
    };
  });
  const viewportFile = testInfo.outputPath(label + '--viewport.png');
  await page.screenshot({ path: viewportFile, animations: 'disabled' });

  let expanded = false;
  try {
    expanded = await expandScroller(page);
    await page.screenshot({
      path: testInfo.outputPath(label + '--full.png'),
      animations: 'disabled',
      fullPage: true,
    });
  } finally {
    if (expanded) await restoreScroller(page);
  }
  captures.push({ label, ...diagnostics, expandedInternalScroller: expanded });
}

for (const scenario of [
  { label: 'desktop', width: 1440, height: 900, registerCode: 'E2E-VISUAL-D' },
  { label: 'mobile', width: 390, height: 844, registerCode: 'E2E-VISUAL-M' },
]) {
  test('Pass 9 screenshot and form alignment audit: ' + scenario.label, async ({ page }, testInfo) => {
    // Expanded full-page screenshots of five operational routes and dialogs.
    test.setTimeout(180_000);
    test.skip(process.env.E2E_FINANCIAL_FIXTURES !== '1', 'Requires isolated visual CI fixtures.');
    await page.setViewportSize({ width: scenario.width, height: scenario.height });
    await login(page);
    const captures = [];
    const prefix = 'pass9-' + scenario.label + '-';
    const { session, guest } = await seedPaidVisualOrder(page, scenario.registerCode);

    for (const [route, title] of [
      ['/orders', 'Orders'],
      ['/cash-movements', 'Cash Movements'],
      ['/sessions', 'Register Sessions'],
      ['/registers', 'Registers'],
      ['/pos', 'Point of Sale'],
    ]) {
      await page.goto(route);
      if (route === '/pos') await expect(page.getByRole('heading', { name: title, exact: true })).toBeAttached();
      else await expect(page.getByRole('heading', { name: title, exact: true })).toBeVisible();
      await record(page, testInfo, captures, prefix + route.slice(1) + '-overview');

      if (route === '/orders') {
        // Verify that an actual paid record is visible and its action panel fits.
        await page.getByRole('row').filter({ hasText: guest }).first().click();
        await expect(page.getByRole('button', { name: 'Process Refund' })).toBeVisible();
        await record(page, testInfo, captures, prefix + 'orders-paid-details');
        await page.getByRole('button', { name: 'Process Refund' }).click();
        await expect(page.getByRole('dialog', { name: 'Order action dialog' })).toBeVisible();
        await record(page, testInfo, captures, prefix + 'orders-refund-dialog');
        await page.getByRole('button', { name: 'Cancel' }).last().click();
      }

      if (route === '/cash-movements') {
        await page.locator('details.admin-create-disclosure summary').click();
        await expect(page.getByRole('button', { name: /paid out/i }).first()).toBeVisible();
        await page.getByRole('button', { name: /paid out/i }).first().click();
        await expect(page.getByText(/Estimated drawer balance:/)).toBeVisible();
        await record(page, testInfo, captures, prefix + 'cash-paid-out-form');
      }

      if (route === '/sessions') {
        const sessionRow = page.getByRole('row').filter({ hasText: session.session_code });
        await expect(sessionRow).toBeVisible();
        await sessionRow.getByRole('button', { name: 'Count & close' }).click();
        await expect(page.getByRole('dialog', { name: 'Close register session' })).toBeVisible();
        await record(page, testInfo, captures, prefix + 'session-close-dialog');
        await page.getByRole('button', { name: 'Close session dialog' }).click();
      }

      if (route === '/pos') {
        await page.locator('.pos-tools-menu summary').click();
        await page.getByRole('button', { name: 'Menu Availability' }).click();
        await expect(page.getByRole('dialog', { name: 'Menu availability' })).toBeVisible();
        await record(page, testInfo, captures, prefix + 'pos-availability-dialog');
        await page.getByRole('dialog', { name: 'Menu availability' }).getByRole('button', { name: 'Close' }).click();
      }
    }

    if (scenario.label === 'mobile') {
      await page.setViewportSize({ width: 320, height: 700 });
      await page.goto('/cash-movements');
      await expect(page.getByRole('heading', { name: 'Cash Movements', exact: true })).toBeVisible();
      await page.locator('details.admin-create-disclosure summary').click();
      await record(page, testInfo, captures, 'pass9-compact-cash-form');
      await page.goto('/orders');
      await page.getByRole('row').filter({ hasText: guest }).first().click();
      await record(page, testInfo, captures, 'pass9-compact-orders-paid-details');
    }

    const jsonPath = testInfo.outputPath(prefix + 'diagnostics.json');
    writeFileSync(jsonPath, JSON.stringify({
      viewport: scenario,
      businessRecords: { sessionCode: session.session_code, guest },
      screenshots: captures,
    }, null, 2));
    // Keep UI findings in evidence instead of blindly changing CSS before
    // inspecting full-page screenshots, especially scrollable tables.
    expect(captures.length).toBeGreaterThanOrEqual(9);
  });
}
