'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';
import { createRefund, fetchOrders, fetchRegisterSessions, voidOrder } from '../../lib/api';
import { printReceipt, printRefundReceipt } from '../../lib/receipt';
import ManagerOverrideModal from '../../components/ManagerOverrideModal';

function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const STATUS_OPTIONS = ['', 'draft', 'held', 'paid', 'folio_pending', 'voided'];
const REFUND_REASON_OPTIONS = [
  { value: 'guest_request', label: 'Guest Request' },
  { value: 'service_issue', label: 'Service Issue' },
  { value: 'wrong_item', label: 'Wrong Item' },
  { value: 'order_error', label: 'Order Error' },
  { value: 'quality_issue', label: 'Quality Issue' },
  { value: 'goodwill', label: 'Goodwill' },
  { value: 'other', label: 'Other' },
];

function refundedQtyByLine(order) {
  const map = {};
  for (const refund of order?.refunds || []) {
    for (const line of refund.lines || []) {
      if (!line.order_line_id) continue;
      map[line.order_line_id] = Number(map[line.order_line_id] || 0) + Number(line.quantity || 0);
    }
  }
  return map;
}

function orderDisplayState(order) {
  if (order?.refund_status === 'fully_refunded') return { label: 'Fully Refunded', tone: 'danger' };
  if (order?.refund_status === 'partially_refunded') return { label: 'Partially Refunded', tone: 'warn' };
  if (order?.status === 'paid') return { label: 'Paid', tone: 'success' };
  if (order?.status === 'folio_pending') return { label: 'Folio Pending', tone: 'warn' };
  if (order?.status === 'voided') return { label: 'Voided', tone: 'danger' };
  if (order?.status === 'held') return { label: 'Held', tone: 'warn' };
  return { label: String(order?.status || 'Unknown').replaceAll('_', ' '), tone: 'info' };
}

export default function OrdersPage() {
  const [orders, setOrders] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [filters, setFilters] = useState({ status: '', session_id: '', q: '', business_date: '', limit: 200 });
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [voidReason, setVoidReason] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [overrideMode, setOverrideMode] = useState(null);
  const [refundForm, setRefundForm] = useState({ refund_mode: 'full', amount: '', reason_code: 'guest_request', reason_text: '', note: '' });
  const [refundLineQtys, setRefundLineQtys] = useState({});
  const [refundModalOpen, setRefundModalOpen] = useState(false);

  async function loadAll({ silent = false } = {}) {
    if (!silent) setLoading(true);
    try {
      const [orderRows, sessionRows] = await Promise.all([
        fetchOrders({ ...filters, session_id: filters.session_id ? Number(filters.session_id) : undefined }),
        fetchRegisterSessions({ limit: 200 }),
      ]);
      const safeOrders = Array.isArray(orderRows) ? orderRows : [];
      setOrders(safeOrders);
      setSessions(Array.isArray(sessionRows) ? sessionRows : []);
      if (selectedOrder) setSelectedOrder(safeOrders.find((row) => row.id === selectedOrder.id) || null);
    } catch (e) {
      setError(e.message || 'Failed to load orders.');
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);
  useEffect(() => { loadAll({ silent: true }).catch(console.error); }, [filters.status, filters.session_id, filters.q, filters.business_date, filters.limit]);
  useEffect(() => {
    if (!selectedOrder) return;
    const defaults = {};
    for (const line of selectedOrder.lines || []) defaults[line.id] = '';
    setRefundLineQtys(defaults);
    setRefundForm({ refund_mode: 'full', amount: '', reason_code: 'guest_request', reason_text: '', note: '' });
  }, [selectedOrder?.id]);

  const summary = useMemo(() => {
    const paid = orders.filter((row) => row.status === 'paid');
    const folioPending = orders.filter((row) => row.status === 'folio_pending');
    return {
      paidCount: paid.length,
      paidSales: paid.reduce((sum, row) => sum + Math.max(Number(row.total_amount || 0) - Number(row.refunded_total || 0), 0), 0),
      folioPendingCount: folioPending.length,
      folioPendingSales: folioPending.reduce((sum, row) => sum + Number(row.folio_pending_amount || row.total_amount || 0), 0),
      heldCount: orders.filter((row) => row.status === 'held').length,
      draftCount: orders.filter((row) => row.status === 'draft').length,
      voidCount: orders.filter((row) => row.status === 'voided').length,
    };
  }, [orders]);

  const refundableMap = useMemo(() => refundedQtyByLine(selectedOrder), [selectedOrder]);

  function remainingLineQty(line) {
    if (!line) return 0;
    return Math.max(Number(line.quantity || 0) - Number(refundableMap[line.id] || 0), 0);
  }

  async function doVoid(managerUser) {
    setError('');
    setNotice('');
    if (!selectedOrder?.id) return;
    if (!voidReason.trim()) return setError('Enter a void reason first.');
    try {
      await voidOrder(selectedOrder.id, { reason: voidReason.trim(), approved_by_user_id: managerUser?.id });
      setNotice(`Order ${selectedOrder.order_no} voided.`);
      setVoidReason('');
      await loadAll({ silent: true });
    } catch (e) {
      setError(e.message || 'Failed to void order.');
    }
  }

  async function doRefund(managerUser) {
    setError('');
    setNotice('');
    if (!selectedOrder?.id) return;
    if (refundForm.reason_code === 'other' && !String(refundForm.reason_text || '').trim()) return setError('Explain the refund reason when Other is selected.');
    try {
      const payload = {
        refund_mode: refundForm.refund_mode,
        amount: refundForm.refund_mode === 'amount' ? Number(refundForm.amount || 0) : undefined,
        reason_code: refundForm.reason_code || undefined,
        reason_text: refundForm.reason_text || undefined,
        note: refundForm.note || undefined,
        approved_by_user_id: managerUser?.id,
      };
      if (refundForm.refund_mode === 'lines') {
        payload.lines = (selectedOrder.lines || [])
          .map((line) => ({ order_line_id: line.id, quantity: Number(refundLineQtys[line.id] || 0) }))
          .filter((line) => line.quantity > 0);
      }
      const refund = await createRefund(selectedOrder.id, payload);
      printRefundReceipt(refund);
      setNotice(`Refund ${refund.refund_no} saved for ${selectedOrder.order_no}.`);
      await loadAll({ silent: true });
      setRefundForm({ refund_mode: 'full', amount: '', reason_code: 'guest_request', reason_text: '', note: '' });
      setRefundLineQtys({});
    } catch (e) {
      setError(e.message || 'Failed to process refund.');
    }
  }

  return (
    <div className="stack">
      <section className="section">
        <div className="toolbar">
          <div>
            <h1>Orders</h1>
            <p className="muted">Inspect split tenders, reprint receipts, void paid orders with override, and process full or partial refunds without leaving the POS back office.</p>
          </div>
          {loading && <span className="badge info">Loading...</span>}
        </div>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="metric-rail">
          <div className="metric-card"><div className="muted">Paid Orders</div><div className="metric-value">{summary.paidCount}</div></div>
          <div className="metric-card"><div className="muted">Net Paid Sales</div><div className="metric-value">{money(summary.paidSales)}</div></div>
          <div className="metric-card"><div className="muted">Folio Pending</div><div className="metric-value">{summary.folioPendingCount}</div></div>
          <div className="metric-card"><div className="muted">Held</div><div className="metric-value">{summary.heldCount}</div></div>
          <div className="metric-card"><div className="muted">Drafts</div><div className="metric-value">{summary.draftCount}</div></div>
          <div className="metric-card"><div className="muted">Voided</div><div className="metric-value">{summary.voidCount}</div></div>
        </div>
      </section>

      <section className="section">
        <div className="toolbar">
          <h2>Filter Orders</h2>
          <div className="row wrap">
            <input placeholder="Search order, guest, table, note" value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} style={{ width: 240 }} />
            <label className="field-inline">Date<input type="date" value={filters.business_date} onChange={(e) => setFilters((prev) => ({ ...prev, business_date: e.target.value }))} /></label>
            <label className="field-inline">Status
              <select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}>
                {STATUS_OPTIONS.map((option) => <option key={option || 'all'} value={option}>{option || 'all'}</option>)}
              </select>
            </label>
            <label className="field-inline">Session
              <select value={filters.session_id} onChange={(e) => setFilters((prev) => ({ ...prev, session_id: e.target.value }))}>
                <option value="">All sessions</option>
                {sessions.map((row) => <option key={row.id} value={row.id}>{row.session_code} · {row.register_name}</option>)}
              </select>
            </label>
          </div>
        </div>
      </section>

      <div className="card-grid card-grid-double">
        <section className="section">
          <h2>Order List</h2>
          <table className="table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 12 }}>
            <thead>
              <tr><th>Order</th><th>Session</th><th>Status</th><th>Guest / Ref</th><th>Total</th><th>Refunded</th><th>Net</th><th>Tender</th></tr>
            </thead>
            <tbody>
              {orders.map((row) => (
                <tr key={row.id} className={selectedOrder?.id === row.id ? 'table-row-active' : ''} onClick={() => setSelectedOrder(row)} style={{ cursor: 'pointer' }}>
                  <td><strong>{row.order_no}</strong><div className="small muted">{row.created_at ? new Date(row.created_at).toLocaleString() : row.business_date}</div></td>
                  <td>{row.register_name || '-'}</td>
                  <td>
                    <span className={`badge ${orderDisplayState(row).tone}`}>{orderDisplayState(row).label}</span>
                  </td>
                  <td><div>{row.guest_name || 'Walk-in'}</div><div className="small muted">{row.table_label || row.order_type || '-'}</div></td>
                  <td>{money(row.total_amount)}</td>
                  <td>{money(row.refunded_total)}</td>
                  <td><strong>{money(Math.max(Number(row.total_amount || 0) - Number(row.refunded_total || 0), 0))}</strong></td>
                  <td>{row.primary_tender || '-'}</td>
                </tr>
              ))}
              {!orders.length && <tr><td colSpan="8" className="muted">No orders found for this filter.</td></tr>}
            </tbody>
          </table>
        </section>

        <section className="section">
          <div className="toolbar">
            <h2>Order Detail</h2>
            {selectedOrder && selectedOrder.status !== 'paid' && selectedOrder.status !== 'voided' && <Link href={`/pos?order_id=${selectedOrder.id}`} className="secondary">Open in POS</Link>}
          </div>
          {!selectedOrder && <p className="muted" style={{ marginTop: 10 }}>Select an order to inspect its lines, split payments, and cashier notes.</p>}
          {!!selectedOrder && (
            <div className="stack-tight" style={{ marginTop: 10 }}>
              <div className="card-grid">
                <div className="card"><div className="muted">Order</div><strong>{selectedOrder.order_no}</strong></div>
                <div className="card"><div className="muted">Cashier</div><strong>{selectedOrder.cashier_name || '-'}</strong></div>
                <div className="card"><div className="muted">Status</div><strong>{orderDisplayState(selectedOrder).label}</strong></div>
                <div className="card"><div className="muted">Settlement</div><strong>{selectedOrder.settlement_state || '-'}</strong></div>
                <div className="card"><div className="muted">Total</div><strong>{money(selectedOrder.total_amount)}</strong></div>
                <div className="card"><div className="muted">Refunded</div><strong>{money(selectedOrder.refunded_total)}</strong></div>
                <div className="card"><div className="muted">Remaining</div><strong>{money(selectedOrder.refundable_balance)}</strong></div>
              </div>

              <div className="card">
                <div className="row" style={{ justifyContent: 'space-between' }}><strong>Lines</strong><span className="small muted">{(selectedOrder.lines || []).length} line(s)</span></div>
                <div className="stack-tight" style={{ marginTop: 10 }}>
                  {(selectedOrder.lines || []).map((line) => <div key={line.id} className="list-row"><div><div><strong>{line.item_name_snapshot}</strong></div><div className="small muted">{line.prep_station || 'kitchen'} · Qty {line.quantity}{line.note ? ` · ${line.note}` : ''}</div></div><div className="text-right"><div><strong>{money(line.line_total)}</strong></div><div className="small muted">{money(line.unit_price)} each</div></div></div>)}
                  {!(selectedOrder.lines || []).length && <div className="muted">No lines.</div>}
                </div>
              </div>

              <div className="card">
                <div className="row" style={{ justifyContent: 'space-between' }}><strong>Payments</strong><span className="small muted">Split tender supported</span></div>
                <div className="stack-tight" style={{ marginTop: 10 }}>
                  {(selectedOrder.payment_breakdown || []).map((payment) => <div key={payment.id} className="list-row"><div><div><strong>{payment.tender_type}</strong></div><div className="small muted">{payment.destination_label || payment.reference_no || 'No reference'}</div><div className="small muted">{payment.settlement_state || '-'}</div></div><div className="text-right"><div><strong>{money(payment.amount_applied)}</strong></div>{!!payment.change_given && <div className="small muted">Change {money(payment.change_given)}</div>}</div></div>)}
                  {!(selectedOrder.payment_breakdown || []).length && <div className="muted">No payments yet.</div>}
                </div>
              </div>

              <div className="card">
                <div className="row" style={{ justifyContent: 'space-between' }}><strong>Room Charge Workflow</strong><span className="small muted">{(selectedOrder.room_charge_postings || []).length} record(s)</span></div>
                <div className="stack-tight" style={{ marginTop: 10 }}>
                  {(selectedOrder.room_charge_postings || []).map((posting) => <div key={posting.id} className="list-row"><div><div><strong>{posting.room_number}</strong> · {posting.guest_label || 'Guest'}</div><div className="small muted">Stay {posting.booking_date} · Service {posting.service_date} · {posting.service_type}</div><div className="small muted">{posting.posting_status_label}{posting.beds24_posting_reference ? ` · ${posting.beds24_posting_reference}` : ''}</div></div><div className="text-right"><div><strong>{money(posting.charge_amount)}</strong></div><div className="small muted">{posting.order_source || '-'}</div></div></div>)}
                  {!(selectedOrder.room_charge_postings || []).length && <div className="muted">No room-charge posting records on this order.</div>}
                </div>
              </div>

              <div className="card">
                <div className="row" style={{ justifyContent: 'space-between' }}><strong>Refunds</strong><span className="small muted">{(selectedOrder.refunds || []).length} recorded</span></div>
                <div className="stack-tight" style={{ marginTop: 10 }}>
                  {(selectedOrder.refunds || []).map((refund) => (
                    <div key={refund.id} className="list-row" style={{ alignItems: 'flex-start' }}>
                      <div>
                        <div><strong>{refund.refund_no}</strong></div>
                        <div className="small muted">{refund.reason_code || refund.reason_text || 'No reason'} · Approved by {refund.approved_by_name || '-'}</div>
                        <div className="small muted">{(refund.payments || []).map((payment) => `${payment.tender_type} ${money(payment.amount)}`).join(' · ') || 'No tenders'}</div>
                      </div>
                      <div className="text-right">
                        <div><strong>{money(refund.refunded_amount)}</strong></div>
                        <button type="button" className="secondary" style={{ marginTop: 8 }} onClick={() => printRefundReceipt(refund)}>Print Refund</button>
                      </div>
                    </div>
                  ))}
                  {!(selectedOrder.refunds || []).length && <div className="muted">No refunds recorded.</div>}
                </div>
              </div>

              <div className="card">
                <strong>Actions</strong>
                <div className="stack-tight" style={{ marginTop: 10 }}>
                  <textarea placeholder="Void reason" value={voidReason} onChange={(e) => setVoidReason(e.target.value)} />
                  <div className="row wrap">
                    {selectedOrder.status === 'paid' && <button type="button" className="secondary" onClick={() => printReceipt(selectedOrder)}>Print / Reprint</button>}
                    {selectedOrder.status !== 'voided' && <button type="button" className="secondary" onClick={() => setOverrideMode('void')}>Void Order</button>}
                  </div>
                </div>
              </div>

              {selectedOrder.status === 'paid' && selectedOrder.refundable_balance > 0.009 && (
                <div className="card">
                  <div className="row" style={{ justifyContent: 'space-between' }}><strong>Refund Options</strong><span className="small muted">Manager approval required</span></div>
                  <div className="stack-tight" style={{ marginTop: 10 }}>
                    <div className="row wrap" style={{ justifyContent: 'space-between' }}>
                      <span className="small muted">Refundable balance: {money(selectedOrder.refundable_balance)}</span>
                      <button type="button" className="primary" onClick={() => setRefundModalOpen(true)}>Process Refund</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {refundModalOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Order action dialog" tabIndex={-1}>
          <div className="modal-card modal-card-medium">
            <div className="modal-header">
              <div>
                <h2>Process Refund</h2>
                <p className="muted">Create a refund for order {selectedOrder?.order_no}. Manager approval required.</p>
              </div>
              <button type="button" className="secondary" onClick={() => setRefundModalOpen(false)}>Close</button>
            </div>
            <div className="modal-form stack-tight">
              <div className="card">
                <div className="row" style={{ justifyContent: 'space-between' }}>
                  <strong>Order Summary</strong>
                  <span className="small muted">Refundable: {money(selectedOrder?.refundable_balance)}</span>
                </div>
                <div className="small muted" style={{ marginTop: 8 }}>
                  Total: {money(selectedOrder?.total_amount)} · Refunded: {money(selectedOrder?.refunded_total)}
                </div>
              </div>
              <div className="row wrap">
                <label className="field-inline">Refund Mode
                  <select value={refundForm.refund_mode} onChange={(e) => setRefundForm((prev) => ({ ...prev, refund_mode: e.target.value }))}>
                    <option value="full">Full Remaining Refund</option>
                    <option value="lines">Refund by Line</option>
                    <option value="amount">Refund by Amount</option>
                  </select>
                </label>
                <label className="field-inline">Reason
                  <select value={refundForm.reason_code} onChange={(e) => setRefundForm((prev) => ({ ...prev, reason_code: e.target.value }))}>
                    {REFUND_REASON_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                  </select>
                </label>
              </div>
              {refundForm.refund_mode === 'amount' && <label className="field">Refund Amount<input type="number" min="0" step="0.01" value={refundForm.amount} onChange={(e) => setRefundForm((prev) => ({ ...prev, amount: e.target.value }))} placeholder="0.00" /></label>}
              {refundForm.refund_mode === 'lines' && (
                <div className="card">
                  <strong>Refund by Line</strong>
                  <div className="stack-tight" style={{ marginTop: 10 }}>
                    {(selectedOrder.lines || []).map((line) => (
                      <div key={line.id} className="list-row">
                        <div>
                          <div><strong>{line.item_name_snapshot}</strong></div>
                          <div className="small muted">Remaining refundable qty: {remainingLineQty(line)}</div>
                        </div>
                        <input
                          type="number"
                          min="0"
                          max={remainingLineQty(line)}
                          step="0.01"
                          value={refundLineQtys[line.id] || ''}
                          onChange={(e) => setRefundLineQtys((prev) => ({ ...prev, [line.id]: e.target.value }))}
                          style={{ width: 110 }}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <label className="field">Reason Detail<textarea value={refundForm.reason_text} onChange={(e) => setRefundForm((prev) => ({ ...prev, reason_text: e.target.value }))} placeholder="Explain why the refund is being processed." /></label>
              <label className="field">Internal Note<textarea value={refundForm.note} onChange={(e) => setRefundForm((prev) => ({ ...prev, note: e.target.value }))} placeholder="Optional note for audit trail or accounting." /></label>
              <div className="row wrap">
                <button type="button" className="secondary" onClick={() => setRefundModalOpen(false)}>Cancel</button>
                <button type="button" className="primary" disabled={refundForm.reason_code === 'other' && !String(refundForm.reason_text || '').trim()} onClick={() => { setRefundModalOpen(false); setOverrideMode('refund'); }}>Continue to Manager Approval</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ManagerOverrideModal
        open={overrideMode === 'void'}
        title="Manager Override Needed"
        subtitle="Voiding an order requires a manager or owner login."
        actionLabel="Approve Void"
        onApprove={doVoid}
        onClose={() => setOverrideMode(null)}
      />

      <ManagerOverrideModal
        open={overrideMode === 'refund'}
        title="Approve Refund"
        subtitle="Refunds require a manager or owner login and will be recorded in the audit trail."
        actionLabel="Approve Refund"
        onApprove={doRefund}
        onClose={() => setOverrideMode(null)}
      />
    </div>
  );
}
