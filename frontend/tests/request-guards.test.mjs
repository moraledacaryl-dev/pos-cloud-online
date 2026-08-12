import assert from 'node:assert/strict';
import test from 'node:test';

import { createInFlightMutationRegistry, mutationRequestKey } from '../lib/requestGuards.mjs';

test('mutationRequestKey ignores read-only requests', () => {
  assert.equal(mutationRequestKey('/orders'), null);
  assert.equal(mutationRequestKey('/orders', { method: 'HEAD' }), null);
});

test('mutationRequestKey differentiates method, path, and payload', () => {
  const first = mutationRequestKey('/orders/7/pay', { method: 'POST', body: '{"amount":100}' });
  const same = mutationRequestKey('/orders/7/pay', { method: 'post', body: '{"amount":100}' });
  const different = mutationRequestKey('/orders/7/pay', { method: 'POST', body: '{"amount":200}' });
  assert.equal(first, same);
  assert.notEqual(first, different);
});

test('registry coalesces only the exact in-flight mutation', async () => {
  const registry = createInFlightMutationRegistry();
  const key = 'POST:/orders/7/pay:{"amount":100}';
  let resolve;
  const pending = new Promise((done) => { resolve = done; });

  registry.set(key, pending);
  assert.equal(registry.get(key), pending);
  assert.equal(registry.size(), 1);

  resolve({ ok: true });
  await pending;
  registry.clear(key, pending);
  assert.equal(registry.get(key), null);
  assert.equal(registry.size(), 0);
});

test('registry does not clear a newer request with an older promise', () => {
  const registry = createInFlightMutationRegistry();
  const key = 'POST:/orders';
  const first = Promise.resolve('first');
  const second = Promise.resolve('second');
  registry.set(key, first);
  registry.set(key, second);
  registry.clear(key, first);
  assert.equal(registry.get(key), second);
});
