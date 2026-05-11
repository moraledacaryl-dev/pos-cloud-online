'use client';

import { useEffect, useMemo, useState } from 'react';
import { createOutlet, createRegister, fetchAccountingAccounts, fetchAccountingHealth, fetchOutlets, fetchRegisters, updateOutlet, updateRegister, validateAccountingAccount } from '../../lib/api';

export default function RegistersPage() {
  const [outlets, setOutlets] = useState([]);
  const [registers, setRegisters] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [accountSearch, setAccountSearch] = useState('');
  const [outletForm, setOutletForm] = useState({ id: null, code: '', name: '', business_unit: 'F&B', is_active: true, notes: '' });
  const [registerForm, setRegisterForm] = useState({ id: null, outlet_id: '', code: '', name: '', register_type: 'cash_drawer', accounting_financial_account_id: '', accounting_financial_account_code: '', cash_tender_label: 'Cash', default_order_type: 'dine_in', is_active: true, notes: '' });
  const [validation, setValidation] = useState(null);
  const [healthRows, setHealthRows] = useState([]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  async function loadAll() {
    try {
      const [outletRows, registerRows, accountRows] = await Promise.all([fetchOutlets(), fetchRegisters(), fetchAccountingAccounts().catch(() => [])]);
      setOutlets(Array.isArray(outletRows) ? outletRows : []);
      setRegisters(Array.isArray(registerRows) ? registerRows : []);
      setAccounts(Array.isArray(accountRows) ? accountRows : []);
      if (!registerForm.outlet_id && outletRows?.[0]?.id) setRegisterForm((prev) => ({ ...prev, outlet_id: String(outletRows[0].id) }));
    } catch (e) {
      setError(e.message || 'Failed to load register setup.');
    }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);

  const filteredAccounts = useMemo(() => accounts.filter((row) => {
    const q = accountSearch.trim().toLowerCase();
    if (!q) return true;
    return [row.name, row.code, row.account_type, row.department].some((v) => String(v || '').toLowerCase().includes(q));
  }), [accounts, accountSearch]);

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
      if (!res.ok) setError('No matching accounting account found for this mapping.');
    } catch (e) { setError(e.message || 'Failed to validate accounting mapping.'); }
  }

  function editOutlet(row) {
    setOutletForm({ ...row, id: row.id, business_unit: row.business_unit || '', notes: row.notes || '' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function editRegister(row) {
    setRegisterForm({ ...row, id: row.id, outlet_id: String(row.outlet_id || ''), accounting_financial_account_id: String(row.accounting_financial_account_id || ''), accounting_financial_account_code: row.accounting_financial_account_code || '', notes: row.notes || '' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function archiveOutlet(row) {
    updateOutlet(row.id, { is_active: !row.is_active }).then(loadAll).catch((e) => setError(e.message || 'Failed to update outlet status.'));
  }

  function archiveRegister(row) {
    updateRegister(row.id, { is_active: !row.is_active }).then(loadAll).catch((e) => setError(e.message || 'Failed to update register status.'));
  }

  return (
    <div className="stack">
      <section className="section">
        <h1>Registers</h1>
        <p className="muted">Connect each POS register to a real accounting drawer using a searchable picker instead of typing raw IDs blindly.</p>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <div className="card-grid card-grid-double">
        <section className="section">
          <h2>{outletForm.id ? 'Edit Outlet' : 'Create Outlet'}</h2>
          <form className="form-grid" style={{ marginTop: 12 }} onSubmit={saveOutlet}>
            <label className="field">Code<input value={outletForm.code} onChange={(e) => setOutletForm((prev) => ({ ...prev, code: e.target.value }))} /></label>
            <label className="field">Name<input value={outletForm.name} onChange={(e) => setOutletForm((prev) => ({ ...prev, name: e.target.value }))} /></label>
            <label className="field">Business Unit<input value={outletForm.business_unit} onChange={(e) => setOutletForm((prev) => ({ ...prev, business_unit: e.target.value }))} /></label>
            <label className="field">Active<select value={String(!!outletForm.is_active)} onChange={(e) => setOutletForm((prev) => ({ ...prev, is_active: e.target.value === 'true' }))}><option value="true">Active</option><option value="false">Inactive</option></select></label>
            <label className="field" style={{ gridColumn: '1 / -1' }}>Notes<textarea value={outletForm.notes} onChange={(e) => setOutletForm((prev) => ({ ...prev, notes: e.target.value }))} /></label>
            <div className="row wrap"><button className="primary" type="submit">{outletForm.id ? 'Update Outlet' : 'Save Outlet'}</button>{outletForm.id && <button type="button" className="secondary" onClick={() => setOutletForm({ id: null, code: '', name: '', business_unit: 'F&B', is_active: true, notes: '' })}>Cancel Edit</button>}</div>
          </form>
        </section>

        <section className="section">
          <h2>{registerForm.id ? 'Edit Register' : 'Create Register'}</h2>
          <form className="form-grid-3" style={{ marginTop: 12 }} onSubmit={saveRegister}>
            <label className="field">Outlet<select value={registerForm.outlet_id} onChange={(e) => setRegisterForm((prev) => ({ ...prev, outlet_id: e.target.value }))}><option value="">Select outlet</option>{outlets.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
            <label className="field">Register Code<input value={registerForm.code} onChange={(e) => setRegisterForm((prev) => ({ ...prev, code: e.target.value }))} /></label>
            <label className="field">Register Name<input value={registerForm.name} onChange={(e) => setRegisterForm((prev) => ({ ...prev, name: e.target.value }))} /></label>
            <label className="field">Cash Label<input value={registerForm.cash_tender_label} onChange={(e) => setRegisterForm((prev) => ({ ...prev, cash_tender_label: e.target.value }))} /></label>
            <label className="field">Default Order Type<select value={registerForm.default_order_type} onChange={(e) => setRegisterForm((prev) => ({ ...prev, default_order_type: e.target.value }))}><option value="dine_in">Dine-in</option><option value="takeout">Takeout</option><option value="delivery">Delivery</option></select></label>
            <label className="field">Active<select value={String(!!registerForm.is_active)} onChange={(e) => setRegisterForm((prev) => ({ ...prev, is_active: e.target.value === 'true' }))}><option value="true">Active</option><option value="false">Inactive</option></select></label>
            <label className="field">Accounting Drawer ID<input value={registerForm.accounting_financial_account_id} onChange={(e) => setRegisterForm((prev) => ({ ...prev, accounting_financial_account_id: e.target.value }))} /></label>
            <label className="field">Accounting Drawer Code<input value={registerForm.accounting_financial_account_code} onChange={(e) => setRegisterForm((prev) => ({ ...prev, accounting_financial_account_code: e.target.value }))} /></label>
            <div className="row wrap" style={{ alignItems: 'end' }}><button type="button" className="secondary" onClick={checkMapping}>Validate Mapping</button>{validation?.ok && <span className="badge success">{validation.account?.name}</span>}</div>
            <label className="field" style={{ gridColumn: '1 / -1' }}>Notes<input value={registerForm.notes} onChange={(e) => setRegisterForm((prev) => ({ ...prev, notes: e.target.value }))} /></label>
            <div className="row wrap" style={{ gridColumn: '1 / -1' }}><button className="primary" type="submit">{registerForm.id ? 'Update Register' : 'Save Register'}</button>{registerForm.id && <button type="button" className="secondary" onClick={() => setRegisterForm({ id: null, outlet_id: outlets?.[0]?.id ? String(outlets[0].id) : '', code: '', name: '', register_type: 'cash_drawer', accounting_financial_account_id: '', accounting_financial_account_code: '', cash_tender_label: 'Cash', default_order_type: 'dine_in', is_active: true, notes: '' })}>Cancel Edit</button>}</div>
          </form>
        </section>
      </div>

      <section className="section">
        <div className="toolbar"><h2>Accounting Account Picker</h2><input placeholder="Search drawer, bank, e-wallet" value={accountSearch} onChange={(e) => setAccountSearch(e.target.value)} style={{ width: 240 }} /></div>
        <table className="table" style={{ marginTop: 10 }}>
          <thead><tr><th>Name</th><th>Code</th><th>Type</th><th>Balance</th><th></th></tr></thead>
          <tbody>
            {filteredAccounts.map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td><td>{row.code || '-'}</td><td>{row.account_type}</td><td>{row.current_balance ?? '-'}</td>
                <td><button type="button" className="secondary" onClick={() => setRegisterForm((prev) => ({ ...prev, accounting_financial_account_id: String(row.id), accounting_financial_account_code: row.code || '' }))}>Use</button></td>
              </tr>
            ))}
            {!filteredAccounts.length && <tr><td colSpan="5" className="muted">No accounting accounts available or API not configured yet.</td></tr>}
          </tbody>
        </table>
      </section>



<section className="section">
  <div className="toolbar"><h2>Register Mapping Health</h2><button type="button" className="secondary" onClick={async () => { const h = await fetchAccountingHealth(); setHealthRows(h?.rows || []); }}>Refresh Health</button></div>
  <table className="table" style={{ marginTop: 10 }}>
    <thead><tr><th>Register</th><th>Mapped Account</th><th>Status</th></tr></thead>
    <tbody>
      {healthRows.map((row) => (
        <tr key={row.register_id}>
          <td>{row.register_name} <span className="small muted">({row.register_code})</span></td>
          <td>{row.accounting_financial_account_id || '-'} {row.accounting_financial_account_code ? `(${row.accounting_financial_account_code})` : ''} {row.account_name ? `- ${row.account_name}` : ''}</td>
          <td><span className={`badge ${row.healthy ? 'success' : 'danger'}`}>{row.healthy ? 'healthy' : 'missing or invalid'}</span></td>
        </tr>
      ))}
      {!healthRows.length && <tr><td colSpan="3" className="muted">No mapping health data yet.</td></tr>}
    </tbody>
  </table>
</section>

      <section className="section">
        <h2>Current Outlets</h2>
        <table className="table" style={{ marginTop: 10 }}>
          <thead><tr><th>Code</th><th>Name</th><th>BU</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {outlets.map((row) => (
              <tr key={row.id}><td>{row.code}</td><td>{row.name}</td><td>{row.business_unit || '-'}</td><td><span className={`badge ${row.is_active ? 'success' : 'warn'}`}>{row.is_active ? 'active' : 'inactive'}</span></td><td><div className="row wrap"><button type="button" className="secondary" onClick={() => editOutlet(row)}>Edit</button><button type="button" className="secondary" onClick={() => archiveOutlet(row)}>{row.is_active ? 'Archive' : 'Activate'}</button></div></td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="section">
        <h2>Current Registers</h2>
        <table className="table" style={{ marginTop: 10 }}>
          <thead><tr><th>Outlet</th><th>Code</th><th>Name</th><th>Accounting Drawer</th><th>Default Type</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {registers.map((row) => (
              <tr key={row.id}><td>{row.outlet_name}</td><td>{row.code}</td><td>{row.name}</td><td>{row.accounting_financial_account_id || '-'} {row.accounting_financial_account_code ? `(${row.accounting_financial_account_code})` : ''}</td><td>{row.default_order_type}</td><td><span className={`badge ${row.is_active ? 'success' : 'warn'}`}>{row.is_active ? 'active' : 'inactive'}</span></td><td><div className="row wrap"><button type="button" className="secondary" onClick={() => editRegister(row)}>Edit</button><button type="button" className="secondary" onClick={() => archiveRegister(row)}>{row.is_active ? 'Archive' : 'Activate'}</button></div></td></tr>
            ))}
            {!registers.length && <tr><td colSpan="7" className="muted">No registers yet.</td></tr>}
          </tbody>
        </table>
      </section>
    </div>
  );
}
