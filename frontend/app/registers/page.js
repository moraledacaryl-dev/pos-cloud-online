'use client';

import { useEffect, useMemo, useState } from 'react';
import { createOutlet, createRegister, fetchAccountingAccounts, fetchAccountingHealth, fetchOutlets, fetchRegisters, updateOutlet, updateRegister, validateAccountingAccount } from '../../lib/api';
import ActionModal from '../../components/ActionModal';
import { humanizeCode } from '../../lib/displayLabels.mjs';

export default function RegistersPage() {
  const [outlets, setOutlets] = useState([]);
  const [registers, setRegisters] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [accountSearch, setAccountSearch] = useState('');
  const [accountingUnavailable, setAccountingUnavailable] = useState('');
  const [outletForm, setOutletForm] = useState({ id: null, code: '', name: '', business_unit: 'F&B', is_active: true, notes: '' });
  const [registerForm, setRegisterForm] = useState({ id: null, outlet_id: '', code: '', name: '', register_type: 'cash_drawer', accounting_financial_account_id: '', accounting_financial_account_code: '', cash_tender_label: 'Cash', default_order_type: 'dine_in', is_active: true, notes: '' });
  const [validation, setValidation] = useState(null);
  const [healthRows, setHealthRows] = useState([]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [pendingStatusChange, setPendingStatusChange] = useState(null);

  async function loadAll() {
    setError('');
    try {
      const [outletRows, registerRows] = await Promise.all([fetchOutlets(), fetchRegisters()]);
      setOutlets(Array.isArray(outletRows) ? outletRows : []);
      setRegisters(Array.isArray(registerRows) ? registerRows : []);
      if (!registerForm.outlet_id && outletRows?.[0]?.id) setRegisterForm((prev) => ({ ...prev, outlet_id: String(outletRows[0].id) }));
    } catch (e) {
      setError(e.message || 'Failed to load register setup.');
    }

    try {
      const accountRows = await fetchAccountingAccounts();
      setAccounts(Array.isArray(accountRows) ? accountRows : []);
      setAccountingUnavailable('');
    } catch (e) {
      setAccounts([]);
      setAccountingUnavailable('Accounting is temporarily unavailable. Local register configuration remains visible, but drawer mapping lookup and validation are unavailable until the integration recovers.');
    }
    try {
      const health = await fetchAccountingHealth();
      setHealthRows(Array.isArray(health?.rows) ? health.rows : []);
    } catch {
      setHealthRows([]);
    }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);

  const compatibleAccounts = useMemo(() => accounts.filter((row) => /drawer|cash/i.test(String(row.account_type || ''))), [accounts]);
  const filteredAccounts = useMemo(() => compatibleAccounts.filter((row) => {
    const q = accountSearch.trim().toLowerCase();
    if (!q) return true;
    return [row.name, row.code, row.account_type, row.department].some((v) => String(v || '').toLowerCase().includes(q));
  }), [compatibleAccounts, accountSearch]);
  const selectedAccount = useMemo(() => accounts.find((row) => String(row.id) === String(registerForm.accounting_financial_account_id)) || null, [accounts, registerForm.accounting_financial_account_id]);

  async function saveOutlet(event) {
    event.preventDefault();
    setError(''); setNotice('');
    try {
      if (outletForm.id) await updateOutlet(outletForm.id, { ...outletForm });
      else await createOutlet(outletForm);
      setOutletForm({ id: null, code: '', name: '', business_unit: 'F&B', is_active: true, notes: '' });
      setNotice(`Outlet ${outletForm.id ? 'updated' : 'saved'}.`);
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to save outlet.'); }
  }

  async function saveRegister(event) {
    event.preventDefault();
    setError(''); setNotice('');
    try {
      const payload = { ...registerForm, outlet_id: Number(registerForm.outlet_id), accounting_financial_account_id: registerForm.accounting_financial_account_id ? Number(registerForm.accounting_financial_account_id) : null };
      if (registerForm.id) await updateRegister(registerForm.id, payload);
      else await createRegister(payload);
      setRegisterForm((prev) => ({ ...prev, id: null, code: '', name: '', accounting_financial_account_id: '', accounting_financial_account_code: '', notes: '' }));
      setNotice(`Register ${registerForm.id ? 'updated' : 'saved'}.`);
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to save register.'); }
  }

  async function checkMapping() {
    setError('');
    try {
      const res = await validateAccountingAccount({ account_id: registerForm.accounting_financial_account_id || undefined, account_code: registerForm.accounting_financial_account_code || undefined });
      setValidation(res);
      setAccountingUnavailable('');
      if (!res.ok) setError('No matching accounting account found for this mapping.');
    } catch (e) {
      setValidation(null);
      setAccountingUnavailable('Accounting is temporarily unavailable. Mapping validation cannot run right now; retry after the integration recovers.');
    }
  }

  function editOutlet(row) {
    setOutletForm({ ...row, id: row.id, business_unit: row.business_unit || '', notes: row.notes || '' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function editRegister(row) {
    setRegisterForm({ ...row, id: row.id, outlet_id: String(row.outlet_id || ''), accounting_financial_account_id: String(row.accounting_financial_account_id || ''), accounting_financial_account_code: row.accounting_financial_account_code || '', notes: row.notes || '' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function archiveOutlet(row) {
    try {
      await updateOutlet(row.id, { is_active: !row.is_active });
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to update outlet status.'); }
  }

  async function archiveRegister(row) {
    try {
      await updateRegister(row.id, { is_active: !row.is_active });
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to update register status.'); }
  }

  return (
    <div className="stack">
      <section className="section">
        <h1>Registers</h1>
        <p className="muted">Connect each POS register to a real accounting drawer using a searchable picker instead of typing raw IDs blindly.</p>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
        {!!accountingUnavailable && <div className="integration-status warn" role="status"><strong>Accounting unavailable</strong><p>{accountingUnavailable}</p></div>}
      </section>

      <div className="card-grid card-grid-double">
        <details className="section admin-create-disclosure" open={!!outletForm.id}>
          <summary><span><strong>{outletForm.id ? 'Edit outlet' : 'Add an outlet'}</strong><small>Business unit and outlet identity</small></span><span className="summary-action">{outletForm.id ? 'Editing' : 'Open form'}</span></summary>
          <form className="form-grid" style={{ marginTop: 12 }} onSubmit={saveOutlet}>
            <label className="field">Code<input value={outletForm.code} onChange={(e) => setOutletForm((prev) => ({ ...prev, code: e.target.value }))} /></label>
            <label className="field">Name<input value={outletForm.name} onChange={(e) => setOutletForm((prev) => ({ ...prev, name: e.target.value }))} /></label>
            <label className="field">Business Unit<input value={outletForm.business_unit} onChange={(e) => setOutletForm((prev) => ({ ...prev, business_unit: e.target.value }))} /></label>
            <label className="field">Active<select value={String(!!outletForm.is_active)} onChange={(e) => setOutletForm((prev) => ({ ...prev, is_active: e.target.value === 'true' }))}><option value="true">Active</option><option value="false">Inactive</option></select></label>
            <label className="field" style={{ gridColumn: '1 / -1' }}>Notes<textarea value={outletForm.notes} onChange={(e) => setOutletForm((prev) => ({ ...prev, notes: e.target.value }))} /></label>
            <div className="row wrap"><button className="primary" type="submit">{outletForm.id ? 'Update Outlet' : 'Save Outlet'}</button>{outletForm.id && <button type="button" className="secondary" onClick={() => setOutletForm({ id: null, code: '', name: '', business_unit: 'F&B', is_active: true, notes: '' })}>Cancel Edit</button>}</div>
          </form>
        </details>

        <details className="section admin-create-disclosure" open={!!registerForm.id}>
          <summary><span><strong>{registerForm.id ? 'Edit register' : 'Add a register'}</strong><small>Drawer, tender, and order defaults</small></span><span className="summary-action">{registerForm.id ? 'Editing' : 'Open form'}</span></summary>
          <form className="form-grid-3" style={{ marginTop: 12 }} onSubmit={saveRegister}>
            <label className="field">Outlet<select value={registerForm.outlet_id} onChange={(e) => setRegisterForm((prev) => ({ ...prev, outlet_id: e.target.value }))}><option value="">Select outlet</option>{outlets.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
            <label className="field">Register Code<input value={registerForm.code} onChange={(e) => setRegisterForm((prev) => ({ ...prev, code: e.target.value }))} /></label>
            <label className="field">Register Name<input value={registerForm.name} onChange={(e) => setRegisterForm((prev) => ({ ...prev, name: e.target.value }))} /></label>
            <label className="field">Cash Label<input value={registerForm.cash_tender_label} onChange={(e) => setRegisterForm((prev) => ({ ...prev, cash_tender_label: e.target.value }))} /></label>
            <label className="field">Default Order Type<select value={registerForm.default_order_type} onChange={(e) => setRegisterForm((prev) => ({ ...prev, default_order_type: e.target.value }))}><option value="dine_in">Dine-in</option><option value="takeout">Takeout</option><option value="delivery">Delivery</option></select></label>
            <label className="field">Active<select value={String(!!registerForm.is_active)} onChange={(e) => setRegisterForm((prev) => ({ ...prev, is_active: e.target.value === 'true' }))}><option value="true">Active</option><option value="false">Inactive</option></select></label>
            <div className="account-binding-card" style={{ gridColumn: '1 / -1' }}>
              <div><span className="eyebrow">Accounting drawer</span><strong>{selectedAccount?.name || (registerForm.accounting_financial_account_id ? `Mapped account ${registerForm.accounting_financial_account_id}` : 'No drawer selected')}</strong><div className="small muted">{selectedAccount ? `${selectedAccount.code || 'No code'} · ${humanizeCode(selectedAccount.account_type)}` : 'Choose a compatible cash/drawer account below. Raw IDs cannot be edited.'}</div></div>
              <div className="row wrap"><button type="button" className="secondary" onClick={checkMapping} disabled={!registerForm.accounting_financial_account_id || !!accountingUnavailable}>Validate</button>{registerForm.accounting_financial_account_id && <button type="button" className="secondary" onClick={() => setRegisterForm((prev) => ({ ...prev, accounting_financial_account_id: '', accounting_financial_account_code: '' }))}>Clear</button>}{validation?.ok && <span className="badge success">Valid</span>}</div>
            </div>
            <label className="field" style={{ gridColumn: '1 / -1' }}>Notes<input value={registerForm.notes} onChange={(e) => setRegisterForm((prev) => ({ ...prev, notes: e.target.value }))} /></label>
            <div className="row wrap" style={{ gridColumn: '1 / -1' }}><button className="primary" type="submit">{registerForm.id ? 'Update Register' : 'Save Register'}</button>{registerForm.id && <button type="button" className="secondary" onClick={() => setRegisterForm({ id: null, outlet_id: outlets?.[0]?.id ? String(outlets[0].id) : '', code: '', name: '', register_type: 'cash_drawer', accounting_financial_account_id: '', accounting_financial_account_code: '', cash_tender_label: 'Cash', default_order_type: 'dine_in', is_active: true, notes: '' })}>Cancel Edit</button>}</div>
          </form>
        </details>
      </div>

      <section className="section">
        <div className="toolbar"><div><h2>Choose Accounting Drawer</h2><p className="small muted">Only compatible cash and drawer accounts are shown.</p></div><input placeholder="Search cash drawers" value={accountSearch} onChange={(e) => setAccountSearch(e.target.value)} style={{ width: 240 }} disabled={!!accountingUnavailable} /></div>
        <table className="table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 10 }}>
          <thead><tr><th>Name</th><th>Code</th><th>Type</th><th>Balance</th><th>Action</th></tr></thead>
          <tbody>
            {filteredAccounts.map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td><td>{row.code || '-'}</td><td>{humanizeCode(row.account_type)}</td><td>{row.current_balance ?? '-'}</td>
                <td><button type="button" className="secondary" onClick={() => setRegisterForm((prev) => ({ ...prev, accounting_financial_account_id: String(row.id), accounting_financial_account_code: row.code || '' }))}>{String(registerForm.accounting_financial_account_id) === String(row.id) ? 'Selected' : 'Select drawer'}</button></td>
              </tr>
            ))}
            {!filteredAccounts.length && <tr><td colSpan="5" className="muted">{accountingUnavailable ? 'Accounting account lookup is temporarily unavailable.' : 'No compatible cash drawer accounts are available.'}</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="section">
        <div className="toolbar"><h2>Register Mapping Health</h2><button type="button" className="secondary" onClick={async () => { try { const h = await fetchAccountingHealth(); setHealthRows(h?.rows || []); setAccountingUnavailable(''); } catch { setHealthRows([]); setAccountingUnavailable('Accounting is temporarily unavailable. Mapping health cannot be refreshed right now.'); } }}>Refresh Health</button></div>
        <table className="table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 10 }}>
          <thead><tr><th>Register</th><th>Mapped Account</th><th>Status</th></tr></thead>
          <tbody>
            {healthRows.map((row) => (
              <tr key={row.register_id}>
                <td>{row.register_name} <span className="small muted">({row.register_code})</span></td>
                <td>{row.accounting_financial_account_id || '-'} {row.accounting_financial_account_code ? `(${row.accounting_financial_account_code})` : ''} {row.account_name ? `- ${row.account_name}` : ''}</td>
                <td><span className={`badge ${row.healthy ? 'success' : 'danger'}`}>{row.healthy ? 'healthy' : 'missing or invalid'}</span></td>
              </tr>
            ))}
            {!healthRows.length && <tr><td colSpan="3" className="muted">Mapping health is unavailable or no registers exist.</td></tr>}
          </tbody>
        </table>
      </section>

      <section className="section">
        <h2>Current Outlets</h2>
        <table className="table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 10 }}>
          <thead><tr><th>Code</th><th>Name</th><th>BU</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {outlets.map((row) => (
              <tr key={row.id}><td>{row.code}</td><td>{row.name}</td><td>{row.business_unit || '-'}</td><td><span className={`badge ${row.is_active ? 'success' : 'warn'}`}>{row.is_active ? 'active' : 'inactive'}</span></td><td><div className="row wrap"><button type="button" className="secondary" onClick={() => editOutlet(row)}>Edit</button><button type="button" className="secondary" onClick={() => setPendingStatusChange({ kind: 'outlet', row })}>{row.is_active ? 'Archive' : 'Activate'}</button></div></td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <h2>Current Registers</h2>
        <table className="table" tabIndex={0} aria-label="Scrollable data table" style={{ marginTop: 10 }}>
          <thead><tr><th>Outlet</th><th>Code</th><th>Name</th><th>Accounting Drawer</th><th>Default Type</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            {registers.map((row) => (
              <tr key={row.id}><td>{row.outlet_name}</td><td>{row.code}</td><td>{row.name}</td><td>{row.accounting_financial_account_id || '-'} {row.accounting_financial_account_code ? `(${row.accounting_financial_account_code})` : ''}</td><td>{humanizeCode(row.default_order_type)}</td><td><span className={`badge ${row.is_active ? 'success' : 'warn'}`}>{row.is_active ? 'active' : 'inactive'}</span></td><td><div className="row wrap"><button type="button" className="secondary" onClick={() => editRegister(row)}>Edit</button><button type="button" className="secondary" onClick={() => setPendingStatusChange({ kind: 'register', row })}>{row.is_active ? 'Archive' : 'Activate'}</button></div></td></tr>
            ))}
            {!registers.length && <tr><td colSpan="7" className="muted">No registers yet.</td></tr>}
          </tbody>
        </table>
      </section>
      <ActionModal
        open={!!pendingStatusChange}
        title={`${pendingStatusChange?.row?.is_active ? 'Archive' : 'Activate'} ${pendingStatusChange?.row?.name || 'record'}?`}
        description={pendingStatusChange?.row?.is_active ? 'Archiving removes this choice from new sessions. Existing transaction history is preserved; close any open session first.' : 'This makes the record available for new POS activity.'}
        confirmLabel={pendingStatusChange?.row?.is_active ? 'Archive' : 'Activate'}
        tone={pendingStatusChange?.row?.is_active ? 'danger' : 'normal'}
        onClose={() => setPendingStatusChange(null)}
        onConfirm={async () => { if (pendingStatusChange?.kind === 'outlet') await archiveOutlet(pendingStatusChange.row); else await archiveRegister(pendingStatusChange.row); setPendingStatusChange(null); }}
      />
    </div>
  );
}
