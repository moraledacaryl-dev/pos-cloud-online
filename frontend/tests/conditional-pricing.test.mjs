import assert from 'node:assert/strict';
import test from 'node:test';
import { resolveConditionalBasePrice } from '../lib/conditionalPricing.mjs';

const rule = { id: 'combo', qualifier_tag: 'qualifier', target_tag: 'target', priority: 10 };
const target = { price: 100, pricing_tags: ['target'], conditional_prices: [{ rule_id: 'combo', price: '80' }] };
const qualifier = { price: 50, pricing_tags: ['qualifier'], is_active: true, is_available: true };

test('generic conditional price activates and reverts when qualifier is removed', () => {
  assert.equal(resolveConditionalBasePrice(target, [target], [rule]), 100);
  assert.equal(resolveConditionalBasePrice(target, [target, qualifier], [rule]), 80);
  assert.equal(resolveConditionalBasePrice(target, [target], [rule]), 100);
});

test('inactive and unavailable qualifiers never activate pricing', () => {
  assert.equal(resolveConditionalBasePrice(target, [target, { ...qualifier, is_available: false }], [rule]), 100);
  assert.equal(resolveConditionalBasePrice(target, [target, { ...qualifier, is_active: false }], [rule]), 100);
  assert.equal(resolveConditionalBasePrice(target, [target, qualifier], [{ ...rule, is_active: false }]), 100);
});

test('lowest eligible price wins and malformed prices are rejected', () => {
  const other = { id: 'other', qualifier_tag: 'qualifier', target_tag: 'target', priority: 1 };
  const product = { ...target, conditional_prices: [{ rule_id: 'combo', price: '85' }, { rule_id: 'other', price: '75' }, { rule_id: 'other', price: '-1' }] };
  assert.equal(resolveConditionalBasePrice(product, [qualifier], [rule, other]), 75);
});

test('legacy pastry and drink discount remains available with empty generic metadata', () => {
  const pastry = { price: 100, with_drink_price: 90, pricing_role: 'pastry', pricing_tags: [], conditional_prices: [] };
  assert.equal(resolveConditionalBasePrice(pastry, [qualifier], []), 100);
  assert.equal(resolveConditionalBasePrice(pastry, [{ ...qualifier, pricing_role: 'drink' }], []), 90);
});
