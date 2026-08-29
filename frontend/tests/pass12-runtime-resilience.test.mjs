import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

function read(path) {
  return fs.readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');
}

test('Pass 12 app shell reserves an explicit sync-banner row', () => {
  const css = read('app/pass12-runtime.css');
  assert.match(css, /grid-template-rows:\s*auto auto minmax\(0, 1fr\)/);
});

test('Pass 12 KDS alerts are same-origin, gesture enabled, and promise-safe', () => {
  const kitchen = read('app/kitchen/page.js');
  const config = read('next.config.js');
  assert.match(kitchen, /src="\/sounds\/kds-alert\.wav"/);
  assert.match(kitchen, /Enable sound/);
  assert.match(kitchen, /await audioRef\.current\.play\(\)/);
  assert.doesNotMatch(kitchen, /data:audio\/wav/);
  assert.match(config, /media-src 'self'/);
});

test('Pass 12 customer display query state is hydrated after mount', () => {
  const display = read('app/customer-display/page.js');
  assert.match(display, /const \[channel, setChannel\] = useState\('main'\)/);
  assert.match(display, /useEffect\(\(\) => \{\s*const params = new URLSearchParams\(window\.location\.search\)/s);
  assert.doesNotMatch(display, /useMemo\(\(\) => typeof window/);
});

test('Pass 12 restricted terminal routes provide workspace and logout recovery', () => {
  const guard = read('components/RouteGuard.js');
  assert.match(guard, /Open my workspace/);
  assert.match(guard, /Sign out/);
  assert.match(guard, /logoutSession/);
});

test('Pass 12 degraded integration states stay visible instead of becoming empty data', () => {
  const registers = read('app/registers/page.js');
  const banner = read('components/SyncHealthBanner.js');
  assert.match(registers, /Accounting unavailable/);
  assert.doesNotMatch(registers, /fetchAccountingAccounts\(\)\.catch\(\(\) => \[\]\)/);
  assert.match(banner, /Local selling is available/);
  assert.match(banner, /aria-live="polite"/);
});
