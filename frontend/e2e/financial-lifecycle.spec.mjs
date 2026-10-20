import { randomUUID } from 'node:crypto';

import { expect, test } from '@playwright/test';

const ownerUsername = process.env.E2E_OWNER_USERNAME || 'ci-owner';
const ownerPassword = process.env.E2E_OWNER_PASSWORD || 'CiOwnerPassword-2026!';
const REGISTER_CODE = 'E2E-FINANCE';
const SKU = 'E2E-FINANCE-100';

async function login(page) {
  await page.goto('/login');
  await page.getByLabel('Username').fill(ownerUsername);
  await page.getByLabel('Password').fill(ownerPassword);
  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login'),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ]);
}

async function api(page, method, path, body) {
  return page.evaluate(async ({ method, path, body }) => {
    const csrfCookie = document.cookie.split(';')
      .map((item) => item.trim())
      .find((item) => item.startsWith('pos_csrf='));
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (csrfCookie && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      headers['X-CSRF-Token'] = decodeURIComponent(csrfCookie.slice('pos_csrf='.length));
    }
    const response = await fetch(`/api${path}`, {
      method, credentials: 'same-origin', cache: 'no-store', headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    let data = null;
    try { data = await response.json(); } catch {}
    return { status: response.status, data };
  }, { method, path, body });
}

function succeeded(response, label) {
  expect(response.status, `${label}: ${JSON.stringify(response.data)}`).toBe(200);
  return response.data;
}

test('authenticated POS sale, stale-cart block, cash replay, outbox and shift close stay consistent', async ({ page }, testInfo) => {
  // These fixtures exist only inside the isolated PostgreSQL pos_browser
  // database provisioned by production-equivalent CI.
  test.skip(process.env.E2E_FINANCIAL_FIXTURES !== '1', 'Requires isolated CI financial fixtures.');
  await login(page);

  const registers = succeeded(await api(page, 'GET', '/registers'), 'list registers');
  const register = registers.find((row) => row.code === REGISTER_CODE);
  expect(register, 'mapped CI register must be provisioned').toBeTruthy();
  expect(register.accounting_financial_account_id).toBe(1);

  const catalog = succeeded(await api(page, 'GET', '/catalog/items'), 'list catalog');
  const item = catalog.find((row) => row.sku_code === SKU);
  expect(item, 'mapped CI catalog item must be provisioned').toBeTruthy();
  expect(Number(item.price)).toBe(100);

  const businessDate = new Date(Date.now() + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const session = succeeded(await api(page, 'POST', '/register-sessions/open', {
    register_id: register.id, business_date: businessDate,
    shift_name: 'CI Financial E2E', opening_float: '100.00',
  }), 'open session');
  expect(session.status).toBe('open');

  // A stale cashier cart must not be allowed to submit a sold-out item.
  succeeded(await api(page, 'PUT', `/catalog/items/${item.id}`, { is_available: false }), 'sell out');
  const before = succeeded(await api(page, 'GET', `/orders?session_id=${session.id}`), 'orders before');
  const stale = await api(page, 'POST', '/orders', {
    register_session_id: session.id,
    lines: [{ catalog_item_id: item.id, quantity: 1, unit_price: 100 }],
  });
  expect(stale.status).toBe(400);
  expect(JSON.stringify(stale.data)).toMatch(/sold out/i);
  expect(succeeded(await api(page, 'GET', `/orders?session_id=${session.id}`), 'orders after rejected cart')).toHaveLength(before.length);
  succeeded(await api(page, 'PUT', `/catalog/items/${item.id}`, { is_available: true }), 'restore availability');

  const guest = `CI Financial ${randomUUID().slice(0, 8)}`;
  const order = succeeded(await api(page, 'POST', '/orders', {
    register_session_id: session.id, order_type: 'dine_in',
    guest_name: guest, table_label: 'CI-TABLE-8',
    lines: [{ catalog_item_id: item.id, quantity: 2, unit_price: 100, discount_amount: 0 }],
  }), 'create order');
  expect(order.status).toBe('draft');
  expect(Number(order.total_amount)).toBe(200);
  expect(order.lines).toHaveLength(1);

  const reference = `CI-GC-${randomUUID()}`;
  const tender = {
    payments: [
      { tender_type: 'cash', amount_applied: 125, amount_received: 125 },
      {
        tender_type: 'gcash', amount_applied: 75, amount_received: 75,
        reference_no: reference, accounting_financial_account_id: 2,
      },
    ],
  };
  const paid = succeeded(await api(page, 'POST', `/orders/${order.id}/pay`, tender), 'pay order');
  expect(paid.status).toBe('paid');
  expect(Number(paid.paid_amount)).toBe(200);
  expect(Number(paid.balance_due)).toBe(0);
  expect(paid.payment_breakdown).toHaveLength(2);

  const replayPay = await api(page, 'POST', `/orders/${order.id}/pay`, tender);
  expect(replayPay.status).toBe(400);
  expect(JSON.stringify(replayPay.data)).toMatch(/cannot be paid|paid/i);

  // Network retry of the SAME request must not create a second drawer entry.
  const requestId = randomUUID();
  const cashPayload = {
    register_session_id: session.id, direction: 'in', movement_type: 'paid_in',
    amount: 25, category: 'CI Change Fund', note: 'CI test cash in',
    reference_no: `E2E-${requestId}`, client_request_id: requestId,
  };
  const firstCash = succeeded(await api(page, 'POST', '/cash-movements', cashPayload), 'cash entry');
  const retriedCash = succeeded(await api(page, 'POST', '/cash-movements', cashPayload), 'cash retry');
  expect(retriedCash.id).toBe(firstCash.id);

  const changedReplay = await api(page, 'POST', '/cash-movements', { ...cashPayload, amount: 50 });
  expect(changedReplay.status).toBe(400);
  expect(JSON.stringify(changedReplay.data)).toMatch(/already used/i);

  const movements = succeeded(await api(page, 'GET', `/cash-movements?session_id=${session.id}`), 'drawer movements');
  expect(movements.filter((row) => row.movement_type === 'cash_sale' && Number(row.amount) === 125)).toHaveLength(1);
  expect(movements.filter((row) => row.client_request_id === requestId || row.id === firstCash.id)).toHaveLength(1);

  const liveSession = succeeded(await api(page, 'GET', `/register-sessions/${session.id}`), 'session detail');
  expect(Number(liveSession.closing_expected_cash)).toBe(250);
  const outbox = succeeded(await api(page, 'GET', '/sync/outbox?limit=500'), 'sync outbox');
  const forOrder = outbox.filter((row) => Number(row.aggregate_id) === order.id);
  expect(forOrder.filter((row) => row.event_type === 'order.finalized')).toHaveLength(1);
  expect(forOrder.filter((row) => row.event_type === 'inventory.sale_completed')).toHaveLength(1);
  expect(outbox.filter((row) => row.event_type === 'payment.collected' && JSON.stringify(row.payload_json).includes(reference))).toHaveLength(1);

  const closed = succeeded(await api(page, 'POST', `/register-sessions/${session.id}/close`, {
    closing_actual_cash: 250,
    close_mode: 'verified', blind_close: false,
    sign_off_name: 'CI Financial E2E',
    sign_off_role: 'Test Owner',
  }), 'close session');
  expect(closed.status).toBe('closed');
  expect(Number(closed.variance_amount)).toBe(0);
  expect(succeeded(await api(page, 'GET', `/register-sessions/${session.id}`), 'closed session').status).toBe('closed');

  // Replaying a successfully recorded cash movement is safe after close.
  const afterClose = succeeded(await api(page, 'POST', '/cash-movements', cashPayload), 'closed-session retry');
  expect(afterClose.id).toBe(firstCash.id);
  const newAfterClose = await api(page, 'POST', '/cash-movements', {
    ...cashPayload, client_request_id: randomUUID(), reference_no: `CI-AFTER-${randomUUID()}`,
  });
  expect(newAfterClose.status).toBe(400);
  expect(JSON.stringify(newAfterClose.data)).toMatch(/open register session|open register|open/i);

  const closedOutbox = succeeded(await api(page, 'GET', '/sync/outbox?limit=500'), 'closed outbox');
  expect(closedOutbox.filter((row) => row.event_type === 'session.closed' && Number(row.aggregate_id) === session.id)).toHaveLength(1);

  // Keep a browser screenshot in CI artifacts as proof that the paid order is
  // actually visible from the application, not only through its REST API.
  await page.goto('/orders');
  await expect(page.getByRole('heading', { name: 'Orders', exact: true })).toBeVisible();
  await expect(page.getByText(guest).first()).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath('pass8-paid-order-browser-evidence.png'),
    fullPage: true,
  });
});
