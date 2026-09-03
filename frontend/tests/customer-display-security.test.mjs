import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const page = fs.readFileSync(new URL('../app/customer-display/page.js', import.meta.url), 'utf8');
const api = fs.readFileSync(new URL('../lib/api.js', import.meta.url), 'utf8');

test('customer display no longer falls back to localStorage order data', () => {
  assert.equal(page.includes('pos_customer_display'), false);
  assert.equal(page.includes('readDisplaySnapshot'), false);
});

test('customer display uses paired server credential flow', () => {
  assert.match(page, /customer-display\/activate/);
  assert.match(page, /customer-display\/pairing-code/);
  assert.match(api, /credentials: 'same-origin'/);
});

test('customer display uses shared Philippine peso formatter', () => {
  assert.match(page, /Intl\.NumberFormat\('en-PH'/);
  assert.match(page, /currency: 'PHP'/);
});

test('customer display UI does not render guest name or internal local ids', () => {
  assert.equal(page.includes('guest_name'), false);
  assert.equal(page.includes('local_id'), false);
});

test('customer display pairing explains the optional two-screen workflow', () => {
  assert.match(page, /This is the optional guest-facing screen—not the cashier terminal/);
  assert.match(page, /One-time pairing code/);
  assert.match(page, /Open manager setup/);
  assert.match(page, /Not using a customer display\? Return to POS/);
  assert.match(page, /customer-display-pair-form/);
});

test('manager setup lists and revokes paired displays', () => {
  assert.match(page, /customer-display\/devices/);
  assert.match(page, /Paired displays/);
  assert.match(page, /Last seen/);
  assert.match(page, /revokeDisplay/);
});
