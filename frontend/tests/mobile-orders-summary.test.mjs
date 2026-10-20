import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const ordersPage = new URL('../app/orders/page.js', import.meta.url);
const styles = new URL('../app/globals.css', import.meta.url);

test('orders KPI cards use the scoped compact 3-column layout on mobile', async () => {
  const [source, css] = await Promise.all([
    readFile(ordersPage, 'utf8'),
    readFile(styles, 'utf8'),
  ]);
  assert.match(
    source,
    /className="metric-rail orders-review-metrics"/,
    'Orders KPI rail must retain the dedicated responsive class.',
  );
  assert.match(
    css,
    /\.orders-review-metrics\s*\{[^}]*grid-template-columns:\s*repeat\(3, minmax\(0, 1fr\)\)/,
    'The mobile KPI rail must fit three concise metrics per row.',
  );
});
