import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const usersFile = new URL('../app/users/page.js', import.meta.url);
const visualAuditFile = new URL('../e2e/visual-audit.spec.mjs', import.meta.url);

test('users page switches from the wide table to complete mobile cards', async () => {
  const source = await readFile(usersFile, 'utf8');
  assert.match(source, /className="table users-table"/);
  assert.match(source, /className="users-card-list"/);
  assert.match(source, /<dt>Staff Identity<\/dt>/);
  assert.match(source, /<dt>Primary Role<\/dt>/);
  assert.match(source, /<dt>Assigned Roles<\/dt>/);
  assert.match(source, /@media \(max-width: 760px\)[\s\S]*?\.users-table \{ display: none; \}[\s\S]*?\.users-card-list \{ display: grid;/);
});

test('full-page visual audit expands and restores the application content scroller', async () => {
  const source = await readFile(visualAuditFile, 'utf8');
  assert.match(source, /async function expandInternalAppScroller/);
  assert.match(source, /main\.scrollHeight <= main\.clientHeight \+ 1/);
  assert.match(source, /main\.style\.overflow = 'visible'/);
  assert.match(source, /async function restoreInternalAppScroller/);
  assert.match(source, /internal_scroll_expanded: expandedInternalScroller/);
  assert.match(source, /expanded full-page capture should exceed viewport/);
});
