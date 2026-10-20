import { todayISO } from './posWorkspace.mjs';

// Pure, server-facing financial payload builders. Keep the cashier component
// concerned with state/actions and independently test these mappings.
const amount = (value, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export function buildOrderWritePayload({
  sessionId,
  discountApprovalUserId,
  orderType,
  guestName,
  activeArea,
  tableLabel,
  seatCount,
  note,
  cart = [],
}) {
  return {
    register_session_id: Number(sessionId),
    approved_by_user_id: discountApprovalUserId || null,
    order_type: orderType,
    source_channel: 'pos',
    guest_name: guestName || null,
    service_area: activeArea || null,
    table_label: tableLabel || null,
    seat_count: seatCount ? Number(seatCount) : null,
    note: note || null,
    lines: cart.map((row) => ({
      catalog_item_id: row.catalog_item_id,
      quantity: row.quantity,
      unit_price: row.price,
      discount_amount: amount(row.discount_amount),
      modifiers: (row.metadata?.groups || []).map((group) => ({
        id: group.id,
        labels: (group.selections || []).map((option) => option.label),
      })),
      note: row.note || null,
    })),
  };
}

export function buildPaymentWritePayload({
  payments = [],
  note,
  orderType,
  currentSession,
  businessDate = todayISO(),
}) {
  const stayDate = currentSession?.business_date || businessDate;
  return {
    note,
    payments: payments.map((row) => {
      const roomCharge = row.tender_type === 'room_charge';
      return {
        tender_type: row.tender_type,
        amount_applied: amount(row.amount_applied),
        amount_received: roomCharge ? 0 : amount(row.amount_received || row.amount_applied),
        reference_no: row.reference_no || null,
        accounting_financial_account_id: row.accounting_financial_account_id
          ? Number(row.accounting_financial_account_id) : null,
        room_charge_service_type: roomCharge ? (row.room_charge_service_type || 'room_service') : null,
        room_charge_booking_date: roomCharge ? (row.room_charge_booking_date || stayDate) : null,
        room_charge_service_date: roomCharge ? (row.room_charge_service_date || stayDate) : null,
        room_charge_room_number: roomCharge ? (row.room_charge_room_number || null) : null,
        room_charge_guest_label: roomCharge ? (row.room_charge_guest_label || null) : null,
        room_charge_beds24_booking_id: roomCharge ? (row.room_charge_beds24_booking_id || null) : null,
        room_charge_order_source: roomCharge
          ? (row.room_charge_order_source || (orderType === 'room_service' ? 'room_service' : 'restaurant'))
          : null,
        room_charge_note: roomCharge ? (row.room_charge_note || null) : null,
        room_charge_bill_to: roomCharge ? (row.room_charge_bill_to || null) : null,
        room_charge_booking_snapshot_id: roomCharge && row.room_charge_booking_snapshot_id
          ? Number(row.room_charge_booking_snapshot_id) : null,
      };
    }),
  };
}
