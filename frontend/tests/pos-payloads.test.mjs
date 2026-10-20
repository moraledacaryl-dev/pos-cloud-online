import assert from 'node:assert/strict';
import test from 'node:test';

import { buildOrderWritePayload, buildPaymentWritePayload } from '../lib/posPayloads.mjs';

test('draft creation preserves quantities, modifiers, discounts, identity and notes', () => {
  const payload = buildOrderWritePayload({
    sessionId: '41', discountApprovalUserId: 7,
    orderType: 'dine_in', guestName: 'Customer A', activeArea: 'Terrace',
    tableLabel: 'TR2', seatCount: '4', note: 'No onions',
    cart: [{
      catalog_item_id: 19, quantity: 2, price: 165,
      discount_amount: 15.5,
      note: 'Make both iced',
      metadata: {
        groups: [{ id: 'add-ons', selections: [{ label: 'Sago' }, { label: 'Pearls' }] }],
        bundles: [{ id: 'drink', selections: [{ label: 'Tea' }] }],
      },
    }],
  });
  assert.deepEqual(payload, {
    register_session_id: 41,
    approved_by_user_id: 7,
    order_type: 'dine_in',
    source_channel: 'pos',
    guest_name: 'Customer A',
    service_area: 'Terrace',
    table_label: 'TR2',
    seat_count: 4,
    note: 'No onions',
    lines: [{
      catalog_item_id: 19,
      quantity: 2,
      unit_price: 165,
      discount_amount: 15.5,
      // Free-form bundle metadata is not a modifier group in the API.
      modifiers: [{ id: 'add-ons', labels: ['Sago', 'Pearls'] }],
      note: 'Make both iced',
    }],
  });
});

test('new unassigned draft does not leak old guest identity or legacy approval fields', () => {
  const payload = buildOrderWritePayload({
    sessionId: '12', discountApprovalUserId: undefined,
    orderType: 'takeout', guestName: '', activeArea: 'Lobby',
    tableLabel: '', seatCount: '', note: null,
    cart: [{ catalog_item_id: 8, quantity: 1, price: 25, metadata: {}, discount_amount: '' }],
  });
  assert.equal(payload.approved_by_user_id, null);
  assert.equal(payload.guest_name, null);
  assert.equal(payload.table_label, null);
  assert.equal(payload.seat_count, null);
  assert.equal(payload.lines[0].discount_amount, 0);
  assert.deepEqual(payload.lines[0].modifiers, []);
});

test('split cash and GCash tender have correct amounts, routing and no room-booking metadata', () => {
  const payload = buildPaymentWritePayload({
    orderType: 'dine_in', note: 'Paid in two tenders',
    currentSession: { business_date: '2026-10-21' },
    payments: [
      {
        tender_type: 'cash', amount_applied: '125', amount_received: '150',
        accounting_financial_account_id: '3', reference_no: '',
        room_charge_guest_label: 'STALE CUSTOMER',
        room_charge_booking_snapshot_id: '55',
      },
      {
        tender_type: 'gcash', amount_applied: '75', amount_received: '75',
        accounting_financial_account_id: '9', reference_no: 'GC-101',
        room_charge_room_number: 'NO LEAK',
      },
    ],
  });
  assert.equal(payload.note, 'Paid in two tenders');
  assert.equal(payload.payments.length, 2);
  assert.deepEqual(
    payload.payments.map(({ tender_type, amount_applied, amount_received, reference_no, accounting_financial_account_id }) => ({
      tender_type, amount_applied, amount_received, reference_no, accounting_financial_account_id,
    })),
    [
      { tender_type: 'cash', amount_applied: 125, amount_received: 150, reference_no: null, accounting_financial_account_id: 3 },
      { tender_type: 'gcash', amount_applied: 75, amount_received: 75, reference_no: 'GC-101', accounting_financial_account_id: 9 },
    ],
  );
  for (const payment of payload.payments) {
    assert.equal(payment.room_charge_booking_date, null);
    assert.equal(payment.room_charge_service_date, null);
    assert.equal(payment.room_charge_guest_label, null);
    assert.equal(payment.room_charge_room_number, null);
    assert.equal(payment.room_charge_booking_snapshot_id, null);
    assert.equal(payment.room_charge_order_source, null);
    assert.equal(payment.room_charge_beds24_booking_id, null);
  }
});

test('room charges retain guest booking and service context without pretending cash received', () => {
  const [charge] = buildPaymentWritePayload({
    orderType: 'room_service', note: 'Charge to room',
    currentSession: { business_date: '2026-10-21' },
    payments: [{
      tender_type: 'room_charge',
      amount_applied: '345', amount_received: '345',
      reference_no: 'folio-5',
      room_charge_service_type: 'signed_from_cafe',
      room_charge_booking_date: '2026-10-20',
      room_charge_service_date: '2026-10-21',
      room_charge_room_number: '205',
      room_charge_guest_label: 'Sample Guest',
      room_charge_beds24_booking_id: 'BEDS-123',
      room_charge_order_source: 'restaurant',
      room_charge_note: 'Guest signed',
      room_charge_bill_to: 'Company',
      room_charge_booking_snapshot_id: '63',
    }],
  }).payments;
  assert.deepEqual(charge, {
    tender_type: 'room_charge',
    amount_applied: 345,
    amount_received: 0,
    reference_no: 'folio-5',
    accounting_financial_account_id: null,
    room_charge_service_type: 'signed_from_cafe',
    room_charge_booking_date: '2026-10-20',
    room_charge_service_date: '2026-10-21',
    room_charge_room_number: '205',
    room_charge_guest_label: 'Sample Guest',
    room_charge_beds24_booking_id: 'BEDS-123',
    room_charge_order_source: 'restaurant',
    room_charge_note: 'Guest signed',
    room_charge_bill_to: 'Company',
    room_charge_booking_snapshot_id: 63,
  });
});

test('room charge defaults to shift date and correct service source', () => {
  const [charge] = buildPaymentWritePayload({
    orderType: 'room_service',
    currentSession: { business_date: '2026-12-31' },
    businessDate: '2027-01-01',
    payments: [{ tender_type: 'room_charge', amount_applied: '100.00' }],
  }).payments;
  assert.equal(charge.room_charge_booking_date, '2026-12-31');
  assert.equal(charge.room_charge_service_date, '2026-12-31');
  assert.equal(charge.room_charge_order_source, 'room_service');
  assert.equal(charge.room_charge_service_type, 'room_service');
  assert.equal(charge.amount_received, 0);
  const [cafeCharge] = buildPaymentWritePayload({
    orderType: 'dine_in', currentSession: null, businessDate: '2027-01-01',
    payments: [{ tender_type: 'room_charge', amount_applied: '125' }],
  }).payments;
  assert.equal(cafeCharge.room_charge_order_source, 'restaurant');
  assert.equal(cafeCharge.room_charge_booking_date, '2027-01-01');
});

test('card/transfer retain payment references and account mapping', () => {
  const { payments } = buildPaymentWritePayload({
    payments: [
      { tender_type: 'card', amount_applied: '40.50', amount_received: '', reference_no: 'CARD-A', accounting_financial_account_id: '25' },
      { tender_type: 'bank_transfer', amount_applied: '70.00', amount_received: '70', reference_no: 'BANK-7', accounting_financial_account_id: '26' },
    ],
  });
  assert.deepEqual(payments.map(p => [p.tender_type, p.amount_applied, p.amount_received, p.reference_no, p.accounting_financial_account_id]), [
    ['card', 40.5, 40.5, 'CARD-A', 25],
    ['bank_transfer', 70, 70, 'BANK-7', 26],
  ]);
});
