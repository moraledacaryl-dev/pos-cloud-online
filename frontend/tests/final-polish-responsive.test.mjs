import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const layoutFile = new URL('../app/layout.js', import.meta.url);
const polishFile = new URL('../app/final-polish.css', import.meta.url);

test('final visual polish is loaded after the established theme layers', async () => {
  const layout = await readFile(layoutFile, 'utf8');
  const themeIndex = layout.indexOf("import './hidden-oasis-theme.css';");
  const polishIndex = layout.indexOf("import './final-polish.css';");

  assert.ok(themeIndex >= 0, 'Hidden Oasis theme import must remain present.');
  assert.ok(polishIndex > themeIndex, 'Final polish must load last so its bounded density overrides are deterministic.');
});

test('mobile operational surfaces keep compact first-viewport density', async () => {
  const css = await readFile(polishFile, 'utf8');

  assert.match(css, /@media \(max-width: 760px\)/);
  assert.match(css, /\.metric-rail\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(css, /\.pos-compact-topbar\s*\{[\s\S]*?display:\s*flex;[\s\S]*?flex-wrap:\s*wrap;/);
  assert.match(css, /\.kds-controls\s*\{[\s\S]*?flex-direction:\s*row;[\s\S]*?padding:\s*8px 10px;/);
  assert.match(css, /\.kds-segmented \.toggle-btn,[\s\S]*?min-height:\s*34px;/);
});

test('desktop polish does not target the full-screen POS workspace', async () => {
  const css = await readFile(polishFile, 'utf8');

  assert.match(css, /\.main:not\(:has\(\.pos-page-root\)\)/);
  assert.doesNotMatch(css, /@media \(min-width: 1001px\)[\s\S]*?\.pos-page-root\s+\.section\s*\{[\s\S]*?padding:/);
});
