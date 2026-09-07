import test from 'node:test';
import assert from 'node:assert/strict';

import { buildReceiptHtml, buildRefundReceiptHtml } from '../lib/receipt.js';

const order = {
  order_no: 'POS-20260907-0001',
  subtotal_amount: 100,
  discount_amount: 0,
  tax_amount: 12,
  service_charge_amount: 0,
  total_amount: 112,
  lines: [{ item_name_snapshot: 'Meal', quantity: 1, line_total: 100 }],
};

test('unregistered receipt output cannot be mistaken for an official tax invoice', () => {
  const html = buildReceiptHtml({ ...order, receipt_profile: { registration_status: 'unregistered' } });
  assert.match(html, /PROVISIONAL SALES RECORD/);
  assert.match(html, /NOT AN OFFICIAL SALES INVOICE/);
  assert.doesNotMatch(html, /<div class="document-label">SALES INVOICE<\/div>/);
});

test('registered sales invoice prints tax and machine registration details', () => {
  const receipt_profile = {
    registration_status: 'registered',
    tax_registration_type: 'vat',
    registered_name: 'Hidden Oasis Resort',
    business_address: 'Bulacan',
    tin: '123-456-789-000',
    branch_code: '00000',
    machine_identification_number: 'MIN-001',
    serial_number: 'SN-001',
    permit_to_use_number: 'PTU-001',
  };
  const html = buildReceiptHtml({ ...order, receipt_profile });
  assert.match(html, /SALES INVOICE/);
  assert.match(html, /VATable Sales/);
  assert.match(html, /VAT Amount/);
  assert.match(html, /MIN: MIN-001/);
  assert.match(html, /PTU: PTU-001/);

  const refundHtml = buildRefundReceiptHtml({ refund_no: 'RF-1', refunded_amount: 112, receipt_profile });
  assert.match(refundHtml, /REFUND ACKNOWLEDGMENT/);
  assert.match(refundHtml, /Original invoice/);
});
