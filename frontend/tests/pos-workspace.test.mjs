import assert from 'node:assert/strict';
import test from 'node:test';

import {
  calculateCartTotals,
  emptyPayment,
  groupPriceLabel,
  parseTableValue,
  serviceLabel,
  tableKey,
} from '../lib/posWorkspace.mjs';

test('POS workspace helpers preserve cashier-facing labels and table identity', () => {
  assert.equal(serviceLabel('folio_pending'), 'Billing');
  assert.equal(serviceLabel('preparing'), 'Waiting');
  assert.equal(tableKey('Garden', 'G1'), 'Garden::G1');
  assert.deepEqual(parseTableValue('Above Kitchen::AK2'), { area: 'Above Kitchen', code: 'AK2' });
});

test('new payments default to cash without leaking a stale room-charge identity', () => {
  const payment = emptyPayment('425.50', 12);
  assert.equal(payment.tender_type, 'cash');
  assert.equal(payment.amount_applied, '425.50');
  assert.equal(payment.accounting_financial_account_id, '12');
  assert.equal(payment.room_charge_booking_snapshot_id, '');
});

test('product groups show a range only when variants differ', () => {
  assert.equal(groupPriceLabel({ items: [{ price: 100 }, { price: 100 }] }), '₱100.00');
  assert.equal(groupPriceLabel({ items: [{ price: 100 }, { price: 150 }] }), '₱100.00-₱150.00');
});

test('cart totals match backend tax and service-charge calculation', () => {
  assert.deepEqual(calculateCartTotals([{
    price: 130,
    quantity: 1,
    discount_amount: 0,
    tax_rate: 0.12,
    service_charge_rate: 0.05,
  }]), { subtotal: 130, discount: 0, tax: 15.6, serviceCharge: 6.5, total: 152.1 });
});
