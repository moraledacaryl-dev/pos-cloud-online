export function moneyNumber(value) {
  const num = Number(value);
  return Number.isFinite(num) ? Math.round(num * 100) / 100 : 0;
}

export function summarizeTerminalCart(cart = []) {
  const quantity = cart.reduce((sum, line) => sum + moneyNumber(line.quantity || 0), 0);
  const gross = cart.reduce((sum, line) => sum + (moneyNumber(line.price) * moneyNumber(line.quantity || 0)), 0);
  const discount = cart.reduce((sum, line) => sum + moneyNumber(line.discount_amount || 0), 0);
  return { distinctItems: cart.length, quantity, gross: moneyNumber(gross), discount: moneyNumber(discount), total: moneyNumber(Math.max(gross - discount, 0)) };
}

export function calculatePaymentModal(total, payments = []) {
  const applied = payments.reduce((sum, row) => sum + moneyNumber(row.amount_applied), 0);
  const received = payments.reduce((sum, row) => sum + moneyNumber(row.amount_received), 0);
  const folioApplied = payments
    .filter((row) => String(row.tender_type || '').toLowerCase() === 'room_charge')
    .reduce((sum, row) => sum + moneyNumber(row.amount_applied), 0);
  return {
    total: moneyNumber(total),
    applied: moneyNumber(applied),
    received: moneyNumber(received),
    remaining: moneyNumber(total - applied),
    folioApplied: moneyNumber(folioApplied),
    balanced: Math.abs(moneyNumber(total) - moneyNumber(applied)) <= 0.01,
  };
}

export function needsManagerOverride({ discountAmount = 0, grossAmount = 0 } = {}) {
  const discount = moneyNumber(discountAmount);
  const gross = moneyNumber(grossAmount);
  return discount > 0 && (discount > 500 || (gross > 0 && (discount / gross) > 0.10));
}

export function pickRoomChargeBooking(bookings = [], { stayDate = '', roomNumber = '', guestName = '', query = '' } = {}) {
  const room = String(roomNumber || '').trim().toLowerCase();
  const guest = String(guestName || query || '').trim().toLowerCase();
  const loose = String(query || '').trim().toLowerCase();
  const stay = String(stayDate || '').trim();
  const scored = bookings
    .filter((row) => !stay || String(row.stay_date || '') === stay)
    .map((row) => {
      let score = 0;
      if (room && String(row.room_number || '').trim().toLowerCase() === room) score += 5;
      if (room && String(row.room_number || '').toLowerCase().includes(room)) score += 2;
      const label = `${row.room_number || ''} ${row.guest_name || ''} ${row.guest_label || ''} ${row.beds24_booking_id || ''}`.toLowerCase();
      if (guest && label.includes(guest)) score += 3;
      if (loose && label.includes(loose)) score += 4;
      if (String(row.booking_status || '').toLowerCase() === 'in_house') score += 1;
      return { row, score };
    })
    .sort((a, b) => b.score - a.score || String(a.row.room_number || '').localeCompare(String(b.row.room_number || '')));
  return scored[0]?.row || null;
}

export function findRoomChargeBookingMatches(bookings = [], { stayDate = '', roomNumber = '', guestName = '', query = '' } = {}, limit = 6) {
  const room = String(roomNumber || '').trim().toLowerCase();
  const guest = String(guestName || '').trim().toLowerCase();
  const search = String(query || '').trim().toLowerCase();
  const stay = String(stayDate || '').trim();
  return bookings
    .filter((row) => !stay || String(row.stay_date || '') === stay)
    .map((row) => {
      const haystack = [row.room_number, row.guest_name, row.guest_label, row.beds24_booking_id].map((v) => String(v || '').toLowerCase()).join(' ');
      let score = 0;
      if (search && haystack.includes(search)) score += 5;
      if (room && String(row.room_number || '').trim().toLowerCase() === room) score += 6;
      if (room && haystack.includes(room)) score += 2;
      if (guest && haystack.includes(guest)) score += 3;
      if (String(row.booking_status || '').toLowerCase() === 'in_house') score += 1;
      return { row, score };
    })
    .filter(({ score }) => score > 0 || (!search && !room && !guest))
    .sort((a, b) => b.score - a.score || String(a.row.room_number || '').localeCompare(String(b.row.room_number || '')))
    .slice(0, limit)
    .map(({ row }) => row);
}

export function filterRoomChargeQueue(rows = [], filters = {}) {
  const q = String(filters.q || '').trim().toLowerCase();
  return rows.filter((row) => {
    if (filters.posting_status && row.posting_status !== filters.posting_status) return false;
    if (filters.stay_date && row.booking_date !== filters.stay_date) return false;
    if (filters.room_number && !String(row.room_number || '').toLowerCase().includes(String(filters.room_number).toLowerCase())) return false;
    if (!q) return true;
    return [row.room_number, row.guest_label, row.beds24_posting_reference, row.order_no, row.later_payment_status, row.bill_to]
      .some((value) => String(value || '').toLowerCase().includes(q));
  });
}

export function roomChargeStatusMeta(status) {
  const key = String(status || '').trim().toLowerCase();
  const map = {
    pending_frontdesk_post: { tone: 'warn', label: 'Pending post' },
    posted_to_beds24: { tone: 'info', label: 'Manually marked posted' },
    settled_at_frontdesk: { tone: 'success', label: 'Settled' },
    rejected: { tone: 'danger', label: 'Rejected' },
    disputed: { tone: 'warn', label: 'Disputed' },
    written_off: { tone: 'danger', label: 'Written off' },
    cancelled: { tone: 'muted', label: 'Cancelled' },
  };
  return map[key] || { tone: 'info', label: key || 'Unknown' };
}

export function summarizeRoomChargeQueue(rows = []) {
  const summary = {
    all: rows.length,
    pending_frontdesk_post: 0,
    posted_to_beds24: 0,
    settled_at_frontdesk: 0,
    attention: 0,
  };
  for (const row of rows) {
    const status = String(row.posting_status || '').toLowerCase();
    if (status in summary) summary[status] += 1;
    if (['rejected', 'disputed', 'written_off'].includes(status)) summary.attention += 1;
  }
  return summary;
}

export function rankCatalogItems(items = [], { query = '', category = 'All' } = {}) {
  const q = String(query || '').trim().toLowerCase();
  return items
    .filter((item) => category === 'All' || (item.category_name || 'Uncategorized') === category)
    .map((item) => {
      if (!q) return { item, score: 0 };
      const name = String(item.display_name || item.menu_item_name || '').toLowerCase();
      const sku = String(item.sku_code || '').toLowerCase();
      const variant = String(item.variant_name || '').toLowerCase();
      let score = 0;
      if (name === q || sku === q) score += 100;
      if (name.startsWith(q) || sku.startsWith(q)) score += 40;
      if (name.includes(q)) score += 24;
      if (variant.includes(q)) score += 12;
      if (sku.includes(q)) score += 10;
      return { item, score };
    })
    .filter(({ score }) => !q || score > 0)
    .sort((a, b) => b.score - a.score || String(a.item.display_name || '').localeCompare(String(b.item.display_name || '')))
    .map(({ item }) => item);
}

export function applyKeypadInput(currentValue, key) {
  const current = String(currentValue ?? '');
  if (key === 'clear') return '';
  if (key === 'backspace') return current.slice(0, -1);
  if (key === '.') return current.includes('.') ? current : `${current || '0'}.`;
  if (!/^[0-9]|00$/.test(String(key))) return current;
  const next = `${current}${key}`;
  if (!/^\d*(\.\d{0,2})?$/.test(next)) return current;
  return next;
}

export function summarizeOutboxRows(rows = []) {
  const summary = { all: rows.length, pending: 0, failed: 0, blocked: 0, suppressed: 0, synced: 0, retrying: 0 };
  for (const row of rows) {
    const status = String(row.status || '').toLowerCase();
    if (status in summary) summary[status] += 1;
    if (moneyNumber(row.retry_count) > 0 && !['synced', 'suppressed'].includes(status)) summary.retrying += 1;
  }
  return summary;
}

export function summarizeTerminalHealth(health = null, { online = true, error = '', offlineDraftsCount = 0 } = {}) {
  if (!online) {
    return {
      tone: 'warn',
      label: 'Offline draft mode',
      detail: 'Save orders locally. Payments, room charges, cash movements, and close session must wait for connection.',
      action: offlineDraftsCount ? 'Restore or review local drafts when POS is online again.' : 'Use Save Offline Draft before leaving the screen.',
    };
  }
  if (error) {
    return {
      tone: 'danger',
      label: 'Health check failed',
      detail: error,
      action: 'Tell a manager to open Sync Queue diagnostics if this stays red.',
    };
  }
  if (!health) {
    return {
      tone: 'info',
      label: 'Checking systems',
      detail: 'Reading POS server, Accounting sync, worker, and queue status.',
      action: 'Continue order taking while the check finishes.',
    };
  }

  const outbox = health.outbox || {};
  const issues = [];
  if (!health.database?.ok || health.database?.migration?.requires_upgrade) issues.push('database migration');
  if (!health.accounting_api?.ok) issues.push('Accounting connection');
  if (health.sync_worker?.is_stale) issues.push('sync worker');
  if (moneyNumber(outbox.blocked) > 0) issues.push(`${moneyNumber(outbox.blocked)} blocked sync`);
  if (moneyNumber(outbox.failed) > 0) issues.push(`${moneyNumber(outbox.failed)} failed sync`);
  if (offlineDraftsCount > 0) issues.push(`${offlineDraftsCount} local draft${offlineDraftsCount === 1 ? '' : 's'}`);

  if (!issues.length) {
    return {
      tone: 'success',
      label: 'Ready',
      detail: `${moneyNumber(outbox.due_now)} queued sync event${moneyNumber(outbox.due_now) === 1 ? '' : 's'} now. Worker is healthy.`,
      action: 'Normal cashier operations can continue.',
    };
  }
  const severe = issues.some((item) => /database|Accounting|blocked/.test(item));
  return {
    tone: severe ? 'danger' : 'warn',
    label: severe ? 'Sync attention' : 'Sync watch',
    detail: issues.join(' / '),
    action: severe ? 'Open Sync Queue before closing or posting room charges.' : 'Continue service, then clear the queue during the next quiet moment.',
  };
}

export function explainSyncError(row = {}) {
  const error = String(row.last_error || row.error || '').toLowerCase();
  const type = String(row.event_type || '').toLowerCase();
  const text = String(row.last_error || row.error || '').trim();
  if (!text) {
    return {
      summary: 'No error was recorded for this event.',
      action: 'Retry if the event is still pending, or inspect the raw payload before archiving.',
    };
  }
  if (type === 'room_charge.request_created' && /original receivable|not found|reverses_source|reversal/.test(error)) {
    return {
      summary: 'Accounting rejected this room-charge reversal because the original receivable was not found or not linked.',
      action: 'Confirm the original room charge synced first, then retry this reversal.',
    };
  }
  if (/401|403|unauthorized|forbidden|invalid token|secret|auth/.test(error)) {
    return {
      summary: 'Accounting rejected the sync credentials.',
      action: 'Check the Accounting URL, token, and integration secret in Settings, then retry.',
    };
  }
  if (/disabled|sync type|event type.*off|not enabled/.test(error)) {
    return {
      summary: 'This event type is disabled for sync.',
      action: 'Enable this sync type in Settings or archive the event with a clear reason.',
    };
  }
  if (/failed to fetch|network|timeout|econnrefused|unreachable|connection/.test(error)) {
    return {
      summary: 'Accounting API is unreachable.',
      action: 'Check the Accounting service and network connection, then retry.',
    };
  }
  return {
    summary: text.length > 140 ? `${text.slice(0, 140)}...` : text,
    action: 'Open details, confirm the payload is correct, then retry or archive with a note.',
  };
}

export function deriveKdsBoard(rows = []) {
  const grouped = new Map();
  for (const row of rows) {
    const key = row.order_id;
    if (!grouped.has(key)) grouped.set(key, { order_id: row.order_id, order_no: row.order_no, table_label: row.table_label, guest_name: row.guest_name, escalation: row.escalation_state || 'normal', lines: [] });
    const ticket = grouped.get(key);
    ticket.lines.push(row);
    const rank = { normal: 0, watch: 1, rush: 2, critical: 3 };
    if ((rank[row.escalation_state || 'normal'] || 0) > (rank[ticket.escalation] || 0)) ticket.escalation = row.escalation_state || 'normal';
  }
  return Array.from(grouped.values()).sort((a, b) => (a.escalation === b.escalation ? String(a.order_no || '').localeCompare(String(b.order_no || '')) : ({ critical: 0, rush: 1, watch: 2, normal: 3 }[a.escalation] - { critical: 0, rush: 1, watch: 2, normal: 3 }[b.escalation])));
}
