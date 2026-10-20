import assert from 'node:assert/strict';
import test from 'node:test';

import { listOfflineDrafts, saveOfflineDraft } from '../lib/offlineDrafts.js';
import { clearLastReceipt, loadLastReceipt, saveLastReceipt } from '../lib/receipt.js';

function stubStorage(initial = {}, { blockWrites = false } = {}) {
  const values = new Map(Object.entries(initial));
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => {
      if (blockWrites) throw new Error('SecurityError: storage write blocked');
      values.set(key, String(value));
    },
    removeItem: (key) => {
      if (blockWrites) throw new Error('SecurityError: storage removal blocked');
      values.delete(key);
    },
  };
}

function withBrowser(t, storage) {
  const original = globalThis.window;
  globalThis.window = { localStorage: storage };
  t.after(() => {
    if (original === undefined) delete globalThis.window;
    else globalThis.window = original;
  });
}

test('invalid legacy JSON cannot hide valid recovery drafts', (t) => {
  const now = new Date().toISOString();
  const valid = {
    id: 'offline-valid', saved_at: now,
    expires_at: new Date(Date.now() + 60_000).toISOString(),
    cart: [{ name: 'Coffee', quantity: 2 }],
  };
  const storage = stubStorage({
    pos_offline_order_drafts_v2: JSON.stringify([valid]),
    pos_offline_order_drafts_v1: '{invalid json',
  });
  withBrowser(t, storage);
  assert.deepEqual(listOfflineDrafts().map(row => row.id), ['offline-valid']);
  assert.equal(storage.getItem('pos_offline_order_drafts_v1'), null);
  assert.deepEqual(JSON.parse(storage.getItem('pos_offline_order_drafts_v2')).map(row => row.id), ['offline-valid']);
});

test('legacy drafts with saved_at receive 24h expiry; bad or missing timestamps cannot survive forever', (t) => {
  const fresh = new Date(Date.now() - 10 * 60_000).toISOString();
  const stale = new Date(Date.now() - 48 * 60 * 60_000).toISOString();
  const storage = stubStorage({
    pos_offline_order_drafts_v1: JSON.stringify([
      { id: 'recent', saved_at: fresh, expires_at: 'malformed-date' },
      { id: 'expired', saved_at: stale },
      { id: 'unknown-age', cart: [{ name: 'Sensitive' }] },
      null,
      'invalid',
    ]),
  });
  withBrowser(t, storage);
  const rows = listOfflineDrafts();
  assert.deepEqual(rows.map(row => row.id), ['recent']);
  const expiry = Date.parse(rows[0].expires_at);
  assert.ok(expiry > Date.now());
  assert.ok(expiry <= Date.now() + 24 * 60 * 60_000);
});

test('expired current drafts are purged even if saved earlier', (t) => {
  const storage = stubStorage({
    pos_offline_order_drafts_v2: JSON.stringify([
      { id: 'expired', saved_at: new Date().toISOString(), expires_at: new Date(Date.now() - 1_000).toISOString() },
      { id: 'ready', saved_at: new Date().toISOString(), expires_at: new Date(Date.now() + 60_000).toISOString() },
    ]),
  });
  withBrowser(t, storage);
  assert.deepEqual(listOfflineDrafts().map(row => row.id), ['ready']);
  assert.deepEqual(JSON.parse(storage.getItem('pos_offline_order_drafts_v2')).map(row => row.id), ['ready']);
});

test('new offline draft is explicitly tagged local-only, short-lived and operator-scoped', (t) => {
  const storage = stubStorage();
  withBrowser(t, storage);
  const saved = saveOfflineDraft(
    { id: 'offline-draft-01', cart: [{ name: 'Cookie', quantity: 1 }] },
    { ownerId: 13, ownerLabel: 'Cashier', registerId: 2 },
  );
  assert.equal(saved.status, 'local_only');
  assert.equal(saved.owner_id, 13);
  assert.equal(saved.register_id, 2);
  assert.ok(Date.parse(saved.expires_at) - Date.now() <= 24 * 60 * 60_000);
});

test('last-receipt reprint requires matching operator and drawer including during login initialization', (t) => {
  const storage = stubStorage();
  withBrowser(t, storage);
  const original = { order_no: 'CI-100', guest_name: 'Private Guest' };
  assert.equal(saveLastReceipt(original, { ownerId: 11, registerId: 3 }), true);
  assert.deepEqual(loadLastReceipt({ ownerId: 11, registerId: 3 }), original);
  assert.equal(loadLastReceipt(), null);
  assert.equal(loadLastReceipt({ ownerId: 11 }), null);
  assert.equal(loadLastReceipt({ registerId: 3 }), null);
  assert.equal(loadLastReceipt({ ownerId: 12, registerId: 3 }), null);
  assert.equal(loadLastReceipt({ ownerId: 11, registerId: 4 }), null);
  // An unsuccessful scoped read must not destroy the valid owner's receipt.
  assert.deepEqual(loadLastReceipt({ ownerId: 11, registerId: 3 }), original);
});

test('unscoped legacy receipts are never reprinted under a valid user', (t) => {
  const storage = stubStorage({
    pos_last_receipt_v2: JSON.stringify({
      receipt: { order_no: 'CI-101', guest_name: 'Old Guest' },
      expires_at: new Date(Date.now() + 60_000).toISOString(),
      owner_id: null, register_id: null,
    }),
  });
  withBrowser(t, storage);
  assert.equal(loadLastReceipt({ ownerId: 11, registerId: 3 }), null);
  assert.equal(saveLastReceipt({ order_no: 'CI-102' }), false);
});

test('damaged expiry never makes last customer receipt permanent', (t) => {
  const storage = stubStorage({
    pos_last_receipt_v2: JSON.stringify({
      receipt: { order_no: 'CI-103', guest_name: 'Old Guest' },
      expires_at: 'not-a-date', owner_id: 11, register_id: 3,
    }),
  });
  withBrowser(t, storage);
  assert.equal(loadLastReceipt({ ownerId: 11, registerId: 3 }), null);
  assert.equal(storage.getItem('pos_last_receipt_v2'), null);
});

test('blocked localStorage cannot throw after a successful payment or on clear', (t) => {
  const storage = stubStorage({}, { blockWrites: true });
  withBrowser(t, storage);
  assert.equal(saveLastReceipt({ order_no: 'CI-104' }, { ownerId: 11, registerId: 3 }), false);
  assert.doesNotThrow(() => clearLastReceipt());
  assert.equal(loadLastReceipt({ ownerId: 11, registerId: 3 }), null);
});
