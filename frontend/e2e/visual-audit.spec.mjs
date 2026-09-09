import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const OUTPUT_ROOT = path.resolve(process.cwd(), process.env.VISUAL_AUDIT_OUTPUT || 'visual-audit');
const MODE = (process.env.VISUAL_AUDIT_MODE || 'full').toLowerCase();
const CAPTURE_FULL_PAGE = process.env.VISUAL_AUDIT_FULL_PAGE !== 'false';

const ROUTES = [
  '/dashboard',
  '/pos',
  '/kitchen',
  '/kitchen-board',
  '/bar',
  '/expo',
  '/orders',
  '/registers',
  '/sessions',
  '/cash-movements',
  '/room-charges',
  '/catalog',
  '/recipes',
  '/sync',
  '/settings',
  '/users',
  '/audit',
];

const VIEWPORTS = {
  desktop: { width: 1440, height: 1000 },
  tablet: { width: 1024, height: 768 },
  mobile: { width: 390, height: 844 },
};

const ROLE_CASES = [
  {
    role: 'owner',
    username: process.env.E2E_OWNER_USERNAME || 'ci-owner',
    password: process.env.E2E_OWNER_PASSWORD || 'CiOwnerPassword-2026!',
    allowed: new Set(ROUTES),
  },
  {
    role: 'manager',
    username: process.env.E2E_MANAGER_USERNAME || 'ci-manager',
    password: process.env.E2E_MANAGER_PASSWORD || 'CiManagerPassword-2026!',
    allowed: new Set(ROUTES.filter((route) => route !== '/users')),
  },
  {
    role: 'cashier',
    username: process.env.E2E_CASHIER_USERNAME || 'ci-cashier',
    password: process.env.E2E_CASHIER_PASSWORD || 'CiCashierPassword-2026!',
    allowed: new Set([
      '/dashboard', '/pos', '/orders', '/registers', '/sessions', '/cash-movements',
      '/room-charges', '/catalog', '/recipes',
    ]),
  },
  {
    role: 'kitchen',
    username: process.env.E2E_KITCHEN_USERNAME || 'ci-kitchen',
    password: process.env.E2E_KITCHEN_PASSWORD || 'CiKitchenPassword-2026!',
    allowed: new Set([
      '/dashboard', '/kitchen', '/kitchen-board', '/bar', '/expo', '/catalog', '/recipes',
    ]),
  },
];

const manifest = {
  generated_at: new Date().toISOString(),
  mode: MODE,
  base_url: process.env.E2E_BASE_URL || 'http://127.0.0.1:8080',
  full_page_enabled: CAPTURE_FULL_PAGE,
  routes: ROUTES,
  viewports: VIEWPORTS,
  roles: ROLE_CASES.map(({ role, allowed }) => ({ role, allowed: [...allowed] })),
  captures: [],
};

function safePart(value) {
  return String(value || 'none')
    .replace(/^\/+/, '')
    .replace(/[^a-zA-Z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'root';
}

function selectedViewports() {
  if (MODE === 'smoke') return [['desktop', VIEWPORTS.desktop], ['mobile', VIEWPORTS.mobile]];
  const requested = String(process.env.VISUAL_AUDIT_VIEWPORTS || '').trim();
  if (!requested) return Object.entries(VIEWPORTS);
  return requested.split(',').map((name) => name.trim()).filter(Boolean).map((name) => {
    if (!VIEWPORTS[name]) throw new Error(`Unknown VISUAL_AUDIT_VIEWPORTS entry: ${name}`);
    return [name, VIEWPORTS[name]];
  });
}

function selectedRoles() {
  if (MODE === 'smoke') return ROLE_CASES.filter(({ role }) => ['owner', 'cashier'].includes(role));
  const requested = String(process.env.VISUAL_AUDIT_ROLES || '').trim();
  if (!requested) return ROLE_CASES;
  const wanted = new Set(requested.split(',').map((name) => name.trim()).filter(Boolean));
  return ROLE_CASES.filter(({ role }) => wanted.has(role));
}

function writeManifest() {
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'manifest.json'), JSON.stringify(manifest, null, 2));
}

async function settle(page) {
  await page.waitForLoadState('domcontentloaded');
  await page.waitForTimeout(350);
}

async function capture(page, { role = 'public', viewport, route, state = 'default', note = '' }) {
  const routePart = safePart(route);
  const dir = path.join(OUTPUT_ROOT, safePart(role), safePart(viewport), routePart);
  fs.mkdirSync(dir, { recursive: true });

  const baseName = safePart(state);
  const viewportFile = path.join(dir, `${baseName}--viewport.png`);
  await page.screenshot({ path: viewportFile, fullPage: false, animations: 'disabled' });
  manifest.captures.push({
    role,
    viewport,
    route,
    state,
    kind: 'viewport',
    file: path.relative(OUTPUT_ROOT, viewportFile),
    url: page.url(),
    note,
  });

  if (CAPTURE_FULL_PAGE) {
    const fullFile = path.join(dir, `${baseName}--full.png`);
    await page.screenshot({ path: fullFile, fullPage: true, animations: 'disabled' });
    manifest.captures.push({
      role,
      viewport,
      route,
      state,
      kind: 'full',
      file: path.relative(OUTPUT_ROOT, fullFile),
      url: page.url(),
      note,
    });
  }
  writeManifest();
}

async function login(page, username, password) {
  await page.goto('/login');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await Promise.all([
    page.waitForURL((url) => url.pathname !== '/login'),
    page.getByRole('button', { name: 'Sign in' }).click(),
  ]);
  await settle(page);
}

async function logoutIfPresent(page) {
  const logout = page.getByRole('button', { name: 'Logout' });
  if (await logout.count()) {
    await logout.first().click().catch(() => {});
    await page.waitForURL((url) => url.pathname === '/login').catch(() => {});
  }
}

function shouldCaptureRoute(roleCase, route) {
  if (MODE !== 'smoke') return true;
  const smoke = new Set(['/dashboard', '/pos', '/orders', '/users', '/kitchen']);
  return smoke.has(route) && (roleCase.allowed.has(route) || route === '/users' || route === '/kitchen');
}

async function captureRouteMatrix(page, roleCase, viewportName) {
  for (const route of ROUTES) {
    if (!shouldCaptureRoute(roleCase, route)) continue;
    const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
    await settle(page);
    const denied = page.locator('[data-route-status="403"]');
    if (roleCase.allowed.has(route)) {
      await expect(denied, `${roleCase.role} should be allowed on ${route}`).toHaveCount(0);
      await capture(page, {
        role: roleCase.role,
        viewport: viewportName,
        route,
        state: 'allowed-default',
        note: `HTTP ${response?.status() || 'client-navigation'}; allowed route`,
      });
    } else {
      await expect(denied, `${roleCase.role} should be denied on ${route}`).toBeVisible();
      await capture(page, {
        role: roleCase.role,
        viewport: viewportName,
        route,
        state: 'permission-denied-403',
        note: 'Known route intentionally denied by role matrix',
      });
    }
  }
}

async function captureMobileDrawer(page, roleCase, viewportName) {
  if (viewportName !== 'mobile') return;
  await page.goto('/dashboard');
  await settle(page);
  const opener = page.locator('button.mobile-menu-button');
  if (!await opener.count()) return;
  await opener.click();
  await expect(opener).toHaveAttribute('aria-expanded', 'true');
  await capture(page, {
    role: roleCase.role,
    viewport: viewportName,
    route: '/dashboard',
    state: 'mobile-navigation-open',
  });
  await page.keyboard.press('Escape');
}

async function captureUnknownRoute(page, roleCase, viewportName) {
  const route = '/visual-audit-route-that-does-not-exist';
  const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
  await settle(page);
  await expect(page.getByRole('heading', { name: /Page Not Found/i })).toBeVisible();
  await capture(page, {
    role: roleCase.role,
    viewport: viewportName,
    route,
    state: 'not-found-404',
    note: `HTTP ${response?.status() || 404}`,
  });
}

async function captureOwnerSpecialStates(page, viewportName) {
  if (viewportName === 'desktop') {
    await page.goto('/pos');
    await settle(page);
    await capture(page, { role: 'owner', viewport: viewportName, route: '/pos', state: 'pos-initial-workspace' });

    await page.context().setOffline(true);
    await page.evaluate(() => window.dispatchEvent(new Event('offline')));
    await page.waitForTimeout(250);
    await capture(page, { role: 'owner', viewport: viewportName, route: '/pos', state: 'browser-offline' });
    await page.context().setOffline(false);
    await page.evaluate(() => window.dispatchEvent(new Event('online')));

    await page.goto('/customer-display?setup=1&channel=visual-audit', { waitUntil: 'domcontentloaded' });
    await settle(page);
    await capture(page, {
      role: 'owner',
      viewport: viewportName,
      route: '/customer-display?setup=1&channel=visual-audit',
      state: 'display-management',
    });

    for (const route of ['/dashboard', '/pos', '/orders', '/sync']) {
      await page.unroute('**/api/**').catch(() => {});
      await page.route('**/api/**', async (routeHandler) => {
        const pathname = new URL(routeHandler.request().url()).pathname;
        if (pathname.startsWith('/api/auth/')) return routeHandler.continue();
        return routeHandler.abort('failed');
      });
      await page.goto(route, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(700);
      await capture(page, {
        role: 'owner',
        viewport: viewportName,
        route,
        state: 'dependency-network-failure',
        note: 'Non-auth API requests intentionally aborted by Playwright',
      });
    }
    await page.unroute('**/api/**').catch(() => {});
  }
}

test.describe.serial('comprehensive POS visual audit', () => {
  test.beforeAll(() => {
    fs.rmSync(OUTPUT_ROOT, { recursive: true, force: true });
    writeManifest();
  });

  test.afterAll(() => writeManifest());

  for (const [viewportName, viewport] of selectedViewports()) {
    test(`public states - ${viewportName}`, async ({ page }) => {
      await page.setViewportSize(viewport);

      await page.goto('/login');
      await settle(page);
      await capture(page, { role: 'public', viewport: viewportName, route: '/login', state: 'empty-login' });

      await page.getByLabel('Username').fill('visual-audit-invalid');
      await page.getByLabel('Password').fill('VisualAuditInvalidPassword-2026!');
      await page.getByRole('button', { name: 'Sign in' }).click();
      await page.waitForTimeout(500);
      await capture(page, { role: 'public', viewport: viewportName, route: '/login', state: 'invalid-login' });

      await page.goto('/customer-display?channel=visual-audit', { waitUntil: 'domcontentloaded' });
      await settle(page);
      await capture(page, {
        role: 'public',
        viewport: viewportName,
        route: '/customer-display?channel=visual-audit',
        state: 'unpaired-customer-display',
      });

      await page.goto('/orders', { waitUntil: 'domcontentloaded' });
      await settle(page);
      await capture(page, {
        role: 'public',
        viewport: viewportName,
        route: '/orders',
        state: 'unauthenticated-protected-route',
        note: 'Protected route without session; expected login/auth-required surface',
      });
    });

    for (const roleCase of selectedRoles()) {
      test(`${roleCase.role} visual route matrix - ${viewportName}`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await login(page, roleCase.username, roleCase.password);
        await captureRouteMatrix(page, roleCase, viewportName);
        await captureMobileDrawer(page, roleCase, viewportName);
        await captureUnknownRoute(page, roleCase, viewportName);
        if (roleCase.role === 'owner') await captureOwnerSpecialStates(page, viewportName);
        await logoutIfPresent(page);
      });
    }
  }
});
