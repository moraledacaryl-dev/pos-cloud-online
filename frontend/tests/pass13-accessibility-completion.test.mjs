import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
}

test('Pass 13 central runtime repairs repeated Axe primitives', () => {
  const runtime = read('components/AccessibilityRuntime.js');
  assert.match(runtime, /aria-labelledby/);
  assert.match(runtime, /aria-label', 'Actions'/);
  assert.match(runtime, /Availability filter/);
  assert.match(runtime, /Close mode/);
  assert.match(runtime, /Point of Sale/);
  assert.match(runtime, /main\.order-items-panel/);
  assert.match(runtime, /setAttribute\('role', 'region'\)/);
  assert.match(runtime, /Scrollable data table/);
  assert.match(runtime, /scrollLeft !== 0/);
});

test('Pass 13 sync banner is inside a named landmark', () => {
  const banner = read('components/SyncHealthBanner.js');
  assert.match(banner, /<aside className=/);
  assert.match(banner, /aria-label="POS sync status"/);
});

test('Pass 13 contrast and responsive overflow styles are active after prior pass styles', () => {
  const layout = read('app/layout.js');
  const css = read('app/pass13-accessibility.css');
  assert.match(layout, /pass12-runtime\.css';\s*import '\.\/pass13-accessibility\.css'/s);
  assert.match(layout, /<AccessibilityRuntime \/>/);
  assert.match(css, /\.nav-group-label/);
  assert.match(css, /#626861/);
  assert.match(css, /\.list-row-button\.active \.muted/);
  assert.match(css, /#d7ddd8/);
  assert.match(css, /\.table\[tabindex="0"\]/);
});
