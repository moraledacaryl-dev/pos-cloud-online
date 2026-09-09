import { defineConfig, devices } from '@playwright/test';

const visualAuditEnabled = process.env.VISUAL_AUDIT_RUN === '1';

export default defineConfig({
  testDir: './e2e',
  testIgnore: visualAuditEnabled ? [] : ['**/visual-audit.spec.mjs'],
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 1,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:8080',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
