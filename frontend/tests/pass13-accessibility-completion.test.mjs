import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
}

test('Pass 22 accessibility semantics are rendered by source components', () => {
  const layout = read('app/layout.js');
  const catalog = read('app/catalog/page.js');
  const sessions = read('app/sessions/page.js');
  const pos = read('app/pos/page.js');
  const dialogFocus = read('lib/useDialogFocus.js');
  assert.doesNotMatch(layout, /AccessibilityRuntime/);
  assert.match(catalog, /aria-label="Availability filter"/);
  assert.match(catalog, /<th>Actions<\/th>/);
  assert.match(sessions, /Close mode for/);
  assert.match(pos, /<h1 className="sr-only">Point of Sale<\/h1>/);
  assert.match(pos, /aria-label="Payment"/);
  assert.match(pos, /aria-label="Money drop"/);
  assert.match(pos, /useDialogFocus\(!!nativeDialogKey, closeNativeDialogs, nativeDialogKey\)/);
  assert.match(dialogFocus, /event\.key !== 'Tab'/);
  assert.match(dialogFocus, /previouslyFocused/);
});

test('Pass 13 sync banner is inside a named landmark', () => {
  const banner = read('components/SyncHealthBanner.js');
  assert.match(banner, /<aside className=/);
  assert.match(banner, /aria-label="POS sync status"/);
});

test('standalone pages do not create nested main landmarks', () => {
  const shell = read('components/AppShell.js');
  assert.match(shell, /const ContentElement = isStandalone \? 'div' : 'main'/);
  assert.match(shell, /<ContentElement className=/);
});

test('Pass 13 contrast and responsive overflow styles are active after prior pass styles', () => {
  const layout = read('app/layout.js');
  const css = read('app/pass13-accessibility.css');
  assert.match(layout, /pass12-runtime\.css';\s*import '\.\/pass13-accessibility\.css'/s);
  assert.doesNotMatch(layout, /AccessibilityRuntime/);
  assert.match(css, /\.nav-group-label/);
  assert.match(css, /#626861/);
  assert.match(css, /\.list-row-button\.active \.muted/);
  assert.match(css, /#d7ddd8/);
  assert.match(css, /\.table\[tabindex="0"\]/);
});
