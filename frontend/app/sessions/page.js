'use client';

import { useEffect, useMemo, useState } from 'react';
import { closeRegisterSession, fetchRegisterSessions, fetchRegisters, openRegisterSession, reopenRegisterSession } from '../../lib/api';
import ActionModal from '../../components/ActionModal';

function todayISO() {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

function money(value) {
  return `₱${Number(value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const DENOMS = [1000, 500, 200, 100, 50, 20, 10, 5, 1];

export default function SessionsPage() {
  const [registers, setRegisters] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [filters, setFilters] = useState({ status: 'all', q: '', showArchived: true });
  const [form, setForm] = useState({ register_id: '', business_date: todayISO(), shift_name: 'AM', opening_float: '0', opening_note: '' });
  const [closeForm, setCloseForm] = useState({});
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [reopenSessionId, setReopenSessionId] = useState(null);

  async function loadAll() {
    try {
      const [registerRows, sessionRows] = await Promise.all([fetchRegisters(true), fetchRegisterSessions({ limit: 150 })]);
      setRegisters(Array.isArray(registerRows) ? registerRows : []);
      setSessions(Array.isArray(sessionRows) ? sessionRows : []);
      if (!form.register_id && registerRows?.[0]?.id) setForm((prev) => ({ ...prev, register_id: String(registerRows[0].id) }));
    } catch (e) {
      setError(e.message || 'Failed to load sessions.');
    }
  }

  useEffect(() => { loadAll().catch(console.error); }, []);

  const filteredSessions = useMemo(() => {
    const q = String(filters.q || '').trim().toLowerCase();
    return sessions.filter((row) => {
      if (filters.status !== 'all' && row.status !== filters.status) return false;
      if (!filters.showArchived && row.status !== 'open') return false;
      if (!q) return true;
      return [row.session_code, row.register_name, row.business_date, row.shift_name, row.status, row.variance_note].some((value) => String(value || '').toLowerCase().includes(q));
    });
  }, [sessions, filters]);
  const selectedOpenRegister = useMemo(() => registers.find((row) => String(row.id) === String(form.register_id)) || null, [registers, form.register_id]);

  const sessionSummary = useMemo(() => ({
    open: sessions.filter((row) => row.status === 'open').length,
    closed: sessions.filter((row) => row.status === 'closed').length,
    blind: sessions.filter((row) => row.blind_close || row.close_mode === 'blind').length,
    withVariance: sessions.filter((row) => Math.abs(Number(row.variance_amount || 0)) > 0.009).length,
  }), [sessions]);

  function ensureCloseState(sessionId) {
    setCloseForm((prev) => prev[sessionId] ? prev : ({
      ...prev,
      [sessionId]: {
        closing_actual_cash: '',
        closing_note: '',
        close_mode: 'verified',
        blind_close: false,
        variance_note: '',
        sign_off_name: '',
        sign_off_role: '',
        denomination_lines: DENOMS.map((amount, idx) => ({ line_label: String(amount), amount: 0, sort_order: idx })),
      },
    }));
  }

  async function handleOpen(event) {
    event.preventDefault();
    setError('');
    setNotice('');
    try {
      await openRegisterSession({ ...form, register_id: Number(form.register_id), opening_float: Number(form.opening_float || 0) });
      setNotice('Register session opened.');
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to open session.'); }
  }

  function updateDenom(sessionId, label, qty) {
    setCloseForm((prev) => {
      const state = prev[sessionId] || { denomination_lines: [] };
      const lines = (state.denomination_lines || []).map((row) => row.line_label === label ? { ...row, amount: Number(label) * Number(qty || 0), notes: `qty=${qty || 0}` } : row);
      const total = lines.reduce((sum, row) => sum + Number(row.amount || 0), 0);
      return { ...prev, [sessionId]: { ...state, denomination_lines: lines, closing_actual_cash: total } };
    });
  }

  async function handleClose(sessionId) {
    setError('');
    setNotice('');
    try {
      const payload = closeForm[sessionId] || { closing_actual_cash: 0, closing_note: '', close_mode: 'verified', blind_close: false, denomination_lines: [] };
      await closeRegisterSession(sessionId, payload);
      setNotice(`Closed session ${sessionId}.`);
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to close session.'); }
  }

  async function handleReopen(sessionId, reason) {
    try {
      await reopenRegisterSession(sessionId, { reason, note: '' });
      setNotice(`Reopened session ${sessionId}.`);
      await loadAll();
    } catch (e) { setError(e.message || 'Failed to reopen session.'); }
  }

  return (
    <div className="stack">
      <section className="section">
        <h1>Register Sessions</h1>
        <p className="muted">Open, blind-close, verify by denomination, reopen with reason, and keep archived close history easy to filter.</p>
        {!!notice && <p className="notice-text" style={{ marginTop: 8 }}>{notice}</p>}
        {!!error && <p className="error-text" style={{ marginTop: 8 }}>{error}</p>}
      </section>

      <section className="section">
        <div className="card-grid" style={{ marginBottom: 14 }}>
          <div className="card"><div className="muted">Open sessions</div><div className="kpi">{sessionSummary.open}</div></div>
          <div className="card"><div className="muted">Closed archive</div><div className="kpi">{sessionSummary.closed}</div></div>
          <div className="card"><div className="muted">Blind closes</div><div className="kpi">{sessionSummary.blind}</div></div>
          <div className="card"><div className="muted">Variance cases</div><div className="kpi">{sessionSummary.withVariance}</div></div>
        </div>

        <h2>Open New Session</h2>
        <form className="form-grid" style={{ marginTop: 12 }} onSubmit={handleOpen}>
          <label className="field">Register<select value={form.register_id} onChange={(e) => setForm((prev) => ({ ...prev, register_id: e.target.value }))}><option value="">Select register</option>{registers.map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label className="field">Business Date<input type="date" value={form.business_date} onChange={(e) => setForm((prev) => ({ ...prev, business_date: e.target.value }))} /></label>
          <label className="field">Shift<input value={form.shift_name} onChange={(e) => setForm((prev) => ({ ...prev, shift_name: e.target.value }))} /></label>
          <label className="field">Opening Float<input type="number" step="0.01" value={form.opening_float} onChange={(e) => setForm((prev) => ({ ...prev, opening_float: e.target.value }))} /></label>
          <label className="field" style={{ gridColumn: '1 / -1' }}>Opening Note<textarea value={form.opening_note} onChange={(e) => setForm((prev) => ({ ...prev, opening_note: e.target.value }))} /></label>
          {selectedOpenRegister && !selectedOpenRegister.accounting_financial_account_id && <div className="card warn" style={{ gridColumn: '1 / -1' }}><strong>Manager setup required</strong><div className="small">This register is missing its Accounting drawer mapping. Map it in Registers before opening a shift.</div></div>}
          <div className="row"><button className="primary" type="submit" disabled={!selectedOpenRegister?.accounting_financial_account_id}>Open Session</button></div>
        </form>
      </section>

      <section className="section">
        <div className="toolbar">
          <div>
            <h2>Session Queue</h2>
            <p className="muted">Filter active sessions, archived closes, and variance-heavy sessions without losing reopen or close actions.</p>
          </div>
        </div>
        <div className="form-grid sync-filter-grid" style={{ marginTop: 12 }}>
          <label className="field">Search<input value={filters.q} onChange={(e) => setFilters((prev) => ({ ...prev, q: e.target.value }))} placeholder="session code, register, date, note" /></label>
          <label className="field">Status<select value={filters.status} onChange={(e) => setFilters((prev) => ({ ...prev, status: e.target.value }))}><option value="all">all</option><option value="open">open</option><option value="closed">closed</option></select></label>
          <label className="field-inline" style={{ alignSelf: 'end' }}><input type="checkbox" checked={filters.showArchived} onChange={(e) => setFilters((prev) => ({ ...prev, showArchived: e.target.checked }))} /> Show archived closed sessions</label>
        </div>

        <table className="table" style={{ marginTop: 10 }}>
          <thead><tr><th>Session</th><th>Register</th><th>Status</th><th>Opening</th><th>Expected</th><th>Actual</th><th>Variance</th><th></th></tr></thead>
          <tbody>
            {filteredSessions.map((row) => {
              const state = closeForm[row.id] || {};
              const register = registers.find((item) => item.id === row.register_id);
              const hasDrawerMapping = !!(row.register_accounting_financial_account_id || register?.accounting_financial_account_id);
              return (
                <tr key={row.id}>
                  <td>{row.session_code}<div className="small muted">{row.business_date} · {row.shift_name || '-'}</div><div className="small muted">{row.close_mode || '-'}{row.blind_close ? ' · blind' : ''}</div></td>
                  <td>{row.register_name}</td>
                  <td><span className={`badge ${row.status === 'open' ? 'success' : 'info'}`}>{row.status}</span></td>
                  <td>{money(row.opening_float)}</td>
                  <td>{money(row.closing_expected_cash)}</td>
                  <td>{row.closing_actual_cash == null ? '-' : money(row.closing_actual_cash)}</td>
                  <td><span className={`badge ${Math.abs(Number(row.variance_amount || 0)) > 0.009 ? 'warn' : 'success'}`}>{money(row.variance_amount)}</span>{row.variance_note ? <div className="small muted">{row.variance_note}</div> : null}</td>
                  <td>
                    {row.status === 'open' ? (
                      <div className="stack-tight">
                        {!hasDrawerMapping && <div className="card warn"><strong>Cannot close yet</strong><div className="small">Ask a manager to map {row.register_name} to its Accounting drawer first.</div></div>}
                        <div className="row wrap"><button className="secondary" disabled={!hasDrawerMapping} onClick={() => ensureCloseState(row.id)}>Prepare Count</button></div>
                        {closeForm[row.id] && (
                          <div className="stack-tight" style={{ minWidth: 300 }}>
                            <input type="number" step="0.01" placeholder="Counted cash" value={state.closing_actual_cash || ''} onChange={(e) => setCloseForm((prev) => ({ ...prev, [row.id]: { ...prev[row.id], closing_actual_cash: Number(e.target.value || 0) } }))} />
                            <div className="row wrap">
                              <select value={state.close_mode || 'verified'} onChange={(e) => setCloseForm((prev) => ({ ...prev, [row.id]: { ...prev[row.id], close_mode: e.target.value, blind_close: e.target.value === 'blind' } }))}><option value="verified">Verified close</option><option value="blind">Blind close</option></select>
                              <label className="field-inline"><input type="checkbox" checked={!!state.blind_close} onChange={(e) => setCloseForm((prev) => ({ ...prev, [row.id]: { ...prev[row.id], blind_close: e.target.checked, close_mode: e.target.checked ? 'blind' : 'verified' } }))} /> Blind close</label>
                            </div>
                            <textarea placeholder="Close note" value={state.closing_note || ''} onChange={(e) => setCloseForm((prev) => ({ ...prev, [row.id]: { ...prev[row.id], closing_note: e.target.value } }))} />
                            <textarea placeholder="Variance note if needed" value={state.variance_note || ''} onChange={(e) => setCloseForm((prev) => ({ ...prev, [row.id]: { ...prev[row.id], variance_note: e.target.value } }))} />
                            <div className="row wrap">
                              <input placeholder="Sign-off name" value={state.sign_off_name || ''} onChange={(e) => setCloseForm((prev) => ({ ...prev, [row.id]: { ...prev[row.id], sign_off_name: e.target.value } }))} />
                              <input placeholder="Sign-off role" value={state.sign_off_role || ''} onChange={(e) => setCloseForm((prev) => ({ ...prev, [row.id]: { ...prev[row.id], sign_off_role: e.target.value } }))} />
                            </div>
                            <div className="card">
                              <div className="small muted" style={{ marginBottom: 8 }}>Denominations</div>
                              <div className="row wrap">
                                {DENOMS.map((amount) => <label key={amount} className="field" style={{ width: 82 }}>{amount}<input type="number" min="0" placeholder="0" onChange={(e) => updateDenom(row.id, String(amount), e.target.value)} /></label>)}
                              </div>
                            </div>
                            <button className="secondary" disabled={!hasDrawerMapping} onClick={() => handleClose(row.id)}>Close</button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="stack-tight">
                        <button className="secondary" onClick={() => setReopenSessionId(row.id)}>Reopen</button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {!filteredSessions.length && <tr><td colSpan="8" className="muted">No sessions match the current filter.</td></tr>}
          </tbody>
        </table>
      </section>
      <ActionModal
        open={!!reopenSessionId}
        title={`Reopen session ${reopenSessionId || ''}?`}
        description="Reopening a closed drawer changes the shift audit trail. Record why correction work is needed."
        fieldLabel="Reopen reason"
        required
        confirmLabel="Reopen session"
        onClose={() => setReopenSessionId(null)}
        onConfirm={(reason) => handleReopen(reopenSessionId, reason)}
      />
    </div>
  );
}
