'use client';

import { useEffect, useMemo, useState } from 'react';
import { createCashMovement, fetchAccountingAccounts, fetchCashMovements, fetchRegisterSessions, fetchRegisters } from '../../lib/api';
import { cashMovementLabel, humanizeCode } from '../../lib/displayLabels.mjs';

function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const MOVEMENT_PRESETS = [
  { direction: 'out', movement_type: 'paid_out', category: '' },
  { direction: 'in', movement_type: 'paid_in', category: '' },
  { direction: 'out', movement_type: 'safe_drop', category: '' },
  { direction: 'out', movement_type: 'bank_deposit', category: '' },
  { direction: 'out', movement_type: 'drawer_transfer', category: '' },
  { direction: 'out', movement_type: 'owner_withdrawal', category: '' },
];

const TRANSFER_TYPES = new Set(['safe_drop', 'bank_deposit', 'drawer_transfer']);

export default function CashMovementsPage() {
  const [sessions, setSessions] = useState([]);
  const [registers, setRegisters] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ register_session_id: '', direction: 'out', movement_type: 'paid_out', category: '', amount: '', note: '', reference_no: '', accounting_financial_account_id: '', to_accounting_financial_account_id: '', destination_register_id: '', requires_approval: false });
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
  const needsAccountDestination = ['safe_drop', 'bank_deposit'].includes(String(form.movement_type || '').toLowerCase());
  const needsRegisterDestination = form.movement_type === 'drawer_transfer';
  const approvalRequired = isTransfer || form.movement_type === 'owner_withdrawal';
  const amount = Number(form.amount || 0);
  const drawerBefore = Number(selectedSession?.expected_cash || 0);
  const drawerAfter = drawerBefore + (form.direction === 'in' ? amount : -amount);
  const transferRows = useMemo(() => rows.filter((row) => row.is_transfer), [rows]);
  const canSubmit = !!form.register_session_id
    && !!form.category.trim()
    && amount > 0
    && (form.direction !== 'out' || !!form.reference_no.trim())
    && (!needsAccountDestination || !!form.to_accounting_financial_account_id)
    && (!needsRegisterDestination || !!form.destination_register_id);

  function applyPreset(preset) {
    const transfer = TRANSFER_TYPES.has(preset.movement_type);
    setForm((prev) => ({
      ...prev,
      ...preset,
      to_accounting_financial_account_id: '',
      destination_register_id: '',
      requires_approval: transfer || preset.movement_type === 'owner_withdrawal',
    }));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setError(''); setNotice('');
    if (!form.register_session_id) return setError('Select an open register session.');
    if (!form.category.trim()) return setError('Choose or enter a clear category.');
    if (!(amount > 0)) return setError('Enter an amount greater than zero.');
    if (form.direction === 'out' && !form.reference_no.trim()) return setError('A receipt or reference number is required for cash leaving the drawer.');
    if (needsAccountDestination && !form.to_accounting_financial_account_id) return setError('Choose the destination financial account.');
    if (needsRegisterDestination && !form.destination_register_id) return setError('Choose the destination register.');
    try {
      await createCashMovement({
        ...form,
        register_session_id: Number(form.register_session_id),
        amount: Number(form.amount || 0),
        accounting_financial_account_id: form.accounting_financial_account_id ? Number(form.accounting_financial_account_id) : selectedSession?.register_accounting_financial_account_id || null,
        to_accounting_financial_account_id: form.to_accounting_financial_account_id ? Number(form.to_accounting_financial_account_id) : null,
        destination_register_id: form.destination_register_id ? Number(form.destination_register_id) : null,
        requires_approval: !!form.requires_approval || approvalRequired,
      });
      setForm((prev) => ({ ...prev, amount: '', note: '', reference_no: '', to_accounting_financial_account_id: '', destination_register_id: '', requires_approval: approvalRequired }));
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

      <details className="section admin-create-disclosure">
        <summary><span><strong>Record a cash movement</strong><small>Paid in, paid out, safe drop, transfer, or withdrawal</small></span><span className="summary-action">Open form</span></summary>
        <div className="row wrap task-chip-row">
          {MOVEMENT_PRESETS.map((preset) => {
            const selected = form.movement_type === preset.movement_type;
            return <button key={preset.movement_type} type="button" className={selected ? 'secondary active' : 'secondary'} aria-pressed={selected} onClick={() => applyPreset(preset)}>{cashMovementLabel(preset.movement_type)}</button>;
          })}
        </div>
        <form className="form-grid" style={{ marginTop: 12 }} onSubmit={handleSubmit}>
          <label className="field">Session<select required value={form.register_session_id} onChange={(e) => setForm((prev) => ({ ...prev, register_session_id: e.target.value }))}><option value="">Select session</option>{sessions.map((row) => <option key={row.id} value={row.id}>{row.session_code}</option>)}</select></label>
          <label className="field">Movement Type<input value={cashMovementLabel(form.movement_type)} readOnly aria-readonly="true" /></label>
          <label className="field">Category<input required value={form.category} placeholder="Required — e.g. supplies, change fund" onChange={(e) => setForm((prev) => ({ ...prev, category: e.target.value }))} /></label>
          <label className="field">Amount<input required type="number" min="0.01" step="0.01" value={form.amount} onChange={(e) => setForm((prev) => ({ ...prev, amount: e.target.value }))} /></label>
          <label className="field">Receipt / Reference {form.direction === 'out' ? '(required)' : ''}<input required={form.direction === 'out'} value={form.reference_no} onChange={(e) => setForm((prev) => ({ ...prev, reference_no: e.target.value }))} /></label>
          {needsAccountDestination && <label className="field">Destination Account<select required value={form.to_accounting_financial_account_id} onChange={(e) => setForm((prev) => ({ ...prev, to_accounting_financial_account_id: e.target.value }))}><option value="">Select destination</option>{accounts.map((row) => <option key={row.id} value={row.id}>{row.name}{row.account_type ? ` · ${humanizeCode(row.account_type)}` : ''}</option>)}</select></label>}
          {needsRegisterDestination && <label className="field">Destination Register<select required value={form.destination_register_id} onChange={(e) => setForm((prev) => ({ ...prev, destination_register_id: e.target.value }))}><option value="">Select destination</option>{registers.filter((row) => String(row.id) !== String(selectedSession?.register_id)).map((row) => <option key={row.id} value={row.id}>{row.name}{row.accounting_financial_account_id ? ' · linked' : ' · not linked'}</option>)}</select></label>}
          <label className="field-inline"><input type="checkbox" checked={!!form.requires_approval || approvalRequired} onChange={(e) => setForm((prev) => ({ ...prev, requires_approval: e.target.checked }))} disabled={approvalRequired} /> {isTransfer ? 'Approval required for transfers' : form.movement_type === 'owner_withdrawal' ? 'Approval required for owner withdrawals' : 'Require manager approval'}</label>
          {isTransfer && <div className={`card ${selectedSession?.register_accounting_financial_account_id ? 'success' : 'warn'}`} style={{ gridColumn: '1 / -1' }}><strong>Accounting drawer link</strong><div className="small" style={{ marginTop: 4 }}>From: {selectedSession?.register_name || 'selected register'} → {selectedSession?.register_accounting_financial_account_id ? `account ${selectedSession.register_accounting_financial_account_id}` : 'not linked'}. To: {destinationRegister?.name || 'manual destination'} → {destinationRegister?.accounting_financial_account_id || form.to_accounting_financial_account_id || 'not linked'}.</div></div>}
          <label className="field" style={{ gridColumn: '1 / -1' }}>Note<textarea value={form.note} onChange={(e) => setForm((prev) => ({ ...prev, note: e.target.value }))} /></label>
          <div className="action-review" style={{ gridColumn: '1 / -1' }}>
            <strong>{form.direction === 'in' ? 'Add' : 'Remove'} {money(amount)} {form.direction === 'in' ? 'to' : 'from'} {selectedSession?.register_name || 'the selected drawer'}</strong>
            <span>Estimated drawer balance: {money(drawerBefore)} → {money(drawerAfter)}</span>
            <small>{form.requires_approval || approvalRequired ? 'Manager approval will be required.' : 'This event will be recorded in the audit trail.'}</small>
          </div>
          <div className="row"><button className="primary" type="submit" disabled={!canSubmit}>Review and record</button></div>
        </form>
      </details>

      <section className="section">
        <h2>Transfer History</h2>
        <table className="table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 10 }}>
          <thead><tr><th>Date</th><th>Register</th><th>Transfer</th><th>To</th><th>Amount</th><th>Approval</th><th>Reference</th></tr></thead>
          <tbody>
            {transferRows.map((row) => (
              <tr key={`transfer-${row.id}`}>
                <td>{row.event_date}</td>
                <td>{row.register_name}</td>
                <td>{cashMovementLabel(row.movement_type)}</td>
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
        <table className="table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 10 }}>
          <thead><tr><th>Date</th><th>Register</th><th>Type</th><th>Direction</th><th>Amount</th><th>Reference</th><th>Sync</th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}><td>{row.event_date}</td><td>{row.register_name}</td><td>{cashMovementLabel(row.movement_type)}</td><td>{humanizeCode(row.direction)}</td><td>{money(row.amount)}</td><td>{row.reference_no || '-'}</td><td><span className={`badge ${row.synced_to_accounting ? 'success' : 'warn'}`}>{row.synced_to_accounting ? 'Synced' : 'Pending'}</span></td></tr>
            ))}
            {!rows.length && <tr><td colSpan="7" className="muted">No cash movements yet.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
