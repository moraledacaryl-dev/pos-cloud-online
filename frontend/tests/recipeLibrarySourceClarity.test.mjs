import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const page = readFileSync(new URL('../app/recipes/page.js', import.meta.url), 'utf8');
const recipeService = readFileSync(new URL('../../backend/app/services/recipe_service.py', import.meta.url), 'utf8');

test('recipe library explains eligible linked catalog dishes without misidentifying the menu owner', () => {
  assert.match(page, /Inventory & Procurement owns the master selling catalog/);
  assert.match(page, /linked upstream dish ID/);
  assert.match(page, /Other active POS menu items may still appear in Catalog/);
  assert.match(page, /linked dishes/);
  assert.doesNotMatch(page, /Accounting remains the menu master|Accounting Dishes|imports dishes from Accounting/);
});

test('linked-dish empty-state copy matches the backend eligibility filter', () => {
  assert.match(recipeService, /CatalogItem\.external_menu_item_id\.isnot\(None\)/);
  assert.match(page, /PDF upload becomes available when an eligible dish exists/);
});
