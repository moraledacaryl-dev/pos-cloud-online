import fs from 'node:fs';
import path from 'node:path';

const root = new URL('..', import.meta.url).pathname;
const failures = [];

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.name === 'node_modules' || entry.name === '.next') return [];
    const absolute = path.join(dir, entry.name);
    return entry.isDirectory() ? files(absolute) : [absolute];
  });
}

const sourceRoots = ['app', 'components', 'lib'].map((name) => path.join(root, name));
for (const file of sourceRoots.flatMap(files).filter((name) => /\.(js|mjs)$/.test(name))) {
  const source = fs.readFileSync(file, 'utf8');
  if (/<[A-Za-z][^>]*role="dialog"(?![^>]*(aria-label|aria-labelledby))/.test(source)) failures.push(`${file}: dialog has no accessible name`);
  if (/<th>\s*<\/th>/.test(source)) failures.push(`${file}: empty table header`);
  if (/new Error\(data\?\.detail\s*\|\|/.test(source)) failures.push(`${file}: structured API error is not normalized`);
  if (/AccessibilityRuntime/.test(source)) failures.push(`${file}: removed runtime accessibility repair was reintroduced`);
}

if (failures.length) {
  console.error(failures.join('\n'));
  process.exit(1);
}
console.log('Source audit passed.');
