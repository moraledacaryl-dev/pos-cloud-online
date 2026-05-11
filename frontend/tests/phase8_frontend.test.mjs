import test from "node:test";
import assert from "node:assert/strict";
import { calculatePaymentModal, deriveKdsBoard, filterRoomChargeQueue, needsManagerOverride, pickRoomChargeBooking, summarizeTerminalCart } from "../lib/ui_contracts.mjs";

test("terminal summary totals remain stable", () => {
  const summary = summarizeTerminalCart([{ price: 100, quantity: 2, discount_amount: 10 }, { price: 50, quantity: 1, discount_amount: 0 }]);
  assert.equal(summary.distinctItems, 2);
  assert.equal(summary.quantity, 3);
  assert.equal(summary.gross, 250);
  assert.equal(summary.discount, 10);
  assert.equal(summary.total, 240);
});

test("payment modal balances mixed tender and room charge correctly", () => {
  const totals = calculatePaymentModal(200, [{ tender_type: 'cash', amount_applied: 50, amount_received: 50 }, { tender_type: 'room_charge', amount_applied: 150, amount_received: 0 }]);
  assert.equal(totals.applied, 200);
  assert.equal(totals.remaining, 0);
  assert.equal(totals.folioApplied, 150);
  assert.equal(totals.balanced, true);
});

test("room-charge booking picker prefers exact room and stay match", () => {
  const booking = pickRoomChargeBooking([{ stay_date: '2026-04-20', room_number: '201', guest_name: 'Juan', booking_status: 'in_house' }, { stay_date: '2026-04-20', room_number: '202', guest_name: 'Maria', booking_status: 'in_house' }], { stayDate: '2026-04-20', roomNumber: '201', guestName: 'Juan' });
  assert.equal(booking.room_number, '201');
});

test("manager override threshold matches discount policy", () => {
  assert.equal(needsManagerOverride({ discountAmount: 600, grossAmount: 1000 }), true);
  assert.equal(needsManagerOverride({ discountAmount: 150, grossAmount: 1000 }), true);
  assert.equal(needsManagerOverride({ discountAmount: 80, grossAmount: 1000 }), false);
});

test("front-desk posting queue filters by status and search", () => {
  const rows = filterRoomChargeQueue([{ posting_status: 'pending_frontdesk_post', booking_date: '2026-04-20', room_number: '201', guest_label: 'Juan', order_no: 'ORD-1' }, { posting_status: 'posted_to_beds24', booking_date: '2026-04-20', room_number: '202', guest_label: 'Maria', order_no: 'ORD-2', beds24_posting_reference: 'INV-2' }], { posting_status: 'posted_to_beds24', q: 'INV-2' });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].room_number, '202');
});

test("KDS board groups lines by order and surfaces highest escalation", () => {
  const board = deriveKdsBoard([{ order_id: 1, order_no: 'ORD-1', escalation_state: 'watch', line_id: 11 }, { order_id: 1, order_no: 'ORD-1', escalation_state: 'critical', line_id: 12 }, { order_id: 2, order_no: 'ORD-2', escalation_state: 'normal', line_id: 21 }]);
  assert.equal(board[0].order_id, 1);
  assert.equal(board[0].escalation, 'critical');
  assert.equal(board[0].lines.length, 2);
});
