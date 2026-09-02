export function money(value) { return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`; }
function esc(text) { return String(text || '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'); }
export function buildReceiptHtml(receipt) {
  const rows = (receipt?.lines || []).map((line) => `<div class="line-row"><div>${esc(line.item_name_snapshot || line.name)} × ${Number(line.quantity || 0)}</div><div>${money(line.line_total || ((line.price || 0) * (line.quantity || 0)))}</div></div>${line.note ? `<div class="line-note">${esc(line.note)}</div>` : ''}`).join('');
  const payments = (receipt?.payment_breakdown || []).map((payment) => `<div class="line-row"><div>${esc(payment.tender_type)}</div><div>${money(payment.amount_applied)}</div></div><div class="line-note">${esc(payment.destination_label || payment.reference_no || '')}${payment.settlement_state ? ` · ${esc(payment.settlement_state)}` : ''}</div>`).join('');
  const settlementRows = [`<div class="line-row"><div>Settled</div><div>${money(receipt?.settled_amount ?? receipt?.paid_amount ?? 0)}</div></div>`];
  if (Number(receipt?.folio_pending_amount || 0) > 0) settlementRows.push(`<div class="line-row"><div>Folio Pending</div><div>${money(receipt?.folio_pending_amount || 0)}</div></div>`);
  return `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${esc(receipt?.order_no || 'Receipt')}</title><style>body{font-family:Arial,Helvetica,sans-serif;padding:20px;color:#111}.wrap{max-width:320px;margin:0 auto}h1{font-size:18px;margin:0 0 8px}.muted{color:#666;font-size:12px}.line-row{display:flex;justify-content:space-between;gap:10px;padding:4px 0}.line-note{font-size:11px;color:#666;padding:0 0 4px}.rule{border-top:1px dashed #bbb;margin:10px 0}.total{font-size:16px;font-weight:700}</style></head><body><div class="wrap"><h1>Hidden Oasis POS</h1><div>${esc(receipt?.order_no || '')}</div><div class="muted">${esc(receipt?.business_date || '')} · ${esc(receipt?.guest_name || 'Walk-in')} · ${esc(receipt?.table_label || receipt?.order_type || '-')}</div><div class="muted">Status: ${esc(receipt?.status || '-')} · Settlement: ${esc(receipt?.settlement_state || '-')}</div><div class="rule"></div>${rows}<div class="rule"></div><div class="line-row"><div>Subtotal</div><div>${money(receipt?.subtotal_amount || 0)}</div></div><div class="line-row"><div>Discount</div><div>${money(receipt?.discount_amount || 0)}</div></div><div class="line-row total"><div>Total</div><div>${money(receipt?.total_amount || 0)}</div></div>${settlementRows.join('')}<div class="rule"></div>${payments || '<div class="muted">No payment rows found.</div>'}<div class="muted" style="margin-top:12px">${Number(receipt?.folio_pending_amount || 0) > 0 ? 'Awaiting folio posting / later settlement.' : 'Thank you.'}</div></div></body></html>`;
}
export function printReceipt(receipt) { if (typeof window === 'undefined' || !receipt) return; const popup = window.open('', '_blank', 'width=420,height=720'); if (!popup) return; popup.document.open(); popup.document.write(buildReceiptHtml(receipt)); popup.document.close(); popup.focus(); setTimeout(() => popup.print(), 180); }
const LAST_RECEIPT_KEY = 'pos_last_receipt_v2';
const LEGACY_LAST_RECEIPT_KEY = 'pos_last_receipt';
const LAST_RECEIPT_TTL_MS = 12 * 60 * 60 * 1000;

export function saveLastReceipt(receipt, { ownerId = null, registerId = null } = {}) {
  if (typeof window === 'undefined' || !receipt) return;
  const stored = {
    schema_version: 2,
    saved_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + LAST_RECEIPT_TTL_MS).toISOString(),
    owner_id: ownerId,
    register_id: registerId,
    receipt,
  };
  localStorage.setItem(LAST_RECEIPT_KEY, JSON.stringify(stored));
  localStorage.removeItem(LEGACY_LAST_RECEIPT_KEY);
}

export function loadLastReceipt({ ownerId = null, registerId = null } = {}) {
  if (typeof window === 'undefined') return null;
  try {
    const stored = JSON.parse(localStorage.getItem(LAST_RECEIPT_KEY) || 'null');
    if (!stored?.receipt || Date.parse(stored.expires_at || '') <= Date.now()) {
      clearLastReceipt();
      return null;
    }
    if (ownerId != null && stored.owner_id != null && String(ownerId) !== String(stored.owner_id)) return null;
    if (registerId != null && stored.register_id != null && String(registerId) !== String(stored.register_id)) return null;
    return stored.receipt;
  } catch {
    clearLastReceipt();
    return null;
  }
}

export function clearLastReceipt() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(LAST_RECEIPT_KEY);
  localStorage.removeItem(LEGACY_LAST_RECEIPT_KEY);
}


export function buildRefundReceiptHtml(refund) {
  const rows = (refund?.lines || []).map((line) => `<div class="line-row"><div>${esc(line.item_name_snapshot || 'Refund')} × ${Number(line.quantity || 0)}</div><div>${money(line.refunded_line_total || 0)}</div></div>${line.note ? `<div class="line-note">${esc(line.note)}</div>` : ''}`).join('');
  const payments = (refund?.payments || []).map((payment) => `<div class="line-row"><div>${esc(payment.tender_type)}</div><div>${money(payment.amount)}</div></div>`).join('');
  return `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${esc(refund?.refund_no || 'Refund Receipt')}</title><style>body{font-family:Arial,Helvetica,sans-serif;padding:20px;color:#111}.wrap{max-width:320px;margin:0 auto}h1{font-size:18px;margin:0 0 8px}.muted{color:#666;font-size:12px}.line-row{display:flex;justify-content:space-between;gap:10px;padding:4px 0}.line-note{font-size:11px;color:#666;padding:0 0 4px}.rule{border-top:1px dashed #bbb;margin:10px 0}.total{font-size:16px;font-weight:700}</style></head><body><div class="wrap"><h1>Hidden Oasis POS</h1><div>Refund Receipt</div><div><strong>${esc(refund?.refund_no || '')}</strong></div><div class="muted">Order ${esc(refund?.order_no || '')} · ${esc(refund?.created_at || '')}</div><div class="muted">Approved by ${esc(refund?.approved_by_name || '-')}</div><div class="rule"></div>${rows}<div class="rule"></div><div class="line-row total"><div>Refund Total</div><div>${money(refund?.refunded_amount || 0)}</div></div><div class="line-row"><div>Reason</div><div>${esc(refund?.reason_code || refund?.reason_text || '-')}</div></div><div class="rule"></div>${payments || '<div class="muted">No refund tender rows found.</div>'}<div class="muted" style="margin-top:12px">Processed refund.</div></div></body></html>`;
}

export function printRefundReceipt(refund) { if (typeof window === 'undefined' || !refund) return; const popup = window.open('', '_blank', 'width=420,height=720'); if (!popup) return; popup.document.open(); popup.document.write(buildRefundReceiptHtml(refund)); popup.document.close(); popup.focus(); setTimeout(() => popup.print(), 180); }

export function buildCloseSessionPacketHtml(session) {
  const denomRows = (session?.denomination_lines || []).map((line) => {
    const amount = Number(line.amount || 0);
    if (!amount) return '';
    return `<div class="line-row"><div>${esc(line.line_label || line.label || 'Cash line')}</div><div>${money(amount)}</div></div>${line.notes ? `<div class="line-note">${esc(line.notes)}</div>` : ''}`;
  }).join('');
  return `<!DOCTYPE html><html><head><meta charset="utf-8" /><title>${esc(session?.session_code || 'Close Packet')}</title><style>body{font-family:Arial,Helvetica,sans-serif;padding:20px;color:#111}.wrap{max-width:360px;margin:0 auto}h1{font-size:18px;margin:0 0 8px}.muted{color:#666;font-size:12px}.line-row{display:flex;justify-content:space-between;gap:10px;padding:4px 0}.line-note{font-size:11px;color:#666;padding:0 0 4px}.rule{border-top:1px dashed #bbb;margin:10px 0}.total{font-size:16px;font-weight:700}.sign{margin-top:28px;border-top:1px solid #111;padding-top:6px;font-size:12px}</style></head><body><div class="wrap"><h1>Hidden Oasis POS</h1><div><strong>Shift Close Packet</strong></div><div class="muted">${esc(session?.session_code || '')} · ${esc(session?.business_date || '')} · ${esc(session?.shift_name || '')}</div><div class="muted">${esc(session?.register_name || 'Register')}</div><div class="rule"></div><div class="line-row"><div>Opening Float</div><div>${money(session?.opening_float || 0)}</div></div><div class="line-row"><div>Expected Cash</div><div>${money(session?.closing_expected_cash || 0)}</div></div><div class="line-row"><div>Counted Cash</div><div>${money(session?.closing_actual_cash || 0)}</div></div><div class="line-row total"><div>Variance</div><div>${money(session?.variance_amount || 0)}</div></div><div class="rule"></div>${denomRows || '<div class="muted">No denomination lines entered.</div>'}<div class="rule"></div><div class="line-note">Close mode: ${esc(session?.close_mode || '-')} ${session?.blind_close ? '· blind close' : ''}</div><div class="line-note">Closed by: ${esc(session?.closed_by_name || '-')}</div><div class="line-note">Sign-off: ${esc(session?.sign_off_name || '-')} ${session?.sign_off_role ? `(${esc(session.sign_off_role)})` : ''}</div>${session?.variance_note ? `<div class="line-note">Variance note: ${esc(session.variance_note)}</div>` : ''}${session?.closing_note ? `<div class="line-note">Close note: ${esc(session.closing_note)}</div>` : ''}<div class="sign">Cashier signature</div><div class="sign">Manager signature</div></div></body></html>`;
}

export function printCloseSessionPacket(session) { if (typeof window === 'undefined' || !session) return; const popup = window.open('', '_blank', 'width=460,height=760'); if (!popup) return; popup.document.open(); popup.document.write(buildCloseSessionPacketHtml(session)); popup.document.close(); popup.focus(); setTimeout(() => popup.print(), 180); }
