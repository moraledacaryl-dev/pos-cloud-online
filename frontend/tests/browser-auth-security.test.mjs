import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const api = fs.readFileSync(new URL('../lib/api.js', import.meta.url), 'utf8');
const login = fs.readFileSync(new URL('../app/login/page.js', import.meta.url), 'utf8');
const header = fs.readFileSync(new URL('../components/Header.js', import.meta.url), 'utf8');

test('browser auth is not kept in local storage', () => {
  assert.equal(api.includes('pos_token'), false);
  assert.equal(api.includes('pos_refresh_token'), false);
  assert.equal(login.includes('setToken'), false);
  assert.equal(login.includes('setRefreshToken'), false);
  assert.equal(header.includes('getRefreshToken'), false);
});

test('browser requests use same-origin credentials and csrf header', () => {
  assert.equal(api.includes("credentials: 'same-origin'"), true);
  assert.equal(api.includes('X-CSRF-Token'), true);
  assert.equal(api.includes('headers.Authorization'), false);
});
