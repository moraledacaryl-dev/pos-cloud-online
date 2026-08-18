import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const appShell = readFileSync(new URL('../components/AppShell.js', import.meta.url), 'utf8');
const header = readFileSync(new URL('../components/Header.js', import.meta.url), 'utf8');
const sidebar = readFileSync(new URL('../components/Sidebar.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../app/mobile-accessibility.css', import.meta.url), 'utf8');
const layout = readFileSync(new URL('../app/layout.js', import.meta.url), 'utf8');

test('mobile navigation is a real controlled off-canvas drawer', () => {
  assert.match(header, /aria-expanded=\{menuOpen\}/);
  assert.match(header, /aria-controls="primary-navigation"/);
  assert.match(sidebar, /id="primary-navigation"/);
  assert.match(sidebar, /aria-label="Primary navigation"/);
  assert.match(css, /transform:\s*translateX\(-105%\)/);
  assert.match(css, /\.sidebar\.mobile-open[\s\S]*translateX\(0\)/);
  assert.match(css, /\.drawer-scrim\.open/);
});

test('drawer manages focus, escape, body scroll, inert background, and route close', () => {
  assert.match(appShell, /event\.key === 'Escape'/);
  assert.match(appShell, /event\.key !== 'Tab'/);
  assert.match(appShell, /document\.body\.style\.overflow = 'hidden'/);
  assert.match(appShell, /setAttribute\('inert', ''\)/);
  assert.match(appShell, /removeAttribute\('inert'\)/);
  assert.match(appShell, /openerRef\.current\?\.focus\(\)/);
  assert.match(appShell, /setDrawerOpen\(false\);\s*\n\s*}, \[pathname\]\)/);
  assert.match(sidebar, /onClick=\{onNavigate\}/);
});

test('mobile and tablet breakpoints cover target widths and touch controls', () => {
  assert.match(css, /@media \(max-width: 1000px\)/);
  assert.match(css, /@media \(max-width: 820px\)/);
  assert.match(css, /@media \(max-width: 768px\)/);
  assert.match(css, /@media \(max-width: 390px\)/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /min-height:\s*48px/);
  assert.match(css, /\.modal-card[\s\S]*max-height:\s*min\(88vh, 88dvh\)/);
  assert.match(css, /\.cashier-pos-shell[\s\S]*grid-template-columns:\s*1fr/);
});

test('responsive overrides are loaded after global styles', () => {
  const globalsIndex = layout.indexOf("import './globals.css'");
  const mobileIndex = layout.indexOf("import './mobile-accessibility.css'");
  assert.ok(globalsIndex >= 0);
  assert.ok(mobileIndex > globalsIndex);
});

test('navigation exposes current page and drawer close controls', () => {
  assert.match(sidebar, /aria-current=\{active \? 'page' : undefined\}/);
  assert.match(sidebar, /aria-label="Close navigation menu"/);
});
