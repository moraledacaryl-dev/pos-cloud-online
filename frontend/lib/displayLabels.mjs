const HUMAN_LABELS = {
  paid_out: 'Paid Out',
  paid_in: 'Paid In',
  safe_drop: 'Safe Drop',
  bank_deposit: 'Bank Deposit',
  drawer_transfer: 'Drawer Transfer',
  owner_withdrawal: 'Owner Withdrawal',
  adjustment_in: 'Adjustment In',
  adjustment_out: 'Adjustment Out',
  cash_adjustment: 'Cash Adjustment',
  room_charge: 'Room Charge',
  bank_transfer: 'Bank Transfer',
  in: 'In',
  out: 'Out',
};

export function humanizeCode(value, fallback = 'Unknown') {
  const code = String(value || '').trim();
  if (!code) return fallback;
  if (HUMAN_LABELS[code.toLowerCase()]) return HUMAN_LABELS[code.toLowerCase()];
  return code
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function cashMovementLabel(value) {
  return humanizeCode(value, 'Cash Movement');
}

export function auditActionLabel(value) {
  return humanizeCode(value, 'Audit Event');
}
