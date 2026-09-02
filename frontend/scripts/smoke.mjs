import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';

const host = '127.0.0.1';
const port = Number(process.env.POS_SMOKE_PORT || 3199);
const base = `http://${host}:${port}`;
const child = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '-H', host, '-p', String(port)], {
  cwd: new URL('..', import.meta.url),
  env: { ...process.env, NODE_ENV: 'production', NEXT_PUBLIC_API_BASE: '/api' },
  stdio: ['ignore', 'pipe', 'pipe'],
});

let output = '';
child.stdout.on('data', (chunk) => { output += chunk; });
child.stderr.on('data', (chunk) => { output += chunk; });

async function waitForServer() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`${base}/login`, { redirect: 'manual' });
      if (response.ok) return;
    } catch {}
    if (child.exitCode != null) throw new Error(`Next server exited early (${child.exitCode}).\n${output}`);
    await delay(250);
  }
  throw new Error(`Timed out waiting for ${base}.\n${output}`);
}

async function assertPage(path, expectedText) {
  const response = await fetch(`${base}${path}`, { redirect: 'manual' });
  if (response.status !== 200) throw new Error(`${path} returned HTTP ${response.status}`);
  const body = await response.text();
  if (!body.includes(expectedText)) throw new Error(`${path} did not contain ${expectedText}`);
  return { response, body };
}

try {
  await waitForServer();
  const login = await assertPage('/login', 'POS');
  await assertPage('/dashboard', 'Checking Access');
  const protectedRoutes = [
    '/', '/pos', '/kitchen', '/kitchen-board', '/bar', '/expo', '/orders',
    '/registers', '/sessions', '/cash-movements', '/room-charges', '/catalog',
    '/recipes', '/sync', '/settings', '/users', '/audit',
  ];
  for (const path of protectedRoutes) {
    const response = await fetch(`${base}${path}`, { redirect: 'manual' });
    if (response.status !== 200) throw new Error(`${path} returned HTTP ${response.status}`);
  }
  const customerDisplay = await fetch(`${base}/customer-display`, { redirect: 'manual' });
  if (customerDisplay.status !== 200) throw new Error(`/customer-display returned HTTP ${customerDisplay.status}`);
  const missing = await fetch(`${base}/does-not-exist`, { redirect: 'manual' });
  if (missing.status !== 404) throw new Error(`/does-not-exist returned HTTP ${missing.status} instead of 404`);
  const csp = login.response.headers.get('content-security-policy') || '';
  if (!csp.includes("default-src 'self'") || !csp.includes("media-src 'self'")) throw new Error('CSP is missing required default/media policy');
  if (!csp.includes("style-src 'self' 'unsafe-inline'")) throw new Error('CSP would block React style attributes');
  const scriptPolicy = csp.split(';').find((part) => part.trim().startsWith('script-src')) || '';
  if (scriptPolicy.includes("'unsafe-inline'")) throw new Error('CSP must not allow inline scripts');
  const scriptPath = login.body.match(/src="([^"]*_next\/static\/[^"]+\.js)"/)?.[1];
  if (!scriptPath) throw new Error('Login page did not reference a built JavaScript asset');
  const asset = await fetch(`${base}${scriptPath}`);
  if (!asset.ok) throw new Error(`Built asset returned HTTP ${asset.status}`);
  const api = await fetch(`${base}/api/auth/me`, { redirect: 'manual' });
  // A standalone Next server has no reverse proxy and returns 404; the deployed
  // nginx path returns an authentication or upstream-availability response.
  if (![401, 404, 502, 503].includes(api.status)) throw new Error(`Unauthenticated API path returned unexpected HTTP ${api.status}`);
  console.log(JSON.stringify({ ok: true, base, routeCount: protectedRoutes.length + 3, checks: ['all-routes', 'login', 'protected-shell', 'customer-display', 'not-found', 'csp', 'static-asset', 'api-path'] }));
} finally {
  child.kill('SIGTERM');
  await Promise.race([new Promise((resolve) => child.once('exit', resolve)), delay(3000)]);
  if (child.exitCode == null) child.kill('SIGKILL');
}
