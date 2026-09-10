import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const ordersPage = new URL('../app/orders/page.js', import.meta.url);

test('orders summary can form two compact columns on narrow mobile content widths', async () => {
  const source = await readFile(ordersPage, 'utf8');
  assert.match(
    source,
    /gridTemplateColumns:\s*['"]repeat\(auto-fit, minmax\(min\(140px, 100%\), 1fr\)\)['"]/,
    'Orders KPI rail should use a sub-180px minimum so a 390px mobile viewport can show two summary cards per row.',
  );
});
