import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, unlinkSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { expectedCaptures, verifyManifest } from '../scripts/verify-visual-audit-manifest.mjs';

const PNG = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), Buffer.alloc(120, 9)]);
const SHA = 'a'.repeat(40);

function fixture(mode, fullPage) {
  const root = mkdtempSync(path.join(os.tmpdir(), 'pos-visual-evidence-'));
  const captures = expectedCaptures(mode, fullPage).map((item, index) => {
    const file = `shot-${index}.png`;
    writeFileSync(path.join(root, file), PNG);
    return { ...item, file };
  });
  return {
    root,
    manifest: {
      mode, source_sha: SHA, full_page_enabled: fullPage,
      base_url: 'http://127.0.0.1:8080', captures,
    },
  };
}

test('full screenshot matrix requires 478 separate PNG files', () => {
  const { root, manifest } = fixture('full', true);
  try {
    assert.equal(manifest.captures.length, 478);
    assert.deepEqual(verifyManifest(manifest, root, SHA), {
      mode: 'full', screenshots: 478, captureStates: 239, sha: SHA,
    });
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('smoke screenshot matrix requires 45 separate viewport PNGs', () => {
  const { root, manifest } = fixture('smoke', false);
  try {
    assert.equal(manifest.captures.length, 45);
    assert.equal(verifyManifest(manifest, root, SHA).captureStates, 45);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('incomplete, duplicate or missing PNG fails closed', () => {
  const { root, manifest } = fixture('smoke', false);
  try {
    const missing = { ...manifest, captures: manifest.captures.slice(1) };
    assert.throws(() => verifyManifest(missing, root, SHA), /incomplete/);
    const duplicated = { ...manifest, captures: [...manifest.captures] };
    duplicated.captures[0] = duplicated.captures[1];
    assert.throws(() => verifyManifest(duplicated, root, SHA), /duplicate/);
    unlinkSync(path.join(root, manifest.captures[0].file));
    assert.throws(() => verifyManifest(manifest, root, SHA));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test('wrong source SHA, unsafe target and artifact path are rejected', () => {
  const { root, manifest } = fixture('smoke', false);
  try {
    assert.throws(() => verifyManifest(manifest, root, 'b'.repeat(40)), /SHA/);
    assert.throws(() => verifyManifest({ ...manifest, base_url: 'https://pos.hiddenoasis.app' }, root, SHA), /loopback/);
    const corrupt = { ...manifest, captures: [...manifest.captures] };
    corrupt.captures[0] = { ...corrupt.captures[0], file: '../../secrets.png' };
    assert.throws(() => verifyManifest(corrupt, root, SHA), /escaped artifact/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
