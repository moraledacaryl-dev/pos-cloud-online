import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const page = readFileSync(new URL('../app/kitchen/page.js', import.meta.url), 'utf8');
const streamClient = readFileSync(new URL('../lib/kdsStream.js', import.meta.url), 'utf8');

test('KDS EventSource no longer embeds access JWTs in the URL', () => {
  assert.doesNotMatch(page, /getToken/);
  assert.doesNotMatch(page, /searchParams\.set\(['"]token['"]/);
  assert.doesNotMatch(streamClient, /pos_token|pos_refresh_token|Authorization/);
  assert.match(streamClient, /stream-ticket/);
  assert.match(streamClient, /searchParams\.set\(['"]ticket['"]/);
});

test('KDS reconnect obtains a fresh one-time ticket', () => {
  assert.match(page, /createKitchenStreamTicket\(station\)/);
  assert.match(page, /stream_expiring/);
  assert.match(page, /new EventSource\(kitchenStreamUrl\(station, grant\.ticket\)\)/);
});
