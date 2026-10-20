import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const ordersPage = new URL('../app/orders/page.js', import.meta.url);
const styles = new URL('../app/globals.css', import.meta.url);

test('orders KPI cards show wide financial totals and compact status counts on mobile', async () => {
  const [source, css] = await Promise.all([
    readFile(ordersPage, 'utf8'),
    readFile(styles, 'utf8'),
  ]);
  assert.match(source, /className="metric-rail orders-review-metrics"/);
  assert.match(
    css,
    /\.orders-review-metrics\s*\{[^}]*grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\)/,
    'Four mobile tracks allow two wide financial totals above four status counts.',
  );
  assert.match(
    css,
    /\.orders-review-metrics \.metric-card:nth-child\(-n \+ 2\)\s*\{[^}]*grid-column:\s*span 2/,
    'The monetary KPIs must be two tracks wide to avoid clipping peso amounts.',
  );
});
