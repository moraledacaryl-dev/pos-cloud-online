import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.resolve(here, '..');

function source(relativePath) {
  return fs.readFileSync(path.join(frontendRoot, relativePath), 'utf8');
}

test('POS does not persist the server-backed customer display snapshot in localStorage', () => {
  const pos = source('app/pos/page.js');
  assert.equal(pos.includes("localStorage.setItem('pos_customer_display'"), false);
  assert.equal(pos.includes('localStorage.setItem("pos_customer_display"'), false);
  assert.equal(pos.includes('pos_customer_display'), false);
  assert.match(pos, /localStorage\.removeItem\(\['pos', 'customer', 'display'\]\.join\('_'\)\)/);
  assert.match(pos, /updateCustomerDisplaySnapshot\(snapshot\)/);
});

test('CI proxy propagates downstream abort and close to upstream streams', () => {
  const proxy = source('e2e/ci-proxy.mjs');
  assert.match(proxy, /req\.once\('aborted', destroyUpstream\)/);
  assert.match(proxy, /res\.once\('close', destroyUpstream\)/);
  assert.match(proxy, /upstream\.destroy\(\)/);
  assert.match(proxy, /upstreamRes\.destroy\(\)/);
});

test('production certification no longer depends on public detailed health', () => {
  const script = fs.readFileSync(path.resolve(frontendRoot, '..', 'scripts', 'production-certify.sh'), 'utf8');
  assert.match(script, /BACKEND_BASE.*internal\/healthz\/details/);
  assert.match(script, /PUBLIC_DETAILS_CODE/);
});

test('strict production CSP is request-scoped and contains no unsafe-inline allowances', () => {
  const proxy = source('proxy.js');
  const nextConfig = source('next.config.js');

  assert.match(proxy, /crypto\.randomUUID\(\)/);
  assert.match(proxy, /requestHeaders\.set\('x-nonce', nonce\)/);
  assert.match(proxy, /requestHeaders\.set\('Content-Security-Policy', csp\)/);
  assert.match(proxy, /response\.headers\.set\('Content-Security-Policy', csp\)/);
  assert.match(proxy, /script-src 'self' 'nonce-\$\{nonce\}' 'strict-dynamic'/);
  assert.match(proxy, /style-src 'self'.*nonce-\$\{nonce\}/);
  assert.equal(proxy.includes("script-src 'self' 'unsafe-inline'"), false);
  assert.equal(nextConfig.includes("'unsafe-inline'"), false);
  assert.equal(nextConfig.includes('Content-Security-Policy'), false);
});

test('root layout forces dynamic rendering so Next can apply per-request CSP nonces', () => {
  const layout = source('app/layout.js');
  assert.match(layout, /import \{ connection \} from 'next\/server'/);
  assert.match(layout, /export default async function RootLayout/);
  assert.match(layout, /await connection\(\)/);
});
