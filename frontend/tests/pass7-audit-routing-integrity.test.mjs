import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const routes = fs.readFileSync(new URL('../lib/routes.js', import.meta.url), 'utf8');
const guard = fs.readFileSync(new URL('../components/RouteGuard.js', import.meta.url), 'utf8');
const auditPage = fs.readFileSync(new URL('../app/audit/page.js', import.meta.url), 'utf8');

test('unknown routes are not treated as authorization failures', () => {
  assert.match(routes, /if \(!route\) return true/);
  assert.match(guard, /if \(!route && !isPublic\) return children/);
  assert.doesNotMatch(guard, /if \(!route[^\n]*window\.location\.replace/);
});

test('authenticated login redirects to the user workspace', () => {
  assert.match(guard, /if \(!isLogin \|\| !loaded \|\| !user\) return/);
  assert.match(guard, /defaultRouteForUser\(user\)/);
  assert.match(guard, /window\.location\.replace\(target\)/);
});

test('known unauthorized route renders an explicit restricted state', () => {
  assert.match(guard, /data-route-status="403"/);
  assert.match(guard, /This page exists, but your account does not have permission/);
});

test('route normalization strips collection trailing slashes', () => {
  assert.match(routes, /replace\(\/\\\/\+\$\/, ''\)/);
});

test('audit UI uses bounded cursor pagination', () => {
  assert.match(auditPage, /limit: 50/);
  assert.match(auditPage, /before_id: beforeId/);
  assert.match(auditPage, /next_cursor/);
  assert.match(auditPage, />Previous</);
  assert.match(auditPage, />Next</);
  assert.doesNotMatch(auditPage, /limit: 200/);
});
