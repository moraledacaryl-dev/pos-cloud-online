import fs from 'fs';
const files = ['app/pos/page.js','app/kitchen/page.js','lib/api.js'];
for (const file of files) {
  if (!fs.existsSync(new URL(`../${file}`, import.meta.url))) {
    throw new Error(`Missing ${file}`);
  }
}
console.log('frontend smoke ok');
