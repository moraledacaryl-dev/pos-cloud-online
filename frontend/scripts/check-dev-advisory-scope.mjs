import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

// GHSA-vfj7-8cjw-p6xm has no patched braces release as of 2026-10-17.
// This is a scope guard, NOT a vulnerability waiver or substitute for npm audit.
// Keep the separate npm audit --omit=dev gate in CI.
const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
const chain = ['eslint-config-next', '@next/eslint-plugin-next', 'fast-glob', 'micromatch', 'braces'];
for (const name of chain) {
  const entry = lock.packages[`node_modules/${name}`];
  assert.ok(entry, `Expected tracked dev-only package ${name}; review security scope if dependency graph changed`);
  assert.equal(entry.dev, true, `${name} entered the production dependency closure; investigate immediately`);
}
assert.equal(lock.packages['node_modules/braces'].version, '3.0.3', 'braces version changed; reassess GHSA-vfj7-8cjw-p6xm and remove guard if fixed');
console.log('Tracked GHSA-vfj7-8cjw-p6xm remains confined to development dependencies. Advisory is NOT resolved.');
