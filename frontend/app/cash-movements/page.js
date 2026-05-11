'use client';

import { useEffect, useMemo, useState } from 'react';
import { createCashMovement, fetchAccountingAccounts, fetchCashMovements, fetchRegisterSessions, fetchRegisters } from '../../lib/api';

function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const MOVEMENT_PRESETS = [
  { direction: 'out', movement_type: 'paid_out', category: 'Emergency Purchase' },
  { direction: 'in', movement_type: 'paid_in', category: 'Cash In' },
  { direction: 'out', movement_type: 'safe_drop', category: 'Safe Drop' },
  { direction: 'out', movement_type: 'bank_deposit', category: 'Bank Deposit' },
  { direction: 'out', movement_type: 'drawer_transfer', category: 'Drawer Transfer' },
  { direction: 'out', movement_type: 'owner_withdrawal', category: 'Owner Withdrawal' },
];

const TRANSFER_TYPES = new Set(['safe_drop', 'bank_deposit', 'drawer_transfer']);

export default function CashMovementsPage() {
  const [sessions, setSessions] = useState([]);
  const [registers, setRegisters] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ register_session_id: '', direction: 'out', movement_type: 'paid_out', category: 'Emergency Purchase', amount: '', note: '', reference_no: '', accounting_financial_account_id: '', to_accounting_financial_account_id: '', destination_register_id: '', requires_approval: false });
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function loadAll() {
    try {
      const [sessionRows, movementRows, accountRows, registerRows] = await Promise.all([
        fetchRegisterSessions({ status: 'open', limit: 50 }),
        fetchCashMovements({ limit: 300 }),
        fetchAccountingAccounts().catch(() => []),
        fetchRegisters(true),
      ]);
      setSessions(Array.isArray(sessionRows) ? sessionRows : []);
      setRows(Array.isArray(movementRows) ? movementRows : []);
      setAccounts(Array.isArray(accountRows) ? accountRows : []);
      setRegisters(Array.isArray(registerRows) ? registerRows : []);
      if (!form.register_session_id && sessionRows?.[0]?.id) setForm((prev) => ({ ...prev, register_session_id: String(sessionRows[0].id) }));
    } catch (e) { setError(e.message || 'Failed to load cash movements.'); }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);

  const selectedSession = useMemo(() => sessions.find((row) => String(row.id) === String(form.register_session_id)) || null, [sessions, form.register_session_id]);
  const destinationRegister = useMemo(() => registers.find((row) => String(row.id) === String(form.destination_register_id)) || null, [registers, form.destination_register_id]);
  const isTransfer = TRANSFER_TYPES.has(String(form.movement_type || '').toLowerCase());
  const transferRows = useMemo(() => rows.filter((row) => row.is_transfer), [rows]);

  function applyPreset(preset) {
    const transfer = TRANSFER_TYPES.has(preset.movement_type);
    setForm((prev) => ({ ...prev, ...preset, requires_approval: transfer || prev.requires_approval }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(''); setNotice('');
    try {
      await createCashMovement({
        ...form,
        register_session_id: Number(form.register_session_id),
        amount: Number(form.amount || 0),
        accounting_financial_account_id: form.accounting_financial_account_id ? Number(form.accounting_financial_account_id) : selectedSession?.register_accounting_financial_account_id || null,
        to_accounting_financial_account_id: form.to_accounting_financial_account_id ? Number(form.to_accounting_financial_account_id) : null,
        destination_register_id: form.destination_register_id ? Number(form.destination_register_id) : null,
        requires_approval: !!form.requires_approval || isTransfer,
      });
      setForm((prev) => ({ ...prev, amount: '', note: '', reference_no: '', to_accounting_financial_account_id: '', destination_register_id: '', requires_approval: isTransfer }));
      setNotice('Cash movement recorded.');
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to create cash movement.'); }
  }

  return (
    <div className="stack">
      <section className="section">
        <h1>Cash Movements</h1>
        <p className="muted">Record paid outs, safe drops, bank deposits, and drawer transfers with destination tracking, approval awareness, and transfer history.</p>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="row wrap" style={{ marginBottom: 12 }}>
          {MOVEMENT_PRESETS.map((preset) => <button key={preset.movement_type} type="button" className="secondary" onClick={() => applyPreset(preset)}>{preset.movement_type}</button>)}
        </div>
        <form className="form-grid" style={{ marginTop: 12 }} onSubmit={handleSubmit}>
          <label className="field">Session<select value={form.register_session_id} onChange={(e) => setForm((prev) => ({ ...prev, register_session_id: e.target.value }))}><option value="">Select session</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.session_code}</option>)}</select></label>
          <label className="field">Direction<select value={form.direction} onChange={(e) => setForm((prev) => ({ ...prev, direction: e.target.value, movement_type: e.target.value === 'in' ? 'paid_in' : prev.movement_type }))}><option value="in">In</option><option value="out">Out</option></select></label>
          <label className="field">Movement Type<input value={form.movement_type} onChange={(e) => setForm((prev) => ({ ...prev, movement_type: e.target.value, requires_approval: TRANSFER_TYPES.has(String(e.target.value || '').toLowerCase()) || prev.requires_approval }))} /></label>
          <label className="field">Category<input value={form.category} onChange={(e) => setForm((prev) => ({ ...prev, category: e.target.value }))} /></label>
          <label className="field">Amount<input type="number" step="0.01" value={form.amount} onChange={(e) => setForm((prev) => ({ ...prev, amount: e.target.value }))} /></label>
          <label className="field">Reference No<input value={form.reference_no} onChange={(e) => setForm((prev) => ({ ...prev, reference_no: e.target.value }))} /></label>
          <label className="field">From Account<select value={form.accounting_financial_account_id} onChange={(e) => setForm((prev) => ({ ...prev, accounting_financial_account_id: e.target.value }))}><option value="">Use mapped drawer</option>{accounts.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label className="field">To Account<select value={form.to_accounting_financial_account_id} onChange={(e) => setForm((prev) => ({ ...prev, to_accounting_financial_account_id: e.target.value }))}><option value="">None</option>{accounts.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label className="field">Destination Register<select value={form.destination_register_id} onChange={(e) => setForm((prev) => ({ ...prev, destination_register_id: e.target.value }))}><option value="">None</option>{registers.map((row) => <option key={row.id} value={row.id}>{row.name}{row.accounting_financial_account_id ? ` → account ${row.accounting_financial_account_id}` : ' (not linked)'}</option>)}</select></label>
          <label className="field-inline"><input type="checkbox" checked={!!form.requires_approval || isTransfer} onChange={(e) => setForm((prev) => ({ ...prev, requires_approval: e.target.checked }))} disabled={isTransfer} /> {isTransfer ? 'Approval required for transfers' : 'Require manager approval'}</label>
          {isTransfer && <div className={`card ${selectedSession?.register_accounting_financial_account_id ? 'success' : 'warn'}`} style={{ gridColumn: '1 / -1' }}><strong>Accounting drawer link</strong><div className="small" style={{ marginTop: 4 }}>From: {selectedSession?.register_name || 'selected register'} → {selectedSession?.register_accounting_financial_account_id ? `account ${selectedSession.register_accounting_financial_account_id}` : 'not linked'}. To: {destinationRegister?.name || 'manual destination'} → {destinationRegister?.accounting_financial_account_id || form.to_accounting_financial_account_id || 'not linked'}.</div></div>}
          <label className="field" style={{ gridColumn: '1 / -1' }}>Note<textarea value={form.note} onChange={(e) => setForm((prev) => ({ ...prev, note: e.target.value }))} /></label>
          <div className="row"><button className="primary" type="submit">Save Movement</button></div>
        </form>
      </section>

      <section className="section">
        <h2>Transfer History</h2>
        <table className="table" style={{ marginTop: 10 }}>
          <thead><tr><th>Date</th><th>Register</th><th>Transfer</th><th>To</th><th>Amount</th><th>Approval</th><th>Reference</th></tr></thead>
          <tbody>
            {transferRows.map((row) => (
              <tr key={`transfer-${row.id}`}>
                <td>{row.event_date}</td>
                <td>{row.register_name}</td>
                <td>{row.movement_type}</td>
                <td>{row.destination_register_name || row.to_accounting_financial_account_id || '-'}</td>
                <td>{money(row.amount)}</td>
                <td>{row.approved_by_name || (row.requires_approval ? 'required' : '-')}</td>
                <td>{row.reference_no || row.transfer_group_uuid || '-'}</td>
              </tr>
            ))}
            {!transferRows.length && <tr><td colSpan="7" className="muted">No transfer history yet.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="section">
        <h2>Recent Drawer Events</h2>
        <table className="table" style={{ marginTop: 10 }}>
          <thead><tr><th>Date</th><th>Register</th><th>Type</th><th>Direction</th><th>Amount</th><th>Reference</th><th>Sync</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}><td>{row.event_date}</td><td>{row.register_name}</td><td>{row.movement_type}</td><td>{row.direction}</td><td>{money(row.amount)}</td><td>{row.reference_no || '-'}</td><td><span className={`badge ${row.synced_to_accounting ? 'success' : 'warn'}`}>{row.synced_to_accounting ? 'synced' : 'pending'}</span></td></tr>
            ))}
            {!rows.length && <tr><td colSpan="7" className="muted">No cash movements yet.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
