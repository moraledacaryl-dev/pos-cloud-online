import { test, expect } from '@playwright/test';

function extractScriptNonce(csp) {
  const match = /script-src[^;]*'nonce-([^']+)'/.exec(csp || '');
  return match?.[1] || '';
}

test('nonce CSP removes unsafe-inline scripts without breaking hydration', async ({ page }) => {
  const consoleFailures = [];
  page.on('console', (message) => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (/content security policy|refused to execute|refused to load|hydration/i.test(text)) {
      consoleFailures.push(text);
    }
  });

  const first = await page.goto('/login');
  expect(first?.status()).toBe(200);

  const firstCsp = first?.headers()['content-security-policy'] || '';
  expect(firstCsp).toContain("script-src 'self' 'nonce-");
  expect(firstCsp).toContain("'strict-dynamic'");
  expect(firstCsp).toContain("script-src-attr 'none'");
  expect(firstCsp).not.toMatch(/script-src[^;]*'unsafe-inline'/);
  expect(firstCsp).not.toMatch(/script-src[^;]*'unsafe-eval'/);

  const firstNonce = extractScriptNonce(firstCsp);
  expect(firstNonce.length).toBeGreaterThan(10);

  await expect(page.getByLabel('Username')).toBeVisible();
  await expect(page.getByLabel('Password')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeEnabled();

  const executableScripts = await page.locator('script').evaluateAll((nodes) =>
    nodes
      .filter((node) => {
        const type = (node.getAttribute('type') || '').toLowerCase();
        return type === '' || type === 'text/javascript' || type === 'module';
      })
      .map((node) => ({ src: node.getAttribute('src') || '', nonce: node.nonce || node.getAttribute('nonce') || '' }))
  );

  expect(executableScripts.length).toBeGreaterThan(0);
  for (const script of executableScripts) {
    expect(script.nonce, `missing CSP nonce on script ${script.src || '<inline>'}`).toBe(firstNonce);
  }

  const second = await page.reload();
  expect(second?.status()).toBe(200);
  const secondCsp = second?.headers()['content-security-policy'] || '';
  const secondNonce = extractScriptNonce(secondCsp);
  expect(secondNonce.length).toBeGreaterThan(10);
  expect(secondNonce).not.toBe(firstNonce);

  await expect(page.getByLabel('Username')).toBeVisible();
  expect(consoleFailures).toEqual([]);
});
