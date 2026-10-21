#!/usr/bin/env node
/* Fail closed when a screenshot artifact omits a role, route, state, or PNG. */
import { readFileSync, realpathSync, statSync } from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

export const ALL_ROUTES = [
  '/dashboard', '/pos', '/kitchen', '/kitchen-board', '/bar', '/expo', '/orders',
  '/registers', '/sessions', '/cash-movements', '/room-charges', '/catalog', '/recipes',
  '/sync', '/settings', '/users', '/audit',
];
export const ALLOWED = {
  owner: new Set(ALL_ROUTES),
  manager: new Set(ALL_ROUTES.filter((route) => route !== '/users')),
  cashier: new Set([
    '/dashboard', '/pos', '/orders', '/registers', '/sessions',
    '/cash-movements', '/room-charges', '/catalog', '/recipes',
  ]),
  kitchen: new Set(['/dashboard', '/kitchen', '/kitchen-board', '/bar', '/expo', '/catalog', '/recipes']),
};
const SMOKE_ROUTES = new Set(['/dashboard', '/pos', '/orders', '/catalog', '/users', '/kitchen']);
const SPECIAL_FAILURE_ROUTES = ['/dashboard', '/pos', '/orders', '/sync'];
const PNG_HEADER = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

export function captureKey({ role, viewport, route, state, kind }) {
  return JSON.stringify([role, viewport, route, state, kind]);
}

export function expectedCaptures(mode, fullPage) {
  if (!['smoke', 'full'].includes(mode)) throw new Error('Unknown visual audit mode');
  const viewports = mode === 'smoke' ? ['desktop', 'mobile'] : ['desktop', 'tablet', 'mobile'];
  const roles = mode === 'smoke' ? ['owner', 'cashier'] : Object.keys(ALLOWED);
  const kinds = fullPage ? ['viewport', 'full'] : ['viewport'];
  const rows = [];
  const add = (role, viewport, route, state) => {
    for (const kind of kinds) rows.push({ role, viewport, route, state, kind });
  };
  for (const viewport of viewports) {
    add('public', viewport, '/login', 'empty-login');
    add('public', viewport, '/login', 'invalid-login');
    add('public', viewport, '/customer-display?channel=visual-audit', 'unpaired-customer-display');
    add('public', viewport, '/orders', 'unauthenticated-protected-route');
    for (const role of roles) {
      const routes = mode === 'smoke' ? ALL_ROUTES.filter((route) => SMOKE_ROUTES.has(route)) : ALL_ROUTES;
      for (const route of routes) add(role, viewport, route, ALLOWED[role].has(route) ? 'allowed-default' : 'permission-denied-403');
      if (viewport === 'mobile') add(role, viewport, '/dashboard', 'mobile-navigation-open');
      add(role, viewport, '/visual-audit-route-that-does-not-exist', 'not-found-404');
      if (role === 'owner' && viewport === 'desktop') {
        add(role, viewport, '/pos', 'pos-initial-workspace');
        add(role, viewport, '/pos', 'browser-offline');
        add(role, viewport, '/customer-display?setup=1&channel=visual-audit', 'display-management');
        for (const route of SPECIAL_FAILURE_ROUTES) add(role, viewport, route, 'dependency-network-failure');
      }
    }
  }
  return rows;
}

export function verifyManifest(manifest, outputRoot, expectedSHA) {
  if (!manifest || typeof manifest !== 'object') throw new Error('Screenshot manifest missing');
  if (!['smoke', 'full'].includes(manifest.mode)) throw new Error('Invalid manifest mode');
  if (typeof manifest.full_page_enabled !== 'boolean') throw new Error('Invalid full-page mode');
  if (expectedSHA && manifest.source_sha !== expectedSHA) throw new Error('Visual audit source SHA mismatch');
  if (manifest.base_url !== 'http://127.0.0.1:8080') throw new Error('Visual audit must target isolated loopback POS');
  const expected = new Set(expectedCaptures(manifest.mode, manifest.full_page_enabled).map(captureKey));
  if (!Array.isArray(manifest.captures)) throw new Error('Screenshot manifest missing captures');
  if (manifest.captures.length !== expected.size) {
    throw new Error(`Visual coverage incomplete: ${manifest.captures.length} PNGs; expected ${expected.size}`);
  }
  const root = realpathSync(outputRoot);
  const seen = new Set(), files = new Set();
  for (const shot of manifest.captures) {
    const key = captureKey(shot);
    if (!expected.has(key) || seen.has(key)) throw new Error(`Unexpected/duplicate screenshot: ${key}`);
    seen.add(key);
    if (typeof shot.file !== 'string' || !shot.file.endsWith('.png')) throw new Error(`Missing PNG path: ${key}`);
    const resolved = path.resolve(root, shot.file);
    if (!resolved.startsWith(root + path.sep)) throw new Error(`PNG escaped artifact root: ${key}`);
    const canonical = realpathSync(resolved);
    if (!canonical.startsWith(root + path.sep)) throw new Error(`PNG symlink escaped artifact root: ${key}`);
    if (files.has(canonical)) throw new Error(`Duplicate PNG filename: ${shot.file}`);
    files.add(canonical);
    if (statSync(canonical).size < 100) throw new Error(`Empty/truncated PNG: ${shot.file}`);
    const png = readFileSync(canonical);
    if (!png.subarray(0, PNG_HEADER.length).equals(PNG_HEADER)) throw new Error(`Invalid PNG signature: ${shot.file}`);
  }
  const missing = [...expected].filter((key) => !seen.has(key));
  if (missing.length) throw new Error(`Missing capture: ${missing[0]}`);
  return {
    mode: manifest.mode, screenshots: manifest.captures.length,
    captureStates: manifest.captures.length / (manifest.full_page_enabled ? 2 : 1),
    sha: manifest.source_sha,
  };
}

function main() {
  const root = path.resolve(process.cwd(), process.env.VISUAL_AUDIT_OUTPUT || 'visual-audit');
  const manifest = JSON.parse(readFileSync(path.join(root, 'manifest.json'), 'utf8'));
  const result = verifyManifest(manifest, root, process.env.GITHUB_SHA || null);
  process.stdout.write(`VISUAL_AUDIT_EVIDENCE_PASS=${JSON.stringify(result)}\n`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
